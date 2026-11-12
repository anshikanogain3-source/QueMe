import { useEffect, useState } from "react";
import { api } from "../api.js";

export function AuthenticatedAudio({ path }) {
  const [source, setSource] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    setSource("");
    setError("");

    if (!path) return undefined;

    api(path)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (active) setSource(objectUrl);
      })
      .catch((err) => {
        if (active) setError(err.message);
      });

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (error) return <span className="muted small-copy">Audio unavailable</span>;
  if (!source) return <span className="muted small-copy">Loading audio…</span>;
  return (
    <audio
      className="stored-audio"
      controls
      preload="none"
      src={source}
      onError={() => setError("Audio unavailable")}
    />
  );
}

