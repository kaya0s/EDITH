"""
services/tts_service.py
=======================
Text-to-Speech Service — Microsoft Edge TTS (en-US-AriaNeural)

Design notes
------------
* Edge TTS is natively async; ``synthesize_async`` is the canonical method.
* ``synthesize`` is a sync wrapper so non-async call sites (e.g. the voice
  module's pipeline) can call it without managing an event loop themselves.
* The event-loop detection logic handles three runtime contexts safely:
    1. Standard script  → asyncio.run()
    2. Already-running loop (Jupyter / FastAPI) → ThreadPoolExecutor
    3. Closed/missing loop → asyncio.run() on a fresh loop
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from pathlib import Path
from typing import Optional

import edge_tts

from config.settings import (
    OUTPUT_AUDIO_PATH,
    TTS_PITCH,
    TTS_RATE,
    TTS_VOICE,
    TTS_VOLUME,
)

logger = logging.getLogger(__name__)


class TTSService:
    """
    Synthesises text to speech using the Edge TTS neural engine.

    The audio is saved as an MP3 file and the path is returned so the
    caller can decide what to do with it (e.g. auto-play, store, stream).

    Usage
    -----
    Synchronous (most common)::

        svc = TTSService()
        path = svc.synthesize("Hello, I am Jarvis.")

    Asynchronous::

        svc = TTSService()
        path = await svc.synthesize_async("Hello, I am Jarvis.")

    Custom voice / output path::

        svc = TTSService(voice="en-GB-RyanNeural", output_path="/tmp/out.mp3")
        path = svc.synthesize("Cheerio!")
    """

    def __init__(
        self,
        voice: str = TTS_VOICE,
        output_path: str = OUTPUT_AUDIO_PATH,
        rate: str = TTS_RATE,
        pitch: str = TTS_PITCH,
        volume: str = TTS_VOLUME,
    ) -> None:
        self._voice = voice
        self._default_output = output_path
        self._rate = rate
        self._pitch = pitch
        self._volume = volume
        # Ensure the output directory exists at construction time
        Path(self._default_output).parent.mkdir(parents=True, exist_ok=True)
        logger.info(
            "TTSService ready  (voice=%s, rate=%s, pitch=%s, volume=%s)",
            self._voice,
            self._rate,
            self._pitch,
            self._volume,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def synthesize_async(
        self,
        text: str,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Asynchronously convert *text* to speech and save the result.

        Args:
            text:        The text to synthesise.  Must be non-empty.
            output_path: Override the default output file path.

        Returns:
            The absolute path to the generated MP3 file.

        Raises:
            ValueError:  If *text* is empty.
            RuntimeError: If the Edge TTS API call fails.
        """
        if not text or not text.strip():
            raise ValueError("TTS text must be a non-empty string.")

        path = output_path or self._default_output
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Synthesising %d char(s) of text → %s  (voice=%s)",
            len(text),
            path,
            self._voice,
        )

        try:
            communicate = edge_tts.Communicate(
                text.strip(),
                self._voice,
                rate=self._rate,
                pitch=self._pitch,
                volume=self._volume,
            )
            await communicate.save(path)
            logger.info("TTS synthesis complete → %s", path)
            return path

        except Exception as exc:
            logger.error("TTS synthesis failed: %s", exc, exc_info=True)
            raise RuntimeError(f"TTS synthesis failed: {exc}") from exc

    def synthesize(
        self,
        text: str,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Synchronous wrapper around :meth:`synthesize_async`.

        Handles the event-loop lifecycle automatically so callers do not
        need to be async-aware:

        * If no event loop is running, uses ``asyncio.run()``.
        * If a loop is already running (e.g. inside Jupyter or FastAPI),
          dispatches to a ``ThreadPoolExecutor`` to avoid a dead-lock.

        Args:
            text:        The text to synthesise.
            output_path: Override the default output file path.

        Returns:
            The absolute path to the generated MP3 file.
        """
        coro = self.synthesize_async(text, output_path)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No current event loop in this thread — create one via asyncio.run
            return asyncio.run(coro)

        if loop.is_running():
            # We're already inside a running loop (Jupyter, FastAPI, etc.).
            # Run the coroutine in a separate thread to avoid blocking.
            logger.debug(
                "Detected running event loop — delegating TTS to ThreadPoolExecutor."
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def voice(self) -> str:
        """The Edge TTS voice currently in use."""
        return self._voice

    @voice.setter
    def voice(self, value: str) -> None:
        logger.info("TTSService voice changed: %s → %s", self._voice, value)
        self._voice = value

    # ── Dunder helpers ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"<TTSService voice={self._voice!r} rate={self._rate!r} "
            f"pitch={self._pitch!r} volume={self._volume!r} "
            f"output={self._default_output!r}>"
        )
