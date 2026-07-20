from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class TextToSpeech:
    """Natural TTS using Piper; falls back to macOS 'say' when unavailable."""

    def __init__(self, voice: str = "en_US-amy-medium") -> None:
        self.voice = voice
        self._piper_bin = shutil.which("piper")

    def speak(self, text: str) -> None:
        if not text.strip():
            return
        if self._piper_bin:
            self._speak_with_piper(text)
            return
        # Fallback for local development.
        subprocess.run(["say", text], check=False)

    def _speak_with_piper(self, text: str) -> None:
        model_path = self._resolve_piper_model()
        if not model_path:
            raise RuntimeError(
                "Piper is installed but no voice model found. "
                "Set PROJECT_WE_PIPER_MODEL_PATH or install a voice model."
            )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            out_path = Path(tmp.name)
        subprocess.run(
            [self._piper_bin, "--model", str(model_path), "--output_file", str(out_path)],
            input=text.encode("utf-8"),
            check=True,
        )
        subprocess.run(["afplay", str(out_path)], check=False)
        out_path.unlink(missing_ok=True)

    def _resolve_piper_model(self) -> Path | None:
        # Primary explicit path
        import os

        explicit = os.getenv("PROJECT_WE_PIPER_MODEL_PATH")
        if explicit:
            p = Path(explicit)
            return p if p.exists() else None

        home = Path.home()
        candidates = [
            home / ".local" / "share" / "piper" / f"{self.voice}.onnx",
            home / ".piper" / f"{self.voice}.onnx",
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

