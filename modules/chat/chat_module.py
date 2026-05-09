"""
modules/chat/chat_module.py
============================
Chat Interaction Module — Text-only interface for the Jarvis Platform

Pipeline
--------
    Text Input (keyboard) → utils/ui.py (get_user_input with ESC detection)
         │
         ▼
    LLMService             ← services/llm_service.py   (Groq LLaMA-3.1-8b-instant)
         │  (response text)
         ▼
    Text Output           ← utils/ui.py (typewriter/visualizer modes)

Features
--------
* Pure text-based interaction (no voice services)
* ESC key detection for instant quit
* Fast typewriter effect (0.02s delay)
* Visual mode support (V key toggle)
* Exit phrase detection (goodbye, exit, quit, etc.)

Architecture rules
------------------
* Calls services — does NOT implement them
* Inherits from BaseModule — plugs into Orchestrator with zero changes
* All terminal output is routed through utils/ui.py — zero raw print() calls
* All configuration comes from config/settings.py — nothing hardcoded here
* Completely independent of voice services (STT/TTS/Audio are NOT used)
* Uses same LLM service as voice mode for consistent responses
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any, FrozenSet, Optional

from config.settings import EXIT_PHRASES as _SETTINGS_EXIT_PHRASES
from core.orchestrator import BaseModule
from services.llm_service import LLMService
from utils import ui

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exit phrases — loaded from .env / settings.py
# ---------------------------------------------------------------------------

_DEFAULT_EXIT_PHRASES: FrozenSet[str] = frozenset(_SETTINGS_EXIT_PHRASES)

# ---------------------------------------------------------------------------
# Return type for a single chat cycle
# ---------------------------------------------------------------------------

ChatCycleResult = dict[str, Any]
"""
Keys
----
input         : str  — what the user typed  (empty if skipped)
response      : str  — JARVIS text reply   (empty if skipped)
audio_path    : str  — path to the MP3     (always empty - no audio in chat mode)
success       : bool — False when cycle was skipped

Note: audio_path is kept for compatibility with voice module interface but is never used.
"""


class ChatModule(BaseModule):
    """
    Self-contained text-only interaction module for the Jarvis platform.

    Two operation modes
    -------------------
    Single turn  → ``module.run()``
    Continuous   → ``module.run_continuous()``

    Every pipeline stage delegates to a dedicated service.
    All user-facing output goes through ``utils.ui`` — no raw print() here.
    """

    # ── BaseModule contract ───────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "chat"

    def on_load(self) -> None:
        """
        Initialise all services once, immediately after registration.

        Chat mode is text-only - no voice services are initialized.
        """
        logger.info("ChatModule: initialising services…")

        try:
            with ui.Spinner("Initialising chat services…"):
                self._llm: LLMService = LLMService()
                # No voice services in chat mode - text only

        except Exception as exc:
            logger.critical("ChatModule failed to initialise: %s", exc, exc_info=True)
            ui.print_error(f"Failed to initialise chat module: {exc}")
            raise

        logger.info("ChatModule loaded — text-only mode.")

    def on_unload(self) -> None:
        logger.info("ChatModule unloaded.")

    def run(self, **kwargs) -> ChatCycleResult:
        """
        Execute a single input → respond cycle (text-only).
        """
        return self._run_cycle()

    # ── Continuous mode ───────────────────────────────────────────────────────

    def run_continuous(
        self,
        exit_phrases: Optional[FrozenSet[str]] = None,
    ) -> None:
        """
        Run the chat pipeline in an infinite loop.

        Exits cleanly when the user types an exit phrase or presses ESC.
        Errors in a single cycle are caught, displayed, and the loop continues.

        Args:
            exit_phrases : phrases that trigger shutdown (falls back to .env).
        """
        exits = exit_phrases or _DEFAULT_EXIT_PHRASES
        logger.info("ChatModule entering continuous mode.")

        while True:
            try:
                result = self._run_cycle()

                if not result["success"]:
                    continue

                user_input = result["input"].lower().strip()

                if self._is_exit_phrase(user_input, exits):
                    ui.print_goodbye()
                    logger.info("Exit phrase detected — stopping continuous mode.")
                    break

            except ui.InteractionModeToggle:
                raise

            except KeyboardInterrupt:
                ui.print_goodbye()
                logger.info("ChatModule interrupted by user (ESC).")
                break

            except Exception as exc:
                logger.error(
                    "Unhandled error in chat cycle (loop continues): %s",
                    exc,
                    exc_info=True,
                )
                ui.print_error(f"{type(exc).__name__}: {exc}")

        logger.info("ChatModule exited continuous mode.")

    # ── Core pipeline ─────────────────────────────────────────────────────────

    def _run_cycle(self) -> ChatCycleResult:
        """
        One complete input → respond turn (text-only).

        Steps
        -----
        1. Show input prompt  →  get user text input
        2. Spinner  →  LLM response via Groq LLaMA
        3. Typewriter stream of JARVIS response

        Returns
        -------
        ChatCycleResult
        """
        _empty: ChatCycleResult = {
            "input": "",
            "response": "",
            "audio_path": "",
            "success": False,
        }

        # ── 1. Get user input ──────────────────────────────────────────────────
        try:
            user_input = ui.get_user_input()
        except (EOFError, KeyboardInterrupt):
            return _empty

        if not user_input or not user_input.strip():
            return _empty

        cmd = user_input.strip().lower()
        if cmd in {"/mode", "/toggle", "/switch"}:
            raise ui.InteractionModeToggle()
        if cmd in {"/chat", "/voice"}:
            raise ui.InteractionModeToggle(cmd.lstrip("/"))

        logger.info("User input: %r", user_input)

        # ── 2. Display user input ─────────────────────────────────────────────
        ui.print_divider()
        ui.print_user(user_input)

        # ── 3. Generate LLM response ──────────────────────────────────────────
        with ui.llm_busy():
            with ui.Spinner("Thinking…"):
                response_text = self._llm.generate_response(user_input)

            # ── 4. Display JARVIS response (text-only) ───────────────────────
            if ui.get_ui_mode() == "visual":
                ui.print_visualizer(response_text, char_delay=0.02)
            else:
                ui.print_jarvis_stream(response_text, char_delay=0.02)

        return {
            "input": user_input,
            "response": response_text,
            "audio_path": "",  # Always empty in chat mode
            "success": True,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _is_exit_phrase(text: str, exits: FrozenSet[str]) -> bool:
        """
        Return True if any phrase from *exits* appears in *text*.

        Substring matching is intentional — "goodbye jarvis" correctly
        triggers on both "goodbye" and "goodbye jarvis".
        """
        return any(phrase in text for phrase in exits)

    def __repr__(self) -> str:
        return "<ChatModule pipeline=input→LLM→text>"
