"""
services/llm_service.py
=======================
LLM Service — Groq (llama-3.1-8b-instant)

Responsibilities
----------------
* Send user prompts to the Groq Chat Completions API.
* Maintain a rolling multi-turn conversation history for context.
* Retry failed API calls with exponential back-off.
* Remain completely unaware of how the response will be used
  (voice, text, API, etc.) — that is the module's concern.
"""

from __future__ import annotations

import logging
import time
from typing import List

from groq import Groq

from config.settings import (
    GROQ_API_KEY,
    LLM_HISTORY_LIMIT,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_SYSTEM_PROMPT,
    LLM_TEMPERATURE,
    MAX_RETRIES,
    RETRY_DELAY,
)
from utils.user_profile import get_user_profile

logger = logging.getLogger(__name__)

# Type alias for a single chat message dict
Message = dict[str, str]

_DEFAULT_SYSTEM_PROMPT = LLM_SYSTEM_PROMPT


class LLMService:
    """
    Thin, stateful wrapper around the Groq Chat Completions API.

    State
    -----
    Keeps a rolling conversation history so the model has context across
    multiple turns.  History is bounded to ``LLM_HISTORY_LIMIT`` messages
    to stay within context-window limits.

    Usage
    -----
    >>> svc = LLMService()
    >>> reply = svc.generate_response("What is the speed of light?")
    >>> print(reply)

    Override system prompt per-call:
    >>> reply = svc.generate_response("Summarise this.", system_prompt="You are a summariser.")
    """

    def __init__(self, system_prompt: str = _DEFAULT_SYSTEM_PROMPT) -> None:
        self._client: Groq = Groq(api_key=GROQ_API_KEY)
        self._model: str = LLM_MODEL
        self._default_system: str = self._get_personalized_prompt(system_prompt)
        self._history: List[Message] = []

        logger.info("LLMService initialised  (model=%s)", self._model)

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_response(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        """
        Generate an LLM response for *prompt* and update conversation history.

        Args:
            prompt:        The user's input text.
            system_prompt: Optional per-call override of the system instruction.
                           Falls back to the instance-level default when omitted.

        Returns:
            The model's reply as a plain string (stripped of leading/trailing
            whitespace).

        Raises:
            RuntimeError: If all retry attempts are exhausted.
        """
        system = self._get_personalized_prompt(system_prompt or self._default_system)

        # Build the full message list: system → history → new user turn
        messages: List[Message] = [
            {"role": "system", "content": system},
            *self._history,
            {"role": "user", "content": prompt},
        ]

        reply = self._call_with_retry(messages)

        # Persist this exchange in the rolling history
        self._history.append({"role": "user", "content": prompt})
        self._history.append({"role": "assistant", "content": reply})

        # Trim history to stay within the configured window
        if len(self._history) > LLM_HISTORY_LIMIT:
            # Drop the oldest exchange (2 messages) to keep pairs aligned
            self._history = self._history[-LLM_HISTORY_LIMIT:]

        logger.debug(
            "LLM response (%d chars): %.80s…",
            len(reply),
            reply,
        )
        return reply

    def reset_history(self) -> None:
        """
        Clear the conversation history and start a fresh context window.

        Call this between independent sessions so the model is not
        confused by stale context.
        """
        self._history.clear()
        logger.info("Conversation history cleared.")

    @property
    def history(self) -> List[Message]:
        """Read-only view of the current conversation history."""
        return list(self._history)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _call_with_retry(self, messages: List[Message]) -> str:
        """
        Call the Groq API with exponential back-off retry.

        Retry schedule (RETRY_DELAY = 1.0 s):
            Attempt 1 → immediate
            Attempt 2 → wait 1.0 s
            Attempt 3 → wait 2.0 s
            … then raise

        Returns:
            The raw model reply string.

        Raises:
            RuntimeError: After ``MAX_RETRIES`` consecutive failures.
        """
        last_exc: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=LLM_TEMPERATURE,
                    max_tokens=LLM_MAX_TOKENS,
                )
                return response.choices[0].message.content.strip()

            except Exception as exc:
                last_exc = exc
                wait_secs = RETRY_DELAY * attempt
                logger.warning(
                    "LLM API attempt %d/%d failed: %s.  Retrying in %.1f s…",
                    attempt,
                    MAX_RETRIES,
                    exc,
                    wait_secs,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(wait_secs)

        logger.error(
            "LLM API unavailable after %d attempts.  Last error: %s",
            MAX_RETRIES,
            last_exc,
        )
        raise RuntimeError(
            f"LLM API unavailable after {MAX_RETRIES} retries."
        ) from last_exc

    def _get_personalized_prompt(self, base_prompt: str) -> str:
        """
        Get personalized system prompt with user's name if available.
        """
        try:
            user_profile = get_user_profile()
            return user_profile.get_personalized_prompt(base_prompt)
        except Exception as exc:
            logger.warning("Failed to get personalized prompt: %s", exc)
            return base_prompt
