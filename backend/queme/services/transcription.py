from flask import current_app

_model = None


def transcribe(audio_bytes: bytes, suffix: str = ".webm"):
    """Return transcript, word timestamps, language, status."""
    import tempfile
    from pathlib import Path

    model_name = current_app.config.get("WHISPER_MODEL") or "base"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(audio_bytes)
    tmp.close()
    path = Path(tmp.name)
    try:
        global _model
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            return {
                "transcript": "",
                "words": [],
                "language": "en",
                "status": "UNAVAILABLE",
                "error": f"faster-whisper not installed: {exc}",
            }
        if _model is None:
            _model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = _model.transcribe(str(path), word_timestamps=True)
        texts = []
        words = []
        for seg in segments:
            texts.append(seg.text.strip())
            if getattr(seg, "words", None):
                for w in seg.words:
                    words.append(
                        {
                            "word": w.word,
                            "start": float(w.start or 0),
                            "end": float(w.end or 0),
                        }
                    )
        transcript = " ".join(t for t in texts if t).strip()
        return {
            "transcript": transcript,
            "words": words,
            "language": getattr(info, "language", "en"),
            "status": "OK" if transcript else "EMPTY",
        }
    except Exception as exc:
        return {
            "transcript": "",
            "words": [],
            "language": "en",
            "status": "ERROR",
            "error": str(exc),
        }
    finally:
        path.unlink(missing_ok=True)
