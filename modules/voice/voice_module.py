"""
modules/voice/voice_module.py
=============================
Voice Interaction Module — Feature #1 of the Jarvis Platform

Pipeline
--------
    Microphone Input
         │
         ▼
    AudioRecorder          ← audio/recorder.py
         │  (input.wav)
         ▼
    STTService             ← services/stt_service.py   (Groq Whisper-large-v3)
         │  (transcript)
         ▼
    LLMService             ← services/llm_service.py   (Groq LLaMA-3.1-8b-instant)
         │  (response text)
         ▼
    TTSService             ← services/tts_service.py   (Edge TTS — en-US-AriaNeural)
         │  (response.mp3)
         ▼
    AudioPlayer            ← audio/player.py

Architecture rules
------------------
* Calls services — does NOT implement them.
* Inherits from BaseModule — plugs into Orchestrator with zero changes.
* All terminal output is routed through utils/ui.py — zero raw print() calls.
* All configuration comes from config/settings.py — nothing hardcoded here.
"""

from __future__ import annotations

import logging
import re
from typing import Any, FrozenSet, Optional

from audio.player import AudioPlayer
from audio.recorder import AudioRecorder
from config.settings import EXIT_PHRASES as _SETTINGS_EXIT_PHRASES
from config.settings import PING_AUDIO_PATH, SILENCE_THRESHOLD
from config.settings import PTT_KEY
from core.orchestrator import BaseModule
from services.llm_service import LLMService
from services.stt_service import STTService
from services.tts_service import TTSService
from utils import ui

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exit phrases — loaded from .env / settings.py
# ---------------------------------------------------------------------------

_DEFAULT_EXIT_PHRASES: FrozenSet[str] = frozenset(_SETTINGS_EXIT_PHRASES)

# ---------------------------------------------------------------------------
# Return type for a single voice cycle
# ---------------------------------------------------------------------------

VoiceCycleResult = dict[str, Any]
"""
Keys
----
transcription : str  — what the user said  (empty if inaudible)
response      : str  — JARVIS text reply   (empty if skipped)
audio_path    : str  — path to the MP3     (empty if skipped)
success       : bool — False when cycle was skipped
"""


class VoiceModule(BaseModule):
    """
    Self-contained voice interaction module for the Jarvis platform.

    Two operation modes
    -------------------
    Single turn  → ``module.run()``
    Continuous   → ``module.run_continuous()``

    Every pipeline stage delegates to a dedicated service or audio class.
    All user-facing output goes through ``utils.ui`` — no raw print() here.
    """

    # ── BaseModule contract ───────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "voice"

    def on_load(self) -> None:
        """
        Initialise all services once, immediately after registration.

        If any service raises (e.g. missing API key) the error surfaces here
        — before the first conversation turn — so startup fails fast and
        clearly rather than mid-conversation.
        """
        logger.info("VoiceModule: initialising services…")

        try:
            with ui.Spinner("Initialising services…"):
                self._recorder: AudioRecorder = AudioRecorder()
                self._player: AudioPlayer = AudioPlayer()
                self._stt: STTService = STTService()
                self._llm: LLMService = LLMService()
                self._tts: TTSService = TTSService()

        except Exception as exc:
            logger.critical("VoiceModule failed to initialise: %s", exc, exc_info=True)
            ui.print_error(f"Failed to initialise voice module: {exc}")
            raise

        logger.info("VoiceModule loaded — all services online.")
        ui.print_system("All systems online.")

    def on_unload(self) -> None:
        logger.info("VoiceModule unloaded.")

    def run(self, **kwargs) -> VoiceCycleResult:
        """
        Execute a single listen → transcribe → respond → speak cycle.
        """
        return self._run_cycle()

    # ── Continuous mode ───────────────────────────────────────────────────────

    def run_continuous(
        self,
        exit_phrases: Optional[FrozenSet[str]] = None,
    ) -> None:
        """
        Run the voice pipeline in an infinite loop.

        Exits cleanly when the user speaks an exit phrase or presses Ctrl-C.
        Errors in a single cycle are caught, displayed, and the loop continues.

        Args:
            exit_phrases : phrases that trigger shutdown (falls back to .env).
        """
        exits = exit_phrases or _DEFAULT_EXIT_PHRASES
        logger.info("VoiceModule entering continuous mode.")

        while True:
            try:
                result = self._run_cycle()

                if not result["success"]:
                    continue

                spoken = result["transcription"].lower().strip()

                if self._is_exit_phrase(spoken, exits):
                    ui.print_goodbye()
                    logger.info("Exit phrase detected — stopping continuous mode.")
                    break

            except ui.InteractionModeToggle:
                raise

            except KeyboardInterrupt:
                ui.print_goodbye()
                logger.info("VoiceModule interrupted by user (ESC).")
                break

            except Exception as exc:
                logger.error(
                    "Unhandled error in voice cycle (loop continues): %s",
                    exc,
                    exc_info=True,
                )
                ui.print_error(f"{type(exc).__name__}: {exc}")

        logger.info("VoiceModule exited continuous mode.")

    # ── Core pipeline ─────────────────────────────────────────────────────────

    def _run_cycle(self) -> VoiceCycleResult:
        """
        One complete listen → transcribe → respond → speak turn.

        Steps
        -----
        1. Show listening prompt  →  record microphone  →  save input.wav
        2. Spinner  →  STT transcription via Groq Whisper
        3. Display user text
        4. Spinner  →  LLM response via Groq LLaMA
        5. Typewriter stream of JARVIS response
        6. Spinner  →  TTS synthesis via Edge TTS
        7. Play audio response

        Returns
        -------
        VoiceCycleResult
        """
        _empty: VoiceCycleResult = {
            "transcription": "",
            "response": "",
            "audio_path": "",
            "success": False,
        }

        # ── 1. Record ─────────────────────────────────────────────────────────
        import keyboard
        import time

        ui.print_hold_space_prompt()
        
        # Wait until space is pressed or ESC for quit
        while not keyboard.is_pressed(PTT_KEY):
            pending = ui.consume_mode_toggle_request()
            if pending is not None and not ui.is_llm_busy():
                ui.clear_prompt()
                raise ui.InteractionModeToggle(pending)
            if keyboard.is_pressed("alt") and keyboard.is_pressed("q") and not ui.is_llm_busy():
                ui.clear_prompt()
                raise ui.InteractionModeToggle()
            if keyboard.is_pressed("ctrl") and keyboard.is_pressed("q") and not ui.is_llm_busy():
                ui.clear_prompt()
                raise ui.InteractionModeToggle()
            if keyboard.is_pressed('esc'):
                ui.print_goodbye()
                raise KeyboardInterrupt("ESC pressed")
            time.sleep(0.05)
            
        ui.clear_prompt()

        # Play a quick "ping" so the user knows when to start speaking
        self._player.play(PING_AUDIO_PATH)

        with ui.PushToTalkVisualizer():
            audio_path = self._recorder.record()
        
        # ── 1.1 Local Silence Check (save STT API credits) ─────────────────────
        if self._recorder.is_silent(threshold=SILENCE_THRESHOLD):
            logger.info("Local silence detected — skipping STT API call.")
            return _empty

        # ── 2. Transcribe ─────────────────────────────────────────────────────
        with ui.Spinner("Transcribing…"):
            transcript = self._stt.transcribe(audio_path)

        if not self._is_meaningful(transcript):
            logger.info("Meaningless transcription (%r) — skipping LLM call.", transcript)
            # We don't show a warning here because it's usually just background noise
            return _empty

        logger.info("Transcript: %r", transcript)

        # ── 3. Display user input ─────────────────────────────────────────────
        ui.print_divider()
        ui.print_user(transcript)

        with ui.llm_busy():
            # ── 4. Generate LLM response ──────────────────────────────────────
            with ui.Spinner("Thinking…"):
                response_text = self._llm.generate_response(transcript)

            # ── 5. Synthesise TTS (do this BEFORE showing text so they can start together) ──
            with ui.Spinner("Synthesising…"):
                output_audio_path = self._tts.synthesize(response_text)

            # ── 6 & 7. Play audio + UI Response simultaneously ───────────────
            import threading
            player_thread = threading.Thread(target=self._player.play, args=(output_audio_path,))
            player_thread.start()

            # Check current UI mode (toggled via 'V' key)
            if ui.get_ui_mode() == "visual":
                ui.print_visualizer(response_text, char_delay=0.05)
            else:
                ui.print_jarvis_stream(response_text, char_delay=0.05)

        # Wait for audio to finish
        player_thread.join()

        return {
            "transcription": transcript,
            "response": response_text,
            "audio_path": output_audio_path,
            "success": True,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _is_meaningful(text: str) -> bool:
        """
        Return True if the text contains actual speech content.

        Filters out noise that Whisper sometimes transcribes as single
        punctuation marks (e.g. ".", "..") or empty whitespace.
        """
        cleaned = text.strip()
        if not cleaned:
            return False

        # If it's just punctuation/symbols, it's likely background noise.
        # We look for at least one alphanumeric character.
        if not re.search(r"[a-zA-Z0-9]", cleaned):
            return False

        return True

    @staticmethod
    def _is_exit_phrase(text: str, exits: FrozenSet[str]) -> bool:
        """
        Return True if any phrase from *exits* appears in *text*.

        Substring matching is intentional — "goodbye jarvis" correctly
        triggers on both "goodbye" and "goodbye jarvis".
        """
        return any(phrase in text for phrase in exits)

    def __repr__(self) -> str:
        return "<VoiceModule pipeline=record→STT→LLM→TTS→play>"
