"""
audio/player.py
===============
Cross-platform audio playback for WAV and MP3 files.

Playback strategy (tried in order)
-----------------------------------
1. ``pygame.mixer``  — most reliable cross-platform MP3 + WAV support.
2. OS-native fallback:
     macOS   → ``afplay``
     Windows → PowerShell / Windows Media Player COM object
     Linux   → ``mpg123`` → ``ffplay`` → ``aplay``

Design notes
------------
* The player is intentionally stateless — it simply plays a file and
  blocks until playback is complete.
* No audio data is stored in memory; the file path is all that is needed.
* Callers (e.g. VoiceModule) do not need to know which backend is used.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioPlayer:
    """
    Plays audio files with cross-platform support.

    Blocks the calling thread until playback has finished, so the
    pipeline (record → transcribe → respond → speak) runs in the
    correct order without any extra synchronisation.

    Usage
    -----
    >>> player = AudioPlayer()
    >>> player.play("audio/response.mp3")

    Raises
    ------
    FileNotFoundError
        If the specified audio file does not exist on disk.
    RuntimeError
        If every available playback backend fails.
    """

    def play(self, file_path: str) -> None:
        """
        Play an audio file and block until playback is complete.

        Args:
            file_path: Path to the audio file (MP3 or WAV).

        Raises:
            FileNotFoundError: If the file does not exist.
            RuntimeError:      If no playback backend succeeds.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(
                f"[AudioPlayer] File not found: {file_path}\n"
                "Make sure TTSService.synthesize() completed successfully."
            )

        logger.info("Playing audio file: %s", file_path)

        # ── Strategy 1: pygame (preferred — works on all platforms with MP3) ──
        if self._play_via_pygame(str(path)):
            return

        # ── Strategy 2: OS-native fallback ────────────────────────────────────
        logger.debug("pygame unavailable or failed — switching to OS-native playback.")
        self._play_native(str(path))

    # ═══════════════════════════════════════════════════════════════════════════
    # Backend: pygame
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _play_via_pygame(file_path: str) -> bool:
        """
        Attempt playback via ``pygame.mixer``.

        Returns ``True`` on success, ``False`` if pygame is not installed
        or raises an unexpected error (so the caller can try a fallback).
        """
        try:
            import pygame  # optional dependency — graceful fallback if absent

            pygame.mixer.init()
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()

            # Block until the track finishes
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)

            pygame.mixer.music.unload()
            pygame.mixer.quit()
            logger.debug("pygame playback finished: %s", file_path)
            return True

        except ImportError:
            logger.debug(
                "pygame is not installed.  "
                "Install it with: pip install pygame  "
                "Falling back to OS-native playback."
            )
            return False

        except Exception as exc:
            logger.warning(
                "pygame playback failed for %s: %s  — trying OS-native fallback.",
                file_path,
                exc,
            )
            return False

    # ═══════════════════════════════════════════════════════════════════════════
    # Backend: OS-native
    # ═══════════════════════════════════════════════════════════════════════════

    def _play_native(self, file_path: str) -> None:
        """Route to the correct OS-native playback implementation."""
        platform = sys.platform

        if platform == "darwin":
            self._play_macos(file_path)
        elif platform == "win32":
            self._play_windows(file_path)
        else:
            self._play_linux(file_path)

    # ── macOS ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _play_macos(file_path: str) -> None:
        """Use the built-in ``afplay`` command (supports MP3 and WAV natively)."""
        try:
            subprocess.run(["afplay", file_path], check=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"afplay failed for {file_path}: {exc}") from exc

    # ── Windows ────────────────────────────────────────────────────────────────

    @staticmethod
    def _play_windows(file_path: str) -> None:
        """
        Play audio on Windows via PowerShell + Windows Media Player COM object.

        Supports both WAV and MP3.  Falls back to ``os.startfile`` if the
        PowerShell command fails (non-blocking, waits a fixed duration).
        """
        abs_path = os.path.abspath(file_path)

        # PowerShell script: load → play → wait for natural end
        ps_script = (
            "Add-Type -AssemblyName presentationCore; "
            "$player = New-Object System.Windows.Media.MediaPlayer; "
            f"$player.Open([System.Uri]::new('{abs_path}')); "
            "Start-Sleep -Milliseconds 800; "
            "$player.Play(); "
            "do { Start-Sleep -Milliseconds 200 } "
            "while ("
            "    $player.NaturalDuration.HasTimeSpan -and "
            "    $player.Position -lt $player.NaturalDuration.TimeSpan"
            "); "
            "$player.Close()"
        )

        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    ps_script,
                ],
                check=True,
                timeout=120,  # safety cap — no track should exceed 2 minutes
            )
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            logger.warning(
                "PowerShell playback failed (%s). Falling back to os.startfile.", exc
            )

        # Last resort: open with the system default media player (non-blocking)
        try:
            os.startfile(abs_path)  # type: ignore[attr-defined]
            # Give the external player a few seconds to start and play
            time.sleep(6)
        except AttributeError:
            raise RuntimeError(
                "os.startfile is not available on this platform.  "
                "Install pygame:  pip install pygame"
            )

    # ── Linux ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _play_linux(file_path: str) -> None:
        """
        Try common Linux CLI audio players in priority order.

        Order: mpg123 → ffplay → aplay → paplay

        Raises:
            RuntimeError: If none of the players is installed or succeeds.
        """
        candidates: list[list[str]] = [
            ["mpg123", "-q", file_path],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", file_path],
            ["aplay", file_path],
            ["paplay", file_path],
        ]

        for cmd in candidates:
            try:
                subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.debug("Linux playback via %r succeeded.", cmd[0])
                return
            except FileNotFoundError:
                logger.debug("Player %r not found — trying next.", cmd[0])
            except subprocess.CalledProcessError as exc:
                logger.debug("Player %r exited with error: %s", cmd[0], exc)

        raise RuntimeError(
            "No audio player found on this Linux system.\n"
            "Fix options:\n"
            "  pip install pygame              (recommended)\n"
            "  sudo apt install mpg123         (CLI fallback)\n"
            "  sudo apt install ffmpeg         (ffplay fallback)"
        )
