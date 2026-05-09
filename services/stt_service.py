"""
services/stt_service.py
=======================
Speech-to-Text Service — Groq Whisper (whisper-large-v3)

Responsibilities
----------------
* Accept a local audio file path.
* Submit it to Groq's Whisper transcription API.
* Return the transcribed text as a plain Python string.
* Retry transiently-failing requests with exponential back-off.

This service is intentionally stateless — it holds no audio buffers and
has no knowledge of how audio was recorded or what happens to the text
afterwards.  Those concerns belong to the caller (VoiceModule).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from groq import Groq

from config.settings import (
    GROQ_API_KEY,
    MAX_RETRIES,
    RETRY_DELAY,
    STT_LANGUAGE,
    STT_MODEL,
)

logger = logging.getLogger(__name__)


class STTService:
    """
    Wraps Groq's Whisper transcription API with resilience primitives.

    Usage
    -----
    >>> svc = STTService()
    >>> text = svc.transcribe("audio/input.wav")
    >>> print(text)
    "What is the weather like today?"

    Supported formats
    -----------------
    Any audio format accepted by Groq's API:  WAV, MP3, MP4, M4A, FLAC, OGG, WEBM.
    In practice Jarvis always passes a WAV file produced by ``AudioRecorder``.
    """

    def __init__(self) -> None:
        self._client = Groq(api_key=GROQ_API_KEY)
        self._model = STT_MODEL
        self._language = STT_LANGUAGE
        logger.info(
            "STTService ready  (model=%s, language=%s)", self._model, self._language
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def transcribe(self, file_path: str) -> str:
        """
        Transcribe the audio file at *file_path* to text.

        Args:
            file_path: Absolute or relative path to an audio file.

        Returns:
            The transcribed text as a stripped string.
            Returns an empty string if the audio contained no speech.

        Raises:
            FileNotFoundError: If *file_path* does not exist on disk.
            RuntimeError:      If all retry attempts are exhausted.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(
                f"[STTService] Audio file not found: {file_path}\n"
                "Make sure AudioRecorder.record() completed successfully."
            )

        logger.info(
            "Starting transcription  (file=%s, model=%s)", path.name, self._model
        )
        return self._transcribe_with_retry(path)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _transcribe_with_retry(self, path: Path) -> str:
        """
        Submit the audio to Groq with exponential-back-off retry.

        The delay between attempts grows linearly:
          attempt 1 → wait RETRY_DELAY * 1 s
          attempt 2 → wait RETRY_DELAY * 2 s
          …

        This avoids hammering the API on transient network errors while
        still recovering quickly from brief outages.
        """
        last_exc: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with path.open("rb") as audio_file:
                    kwargs = {
                        "model": self._model,
                        "file": audio_file,
                        "response_format": "text",  # plain string — no JSON parsing needed
                    }
                    if self._language and self._language.lower() != "auto":
                        kwargs["language"] = self._language

                    result = self._client.audio.transcriptions.create(**kwargs)

                # Groq returns a plain str when response_format="text";
                # guard against potential future SDK changes that wrap it.
                text: str = (
                    result
                    if isinstance(result, str)
                    else getattr(result, "text", "") or ""
                )
                text = text.strip()

                if text:
                    logger.info(
                        "Transcription OK (attempt %d/%d): %r…",
                        attempt,
                        MAX_RETRIES,
                        text[:60],
                    )
                else:
                    logger.warning(
                        "Transcription returned empty text (attempt %d/%d). "
                        "The recording may have been silent.",
                        attempt,
                        MAX_RETRIES,
                    )

                return text

            except FileNotFoundError:
                # File disappeared between our existence check and the open —
                # no point retrying, re-raise immediately.
                raise

            except Exception as exc:
                last_exc = exc
                wait = RETRY_DELAY * attempt
                logger.warning(
                    "STT API attempt %d/%d failed: %s  — retrying in %.1fs…",
                    attempt,
                    MAX_RETRIES,
                    exc,
                    wait,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(wait)

        logger.error(
            "All %d STT retry attempts exhausted for file %s.",
            MAX_RETRIES,
            path.name,
        )
        raise RuntimeError(
            f"STT transcription failed after {MAX_RETRIES} attempts."
        ) from last_exc
