"""
app/main.py
===========
Jarvis AI Platform — Entry Point

Boot sequence
-------------
1. Clear the terminal screen.
2. Render the styled header once (ASCII art + GitHub link).
3. Configure logging (file only — zero console noise).
4. Instantiate the Orchestrator and register modules.
5. Show the 'system ready' block.
6. Hand control to the voice module's continuous loop.

Architecture note
-----------------
This file is intentionally thin.  All feature logic lives in modules.
Adding a new capability means one extra `orch.register()` call here —
nothing else in the codebase changes.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

# ── 0. Suppress library noise before any imports ─────────────────────────────
# Hide the "Hello from the pygame community" greeting
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

# Hide the "pkg_resources is deprecated" warning triggered by pygame
warnings.filterwarnings("ignore", category=UserWarning, module="pygame.pkgdata")

# ── Ensure the project root is on sys.path when run as  `python app/main.py` ─
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import logging

from config.settings import EXIT_PHRASES, INTERACTION_MODE, LOG_DIR, LOG_FILE, LOG_LEVEL
from core.orchestrator import BaseModule, Orchestrator
from modules.voice.voice_module import VoiceModule
from modules.chat.chat_module import ChatModule
from utils import ui
from utils.logger import setup_logger
from utils.user_profile import initialize_user_profile

# ═══════════════════════════════════════════════════════════════════════════════
# Orchestrator factory
# ═══════════════════════════════════════════════════════════════════════════════


def build_orchestrator() -> Orchestrator:
    """
    Compose and return a fully-wired Orchestrator.

    This is the single place where modules are registered.
    To add a new feature, import its module class and add one line:
        orch.register(NewModule())

    Returns
    -------
    Orchestrator
        A ready-to-use orchestrator with all modules loaded.
    """
    orch = Orchestrator()

    class _LazyModule(BaseModule):
        def __init__(self, name: str, factory: type[BaseModule]) -> None:
            self._name = name
            self._factory = factory
            self._impl: BaseModule | None = None

        @property
        def name(self) -> str:
            return self._name

        def on_load(self) -> None:
            # Defer real module initialisation until first use so we can
            # toggle modes at runtime without forcing all services to start.
            return

        def on_unload(self) -> None:
            if self._impl is not None:
                self._impl.on_unload()

        def _ensure(self) -> BaseModule:
            if self._impl is None:
                self._impl = self._factory()
                self._impl.on_load()
            return self._impl

        def run(self, **kwargs):  # type: ignore[override]
            return self._ensure().run(**kwargs)

        def run_continuous(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            impl = self._ensure()
            fn = getattr(impl, "run_continuous", None)
            if fn is None:
                raise AttributeError(f"Module {self._name!r} has no run_continuous()")
            return fn(*args, **kwargs)

    # ── Feature modules ───────────────────────────────────────────────────────
    # Register both modes so Alt+Q can switch at runtime.
    orch.register(_LazyModule("chat", ChatModule))
    orch.register(_LazyModule("voice", VoiceModule))

    # Uncomment as new modules are implemented:
    # from modules.automation.automation_module import AutomationModule
    # orch.register(AutomationModule())

    # from modules.memory.memory_module import MemoryModule
    # orch.register(MemoryModule())

    # from modules.browser.browser_module import BrowserModule
    # orch.register(BrowserModule())

    return orch


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    """
    Bootstrap the Jarvis platform and start the voice assistant.

    Exit codes
    ----------
    0  — clean shutdown (user said goodbye or pressed Ctrl-C).
    1  — startup failure (bad config, missing module, etc.).
    """

    # ── 1. Clear screen + render initial UI (before any log output) ──────────
    # Default to the full header at startup; switch to `compact` only if your
    # terminal renders the header/rules poorly.
    ui_layout = os.getenv("JARVIS_UI_LAYOUT", "full").lower().strip()
    ui.clear_screen()
    if ui_layout == "full":
        ui.display_header(github_url="github.com/kaya0s/J.git")

    # ── 2. Configure logging — file only, terminal stays clean ───────────────
    import logging as _logging

    setup_logger(
        level=getattr(_logging, LOG_LEVEL, _logging.INFO),
        log_file=(LOG_DIR / LOG_FILE) if LOG_FILE else None,
    )
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Jarvis platform starting up.")

    # ── 3. Initialize user profile ───────────────────────────────────────────────
    try:
        from utils.user_profile import get_user_profile
        profile = get_user_profile()
        was_setup_needed = not profile.has_name()
        user_name = initialize_user_profile()
        logger.info(f"User profile initialized for: {user_name}")
    except Exception as exc:
        logger.warning("User profile initialization failed: %s", exc)
        ui.print_warning("Could not initialize user profile.")
        was_setup_needed = False

    # ── 4. Build orchestrator (registers + loads all modules) ─────────────────
    try:
        with ui.Spinner("Initialising modules"):
            orchestrator = build_orchestrator()
    except Exception as exc:
        logger.critical("Orchestrator init failed: %s", exc, exc_info=True)
        ui.print_error(f"Startup failed: {exc}")
        sys.exit(1)

    logger.info("Active modules: %s", orchestrator.modules)

    # ── 5. Show system-ready block ────────────────────────────────────────────
    # Show boot info only if setup was needed (return users don't need duplicate header)
    current_mode = INTERACTION_MODE.lower().strip()
    ui.set_interaction_mode(current_mode)
    ui.init_hotkeys()

    if not was_setup_needed:
        if ui_layout == "full":
            ui.print_boot_info(
                modules=[current_mode],
                exit_phrases=EXIT_PHRASES,
                interaction_mode=current_mode,
            )
        else:
            ui.print_status_bar(
                modules=[current_mode],
                exit_phrases=EXIT_PHRASES,
                interaction_mode=current_mode,
            )

    # ── 6/7. Run the selected module (Alt+Q toggles chat/voice at runtime) ────
    while True:
        module_name = "chat" if current_mode == "chat" else "voice"
        module_type = "Chat" if module_name == "chat" else "Voice"

        module = orchestrator.get(module_name)
        if module is None:
            logger.error(f"{module_type} module not registered.")
            ui.print_error(
                f"{module_type} module not found. Check build_orchestrator() in app/main.py."
            )
            sys.exit(1)

        previous_mode = "voice" if current_mode == "chat" else "chat"

        try:
            module.run_continuous()  # type: ignore[attr-defined]
            # If the module returns naturally, it means the user triggered an
            # exit phrase and requested shutdown.
            sys.exit(0)
        except ui.InteractionModeToggle as exc:
            target = getattr(exc, "target", None)
            if target in {"chat", "voice"}:
                current_mode = target
            else:
                current_mode = "voice" if current_mode == "chat" else "chat"
            ui.set_interaction_mode(current_mode)
            ui.consume_key_buffer()
            ui.hard_clear_screen()
            if ui_layout == "full":
                ui.display_header(github_url="github.com/kaya0s/J.git")
                ui.print_boot_info(
                    modules=[current_mode],
                    exit_phrases=EXIT_PHRASES,
                    interaction_mode=current_mode,
                )
            else:
                ui.print_status_bar(
                    modules=[current_mode],
                    exit_phrases=EXIT_PHRASES,
                    interaction_mode=current_mode,
                )
            continue
        except Exception as exc:
            # If a mode was just toggled to and fails to initialise/run,
            # fall back to the previous mode instead of exiting.
            logger.error("Error in %s module: %s", module_type.lower(), exc, exc_info=True)
            ui.print_error(f"{module_type} error: {exc}")
            current_mode = previous_mode
            ui.set_interaction_mode(current_mode)
            ui.consume_key_buffer()
            ui.hard_clear_screen()
            ui.print_status_bar(
                modules=[current_mode],
                exit_phrases=EXIT_PHRASES,
                interaction_mode=current_mode,
            )
            continue

    # ── 8. Clean shutdown ─────────────────────────────────────────────────────
    logger.info("Jarvis platform shut down cleanly.")
    sys.exit(0)


if __name__ == "__main__":
    main()
