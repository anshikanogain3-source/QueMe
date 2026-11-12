import logging
import math
import re
from collections import Counter

FILLERS = {
    "um",
    "uh",
    "erm",
    "ah",
    "like",
    "basically",
    "actually",
    "literally",
    "you know",
    "i mean",
}

INTENT_PATTERNS = [
    ("REPEAT", re.compile(r"^(?:repeat|repeat that|say that again|could you repeat that|come again)[.!?]*$", re.I)),
    ("SKIP", re.compile(r"^(?:skip|skip this question|next question|pass this question)[.!?]*$", re.I)),
    ("DONE", re.compile(r"^(?:i am done|i'm done|finish interview|end interview|that is all|that's all)[.!?]*$", re.I)),
]

logger = logging.getLogger(__name__)


def tokenize(text: str):
    return re.findall(r"[a-zA-Z']+", (text or "").lower())


def detect_intent(transcript: str):
    utterance = re.sub(r"\s+", " ", (transcript or "").replace("’", "'").strip())
    for name, pattern in INTENT_PATTERNS:
        if pattern.fullmatch(utterance):
            return name
    return "ANSWER"


def filler_stats(transcript: str):
    text = (transcript or "").lower()
    found = []
    for phrase in ("you know", "i mean"):
        count = text.count(phrase)
        found.extend([phrase] * count)
        text = text.replace(phrase, " ")
    words = tokenize(text)
    for w in words:
        if w in FILLERS:
            found.append(w)
    return found


def repetition_count(transcript: str):
    words = tokenize(transcript)
    if len(words) < 2:
        return 0
    repeats = 0
    for a, b in zip(words, words[1:]):
        if a == b and len(a) > 2:
            repeats += 1
    counts = Counter(words)
    for w, c in counts.items():
        if len(w) > 3 and c >= 4:
            repeats += c - 3
    return repeats


def keyword_hits(transcript: str, key_points: str):
    if not key_points:
        return []
    tokens = set(tokenize(transcript))
    hits = []
    for raw in re.split(r"[,;\n]", key_points):
        term = raw.strip().lower()
        if not term:
            continue
        parts = tokenize(term)
        if parts and all(p in tokens for p in parts):
            hits.append(term)
    return hits


def _load_audio(path_or_bytes):
    import numpy as np

    av_error_type = None
    if isinstance(path_or_bytes, (bytes, bytearray)):
        try:
            import av
            import io

            container = av.open(io.BytesIO(path_or_bytes))
            stream = next((s for s in container.streams if s.type == "audio"), None)
            if stream is not None:
                resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
                chunks = []
                for frame in container.decode(stream):
                    for converted in resampler.resample(frame):
                        chunks.append(converted.to_ndarray().reshape(-1))
                for converted in resampler.resample(None):
                    chunks.append(converted.to_ndarray().reshape(-1))
                container.close()
                if chunks:
                    return np.concatenate(chunks).astype(np.float32), 16000
        except Exception as exc:
            av_error_type = type(exc).__name__

    try:
        import librosa
        import io

        if isinstance(path_or_bytes, (bytes, bytearray)):
            y, sr = librosa.load(io.BytesIO(path_or_bytes), sr=16000, mono=True)
        else:
            y, sr = librosa.load(path_or_bytes, sr=16000, mono=True)
        return y.astype(np.float32), sr
    except Exception as exc:
        logger.warning(
            "Audio decoding failed av_error_type=%s librosa_error_type=%s",
            av_error_type or "not_attempted",
            type(exc).__name__,
        )
        return None, None


def analyze_audio(audio_bytes: bytes, transcript: str, words: list, key_points: str = ""):
    import numpy as np

    y, sr = _load_audio(audio_bytes)
    duration = 0.0
    rms_mean = 0.0
    rms_std = 0.0
    pitch_mean = 0.0
    pitch_std = 0.0
    pause_count = 0
    total_pause = 0.0
    longest_pause = 0.0
    speech_ratio = 0.0
    quality = "OK"
    noise = "UNKNOWN"
    usable = True

    if y is not None and sr:
        duration = float(len(y) / sr)
        frame = int(0.03 * sr)
        hop = int(0.015 * sr)
        if hop < 1:
            hop = 1
        rms = []
        for i in range(0, max(len(y) - frame, 1), hop):
            chunk = y[i : i + frame]
            rms.append(float(np.sqrt(np.mean(chunk**2) + 1e-12)))
        rms = np.array(rms) if rms else np.array([0.0])
        rms_mean = float(np.mean(rms))
        rms_std = float(np.std(rms))
        thresh = max(float(np.median(rms) * 0.6), 0.005)
        silent = rms < thresh
        speaking_frames = int((~silent).sum())
        speech_ratio = float(speaking_frames / max(len(rms), 1))
        speaking_duration = speech_ratio * duration

        in_pause = False
        pause_len = 0
        for flag in silent:
            if flag:
                in_pause = True
                pause_len += 1
            elif in_pause:
                sec = pause_len * hop / sr
                if sec >= 0.35:
                    pause_count += 1
                    total_pause += sec
                    longest_pause = max(longest_pause, sec)
                in_pause = False
                pause_len = 0
        if in_pause:
            sec = pause_len * hop / sr
            if sec >= 0.35:
                pause_count += 1
                total_pause += sec
                longest_pause = max(longest_pause, sec)

        try:
            import librosa

            f0 = librosa.yin(y, fmin=50, fmax=400, sr=sr)
            voiced = f0[(f0 > 50) & (f0 < 400)]
            if len(voiced):
                pitch_mean = float(np.mean(voiced))
                pitch_std = float(np.std(voiced))
        except Exception as exc:
            logger.debug("Optional pitch extraction failed error_type=%s", type(exc).__name__)

        if duration < 0.8 or rms_mean < 0.004:
            quality = "POOR"
            usable = False
        elif speech_ratio < 0.15:
            quality = "POOR"
            usable = False
        else:
            quality = "OK"
        noise = "HIGH" if rms_std > 0.08 and speech_ratio < 0.4 else "LOW"
    else:
        if words:
            duration = float(max(w.get("end", 0) for w in words) or 0)
        speaking_duration = duration * 0.8
        speech_ratio = 0.8 if transcript else 0.0
        quality = "UNKNOWN"
        usable = bool(transcript)

    word_count = max(len(tokenize(transcript)), 1 if transcript else 0)
    minutes = max(duration / 60.0, 1 / 60.0)
    wpm = word_count / minutes if duration else 0.0
    fillers = filler_stats(transcript)
    filler_rate = len(fillers) / max(word_count, 1)
    reps = repetition_count(transcript)
    intent = detect_intent(transcript)
    keywords = keyword_hits(transcript, key_points)

    delivery = _delivery_score(
        wpm=wpm,
        filler_rate=filler_rate,
        pause_count=pause_count,
        longest_pause=longest_pause,
        speech_ratio=speech_ratio,
        usable=usable,
        duration=duration,
    )

    return {
        "transcript": transcript,
        "language_detected": "en",
        "answer_duration_seconds": round(duration, 2),
        "speaking_duration_seconds": round(speaking_duration if y is not None else duration * speech_ratio, 2),
        "words_per_minute": round(wpm, 2),
        "pause_count": pause_count,
        "total_pause_duration_seconds": round(total_pause, 2),
        "longest_pause_seconds": round(longest_pause, 2),
        "filler_word_count": len(fillers),
        "filler_word_rate": round(filler_rate, 4),
        "repetition_count": reps,
        "speech_ratio": round(speech_ratio, 4),
        "technical_keywords_found": keywords,
        "filler_words_found": fillers,
        "detected_intent": intent,
        "audio_quality_status": quality,
        "background_noise_level": noise,
        "audio_usable": usable,
        "pitch_mean_hz": round(pitch_mean, 2),
        "pitch_std_hz": round(pitch_std, 2),
        "rms_mean": round(rms_mean, 6),
        "rms_std": round(rms_std, 6),
        "delivery_score": delivery,
        "analysis_json": {"word_timestamps": words[:400]},
    }


def _delivery_score(wpm, filler_rate, pause_count, longest_pause, speech_ratio, usable, duration):
    if not usable:
        return 3.0
    score = 8.0
    if 90 <= wpm <= 170:
        score += 1.0
    elif wpm < 60 or wpm > 210:
        score -= 1.5
    else:
        score -= 0.5
    score -= min(filler_rate * 8, 2.5)
    score -= min(pause_count * 0.15, 1.5)
    if longest_pause > 3:
        score -= 0.8
    if speech_ratio < 0.4:
        score -= 1.0
    elif 0.55 <= speech_ratio <= 0.9:
        score += 0.5
    if duration < 5:
        score -= 1.0
    return round(max(1.0, min(10.0, score)), 2)


def combine_scores(content: float, delivery: float, content_w=0.70, delivery_w=0.30):
    return round(content_w * float(content) + delivery_w * float(delivery), 2)
