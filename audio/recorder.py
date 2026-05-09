"""
audio/recorder.py
=================
Microphone recorder for the Jarvis platform.

Records audio from the default system microphone using ``sounddevice``
and persists it as a 16-bit mono WAV file via ``scipy.io.wavfile``.

Design notes
------------
* Stateless across calls — each ``record()`` invocation is independent.
* Configurable sample rate, duration, and output path via constructor
  args (all fall back to values in ``config/settings.py``).
* Prints a friendly console prompt so the user knows exactly when to speak.
* Raises ``RuntimeError`` (not raw PortAudioError) so callers only need to
  handle one exception type for device-level failures.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write

from config.settings import INPUT_AUDIO_PATH, SAMPLE_RATE, PTT_KEY

logger = logging.getLogger(__name__)


class AudioRecorder:
    """
    Captures microphone audio and saves it as a WAV file.

    Usage
    -----
    Default settings (from ``config/settings.py``)::

        recorder = AudioRecorder()
        path = recorder.record()          # records while key is pressed

    Recording is controlled by pressing and holding the push-to-talk key::

        path = recorder.record()   # records while key is held

    Custom instance config::

        recorder = AudioRecorder(sample_rate=16_000, output_path="/tmp/mic.wav")
        path = recorder.record()
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        output_path: str = INPUT_AUDIO_PATH,
    ) -> None:
        self._sample_rate = sample_rate
        self._output_path = output_path
        self._last_frames: Optional[np.ndarray] = None

        # Guarantee the output directory exists before any recording attempt
        Path(self._output_path).parent.mkdir(parents=True, exist_ok=True)

        logger.debug(
            "AudioRecorder ready  (sample_rate=%d Hz, output=%s)",
            self._sample_rate,
            self._output_path,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def record(self, duration: Optional[int] = None) -> str:
        """
        Record audio from the default microphone and save it to disk.

        The call blocks until the Spacebar is released.

        Args:
            duration: Ignored.
        """
        import keyboard
        import time
        from utils import ui
        import queue

        logger.info(
            "Recording started  (Push-To-Talk @ %d Hz → %s)",
            self._sample_rate,
            self._output_path,
        )

        q = queue.Queue()
        def callback(indata, frames, time_info, status):
            if status:
                pass
            q.put(indata.copy())

        try:
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype=np.int16,
                callback=callback
            ):
                frames_list = []
                while keyboard.is_pressed(PTT_KEY):
                    try:
                        chunk = q.get_nowait()
                        frames_list.append(chunk)
                        
                        if chunk.size > 0:
                            rms = np.sqrt(np.mean(np.square(chunk.astype(np.float32) / 32768.0)))
                            ui.set_audio_level(float(rms))
                    except queue.Empty:
                        pass
                    
                    time.sleep(0.01)

            ui.set_audio_level(0.0)
            
            if not frames_list:
                self._last_frames = np.array([], dtype=np.int16)
            else:
                self._last_frames = np.concatenate(frames_list, axis=0)

        except sd.PortAudioError as exc:
            msg = (
                f"Microphone access failed: {exc}\n"
                "Possible causes:\n"
                "  • No audio input device is connected.\n"
                "  • The device is in use by another application.\n"
                "  • OS-level microphone permissions are denied."
            )
            logger.error(msg)
            raise RuntimeError(msg) from exc

        except Exception as exc:
            logger.error("Unexpected recording error: %s", exc, exc_info=True)
            raise RuntimeError(f"Audio recording failed unexpectedly: {exc}") from exc

        self._save(self._last_frames)
        return self._output_path

    # ── Private helpers ───────────────────────────────────────────────────────

    def _save(self, frames: np.ndarray) -> None:
        """Write *frames* to the configured WAV output path."""
        write(self._output_path, self._sample_rate, frames)
        logger.info("Recording saved → %s", self._output_path)

    # ── Properties (read-only) ────────────────────────────────────────────────

    @property
    def sample_rate(self) -> int:
        """Sample rate used for recordings (Hz)."""
        return self._sample_rate

    @property
    def output_path(self) -> str:
        """File system path where the last recording was (or will be) saved."""
        return self._output_path

    def is_silent(self, threshold: float = 0.005) -> bool:
        """
        Check if the last recording was essentially silent.

        Parameters
        ----------
        threshold : float
            RMS volume threshold (0.0 to 1.0).  Default 0.005 is very sensitive.
            Increase this if background noise is triggering Jarvis.
        """
        if self._last_frames is None or self._last_frames.size == 0:
            return True

        # Calculate Root Mean Square (RMS) volume normalized to [0, 1]
        # np.int16 max value is 32768
        rms = np.sqrt(np.mean(np.square(self._last_frames.astype(np.float32) / 32768.0)))
        logger.debug("Last recording RMS volume: %.6f (threshold: %.6f)", rms, threshold)
        
        return rms < threshold

    # ── Dunder helpers ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"<AudioRecorder sample_rate={self._sample_rate} "
            f"output={self._output_path!r}>"
        )
