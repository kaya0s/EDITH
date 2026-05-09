"""
utils/ui.py
===========
Terminal presentation layer for the Jarvis platform.

Design goals
------------
* Zero external dependencies — pure ANSI escape codes + Python stdlib.
* Works on Windows Terminal, macOS Terminal, and Linux VTE terminals.
* Non-blocking spinners via daemon threads.
* Typewriter streaming effect for JARVIS responses.
* Single source of truth for every string printed to stdout.
* Keeps ALL print/display logic out of business-logic modules.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
import msvcrt
import random
import math
from contextlib import contextmanager
from typing import Optional, Any

# ══════════════════════════════════════════════════════════════════════════════
# Windows ANSI support (no-op on macOS/Linux where it works natively)
# ══════════════════════════════════════════════════════════════════════════════

if sys.platform == "win32":
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

        # Prefer UTF-8 so box-drawing characters render correctly.
        # (Some hosts still ignore this, but it improves consistency.)
        try:
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        except Exception:
            pass

        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Colour / style constants
# ══════════════════════════════════════════════════════════════════════════════

_COLOR_SUPPORTED: bool = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _e(*codes: str) -> str:
    """Return a composed ANSI escape sequence, or '' when colour is unsupported."""
    return "".join(codes) if _COLOR_SUPPORTED else ""


class C:
    """
    Ready-to-use ANSI colour / style strings.

    Naming convention
    -----------------
    R   = Reset        B   = Bold         D  = Dim      I = Italic
    CY  = Bright Cyan  WH  = Bright White GR = Dark Gray
    YL  = Bright Yellow  RE = Bright Red  BL = Bright Blue
    GN  = Bright Green   MG = Bright Magenta
    """

    R = _e("\033[0m")  # Reset all attributes
    B = _e("\033[1m")  # Bold
    D = _e("\033[2m")  # Dim
    I = _e("\033[3m")  # Italic
    U = _e("\033[4m")  # Underline

    # ── Foreground colours ───────────────────────────────────────────────────
    CY = _e("\033[96m")  # Bright Cyan   — JARVIS accent colour
    WH = _e("\033[97m")  # Bright White  — primary text
    GR = _e("\033[90m")  # Dark Gray     — metadata, hints, dim text
    YL = _e("\033[93m")  # Bright Yellow — listening / active indicator
    RE = _e("\033[91m")  # Bright Red    — errors
    GN = _e("\033[92m")  # Bright Green  — success
    BL = _e("\033[94m")  # Bright Blue   — links
    MG = _e("\033[95m")  # Bright Magenta
    
    # ── Specialized Glow Colors ─────────────────────────────────────────────
    GLOW_1 = _e("\033[38;5;23m")   # Deep Teal (Dim)
    GLOW_2 = _e("\033[38;5;30m")   # Medium Teal
    GLOW_3 = _e("\033[38;5;37m")   # Light Cyan
    GLOW_4 = _e("\033[38;5;44m")   # Bright Aqua
    GLOW_5 = _e("\033[38;5;51m")   # Maximum Glow (White-ish Cyan)


# ══════════════════════════════════════════════════════════════════════════════
# Low-level terminal helpers
# ══════════════════════════════════════════════════════════════════════════════


def _width() -> int:
    """Return the current terminal column width (default 80 if undetectable)."""
    columns = None

    # Windows: ask the console for the visible window width (more reliable than env vars).
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class COORD(ctypes.Structure):
                _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

            class SMALL_RECT(ctypes.Structure):
                _fields_ = [
                    ("Left", wintypes.SHORT),
                    ("Top", wintypes.SHORT),
                    ("Right", wintypes.SHORT),
                    ("Bottom", wintypes.SHORT),
                ]

            class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                _fields_ = [
                    ("dwSize", COORD),
                    ("dwCursorPosition", COORD),
                    ("wAttributes", wintypes.WORD),
                    ("srWindow", SMALL_RECT),
                    ("dwMaximumWindowSize", COORD),
                ]

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            h_out = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            csbi = CONSOLE_SCREEN_BUFFER_INFO()
            if kernel32.GetConsoleScreenBufferInfo(h_out, ctypes.byref(csbi)):
                columns = int(csbi.srWindow.Right) - int(csbi.srWindow.Left) + 1
        except Exception:
            columns = None

    if not columns:
        columns = shutil.get_terminal_size((80, 24)).columns

    # Guard: some hosts report huge widths which causes wrapped "walls" of rule chars.
    columns = max(40, min(int(columns), int(os.getenv("JARVIS_MAX_WIDTH", "200"))))
    return columns


def _write(text: str) -> None:
    """Write *text* to stdout and flush immediately."""
    sys.stdout.write(text)
    sys.stdout.flush()


def _clear_line() -> None:
    """Erase the current terminal line and return cursor to column 0."""
    _write("\033[2K\r")


def _move_up(lines: int = 1) -> None:
    """Move the cursor up *lines* rows."""
    _write(f"\033[{lines}A")


def _move_down(lines: int = 1) -> None:
    """Move the cursor down *lines* rows."""
    _write(f"\033[{lines}B")


def _hide_cursor() -> None:
    if _COLOR_SUPPORTED:
        _write("\033[?25l")


def _show_cursor() -> None:
    if _COLOR_SUPPORTED:
        _write("\033[?25h")


def clear_screen() -> None:
    """Clear the screen but preserve the JARVIS header design."""
    global _sticky_header_shown

    # Clear the entire screen.
    _write("\033[2J")   # Clear screen
    _write("\033[H")    # Move cursor to home
    sys.stdout.flush()

    # If a sticky header/status is active, redraw it immediately.
    if _sticky_header_shown and _last_boot_info:
        if _last_header_url:
            display_header(github_url=_last_header_url)
            print_boot_info(**_last_boot_info)  # type: ignore[arg-type]
        else:
            print_status_bar(
                modules=_last_boot_info["modules"],
                exit_phrases=_last_boot_info["exit_phrases"],
                interaction_mode=_last_boot_info["interaction_mode"],
                welcome_message=_last_boot_info["welcome_message"],
                sticky=_last_boot_info["sticky"],
            )


def hard_clear_screen() -> None:
    """
    Clear the terminal viewport + scrollback (where supported).

    Use sparingly (e.g., after one-time setup) so onboarding text + user input
    doesn't remain visible above the live session UI.
    """
    global _sticky_header_shown, _last_header_url, _last_boot_info

    # On Windows, ANSI clear sequences aren't always enough (depends on host).
    # Use the Win32 console API when available, then fall back to ANSI.
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class COORD(ctypes.Structure):
                _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

            class SMALL_RECT(ctypes.Structure):
                _fields_ = [
                    ("Left", wintypes.SHORT),
                    ("Top", wintypes.SHORT),
                    ("Right", wintypes.SHORT),
                    ("Bottom", wintypes.SHORT),
                ]

            class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                _fields_ = [
                    ("dwSize", COORD),
                    ("dwCursorPosition", COORD),
                    ("wAttributes", wintypes.WORD),
                    ("srWindow", SMALL_RECT),
                    ("dwMaximumWindowSize", COORD),
                ]

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            h_out = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            csbi = CONSOLE_SCREEN_BUFFER_INFO()
            if kernel32.GetConsoleScreenBufferInfo(h_out, ctypes.byref(csbi)):
                cell_count = int(csbi.dwSize.X) * int(csbi.dwSize.Y)
                written = wintypes.DWORD(0)
                home = COORD(0, 0)
                kernel32.FillConsoleOutputCharacterW(h_out, " ", cell_count, home, ctypes.byref(written))
                kernel32.FillConsoleOutputAttribute(h_out, csbi.wAttributes, cell_count, home, ctypes.byref(written))
                kernel32.SetConsoleCursorPosition(h_out, home)
        except Exception:
            pass

    _write("\033[3J")  # Clear scrollback (xterm / Windows Terminal)
    _write("\033[2J")  # Clear screen
    _write("\033[H")   # Cursor home
    sys.stdout.flush()

    _sticky_header_shown = False
    _last_header_url = None
    _last_boot_info = None


_current_audio_level: float = 0.0
_sticky_header_shown: bool = False
_last_header_url: Optional[str] = None
_last_boot_info: Optional[dict[str, Any]] = None
_interaction_mode: str = "voice"
_llm_busy: bool = False
_toggle_requested: Optional[str] = None
_hotkeys_initialised: bool = False


class InteractionModeToggle(Exception):
    """Raised to request switching between chat and voice modes."""

    def __init__(self, target: Optional[str] = None) -> None:
        super().__init__(target or "")
        self.target = (target or "").lower().strip() or None


def request_mode_toggle(target: Optional[str] = None) -> None:
    """
    Request switching interaction mode.

    This is safe to call from background hotkey callbacks.
    """
    global _toggle_requested
    _toggle_requested = (target or "").lower().strip() or None


def consume_mode_toggle_request() -> Optional[str]:
    """Return and clear any pending mode-toggle request."""
    global _toggle_requested
    value = _toggle_requested
    _toggle_requested = None
    return value


def init_hotkeys() -> None:
    """
    Best-effort global hotkeys (Windows only).

    Alt key combos are inconsistently delivered to console stdin across hosts
    (Windows Terminal / VSCode / conhost). When the optional `keyboard` package
    is available, we register hotkeys that reliably trigger mode switching.
    """
    global _hotkeys_initialised
    if _hotkeys_initialised or sys.platform != "win32":
        return

    _hotkeys_initialised = True
    try:
        import keyboard  # type: ignore

        keyboard.add_hotkey("alt+q", lambda: (not is_llm_busy()) and request_mode_toggle())
        keyboard.add_hotkey("ctrl+q", lambda: (not is_llm_busy()) and request_mode_toggle())
        keyboard.add_hotkey("alt+c", lambda: (not is_llm_busy()) and request_mode_toggle("chat"))
        keyboard.add_hotkey("alt+v", lambda: (not is_llm_busy()) and request_mode_toggle("voice"))
    except Exception:
        # Hotkeys are optional — stdin detection still handles some consoles.
        pass


def set_interaction_mode(mode: str) -> None:
    global _interaction_mode
    _interaction_mode = (mode or "voice").lower().strip()


def get_interaction_mode() -> str:
    return _interaction_mode


@contextmanager
def llm_busy() -> Any:
    """Disable mode-toggling hotkeys while an LLM response is in progress."""
    global _llm_busy
    prev = _llm_busy
    _llm_busy = True
    try:
        yield
    finally:
        _llm_busy = prev
        # Requirement: toggles are disabled during responses; discard any
        # queued requests and drain key buffers so they don't fire afterwards.
        while consume_mode_toggle_request() is not None:
            pass
        consume_key_buffer()


def is_llm_busy() -> bool:
    return _llm_busy


def consume_key_buffer() -> None:
    """Drain any pending console key events (Windows only)."""
    if sys.platform != "win32":
        return
    try:
        while msvcrt.kbhit():
            msvcrt.getch()
    except Exception:
        pass

def set_audio_level(level: float) -> None:
    global _current_audio_level
    _current_audio_level = level

# ══════════════════════════════════════════════════════════════════════════════
# Non-blocking spinner
# ══════════════════════════════════════════════════════════════════════════════


class Spinner:
    """
    A lightweight, non-blocking terminal spinner that runs in a daemon thread.

    The spinner writes to — and continuously overwrites — a single terminal
    line using ``\\r``.  When stopped, it erases that line so the next write
    appears cleanly in its place.

    Usage (context manager — recommended)
    --------------------------------------
    ::

        with Spinner("Transcribing"):
            text = stt.transcribe(audio_path)

    Usage (manual)
    ---------------
    ::

        sp = Spinner("Thinking", color=C.MG)
        sp.start()
        response = llm.generate_response(prompt)
        sp.stop()

    Parameters
    ----------
    message : str
        Label shown next to the spinner frame (e.g. ``"Thinking…"``).
    color   : str
        ANSI colour applied to the spinner frame character.  Defaults to
        ``C.CY`` (bright cyan).
    interval : float
        Seconds between frame updates.  Default ``0.08`` ≈ 12 fps.
    """

    # Braille dot animation — smooth and lightweight
    _FRAMES: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(
        self,
        message: str,
        color: str = "",
        interval: float = 0.08,
    ) -> None:
        self._message = message
        self._color = color or C.CY
        self._interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ── Context-manager interface ─────────────────────────────────────────────

    def __enter__(self) -> "Spinner":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the spinner animation in a background daemon thread."""
        _hide_cursor()
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the animation and erase the spinner line."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        _clear_line()
        _show_cursor()

    # ── Private ───────────────────────────────────────────────────────────────

    def _spin(self) -> None:
        idx = 0
        while self._running:
            frame = self._FRAMES[idx % len(self._FRAMES)]
            _write(f"\r  {self._color}{frame}{C.R}  {C.GR}{self._message}{C.R}")
            time.sleep(self._interval)
            idx += 1


def print_hold_space_prompt() -> None:
    _write(f"\r  {C.YL}●{C.R}  {C.D}Hold {C.R}{C.WH}{C.B}[SPACE]{C.R}{C.D} to speak…{C.R}\033[K")

def clear_prompt() -> None:
    _clear_line()

class PushToTalkVisualizer:
    """
    A non-blocking visualizer shown while the user holds Space to record.
    """

    def __init__(self) -> None:
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def __enter__(self) -> "PushToTalkVisualizer":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def start(self) -> None:
        _hide_cursor()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.2)
        _clear_line()
        _show_cursor()

    def _run(self) -> None:
        while self._running:
            if get_ui_mode() == "visual":
                global _current_audio_level
                amp = min(1.0, _current_audio_level * 10)
                bar_width = 4 + int(36 * amp)
                bar = '━' * bar_width
                _write(f"\r  {C.WH}{C.B}You{C.R}     {C.D}›{C.R}  \033[K{C.GLOW_4}{bar:^40}{C.R}")
            else:
                _write(f"\r  {C.YL}●{C.R}  {C.GN}Listening...{C.R}\033[K")

            time.sleep(0.05)


class KeyboardListener:
    """
    Background thread that listens for UI toggle keys (Windows only).
    """
    def __init__(self) -> None:
        self.mode = "typewriter"
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._running:
            if msvcrt.kbhit():
                try:
                    key = msvcrt.getch().decode('utf-8').lower()
                    if key == 'v':
                        self.mode = "visual" if self.mode == "typewriter" else "typewriter"
                except Exception:
                    pass
            time.sleep(0.1)

# Global listener instance
_listener = KeyboardListener()
_listener.start()


def get_ui_mode() -> str:
    return _listener.mode


# ══════════════════════════════════════════════════════════════════════════════
# ASCII art header
# ══════════════════════════════════════════════════════════════════════════════

# Block-letter JARVIS — 46 chars wide on each line
_ASCII_JARVIS: tuple[str, ...] = (
    "     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗",
    "     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝",
    "     ██║███████║██████╔╝██║   ██║██║███████╗",
    "██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║",
    "╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║",
    " ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝",
)

_ASCII_JARVIS_ASCII: tuple[str, ...] = (
    "     JJJJJ  AAAA  RRRR   V   V  IIIII  SSSS ",
    "       J   A   A  R   R  V   V    I    S    ",
    "       J   AAAAA  RRRR   V   V    I    SSS  ",
    "   J   J   A   A  R  R    V V     I       S ",
    "    JJJ    A   A  R   R    V    IIIII  SSSS ",
)


def _unicode_ui() -> bool:
    """
    Return True when it's safe/desirable to use Unicode UI glyphs.

    If `JARVIS_UNICODE_UI` is explicitly set, it wins.
    Otherwise prefer Unicode whenever stdout is UTF-8, and fall back to ASCII
    when the encoding is unknown/non-UTF-8 (to avoid mojibake).
    """
    if os.getenv("JARVIS_ASCII_UI") == "1":
        return False

    forced = os.getenv("JARVIS_UNICODE_UI")
    if forced is not None:
        return forced == "1"

    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return encoding in ("utf-8", "utf_8")


def _rule(char: str = "─") -> None:
    """Print a full-width horizontal rule in dim cyan."""
    w = _width()
    # Default to ASCII rules on Windows because many hosts/fonts render
    # box-drawing characters incorrectly (e.g., as '₰' or CJK glyphs).
    # Override with `JARVIS_UNICODE_UI=1` if your terminal renders them cleanly.
    if os.getenv("JARVIS_ASCII_UI") == "1" or (
        sys.platform == "win32" and os.getenv("JARVIS_UNICODE_UI") != "1"
    ):
        char = "-"
    elif (getattr(sys.stdout, "encoding", "") or "").lower() not in ("utf-8", "utf_8"):
        # If stdout isn't UTF-8, avoid non-ASCII rule chars to prevent mojibake.
        char = "-"
    _write(f"{C.D}{C.CY}{char * w}{C.R}\n")


def _centre(text: str, style: str = "") -> None:
    """Print *text* centred to the current terminal width."""
    w = _width()
    _write(f"{style}{text.center(w)}{C.R}\n")


def display_header(
    github_url: str = "github.com/kaya0s/J.git",
) -> None:
    """
    Render the styled Jarvis header.

    Call this **once** at application startup after clearing the screen.

    Parameters
    ----------
    github_url : str
        Repository URL shown beneath the ASCII art.
    """
    art = _ASCII_JARVIS if _unicode_ui() else _ASCII_JARVIS_ASCII
    art_width = max((len(line) for line in art), default=0)

    w = _width()
    pad = " " * max(0, (w - art_width) // 2)

    global _last_header_url
    _last_header_url = github_url

    _write("\n")
    _rule("─")
    _write("\n")

    # ── ASCII art — horizontally centred ──────────────────────────────────────
    for line in art:
        _write(f"{pad}{C.CY}{C.B}{line}{C.R}\n")

    _write("\n")

    # ── Subtitle + GitHub link ────────────────────────────────────────────────
    _centre("Modular AI Platform  ·  Voice Assistant", C.GR)
    _centre(github_url, C.D + C.GR)

    _write("\n")
    _rule("─")
    _write("\n")


# ══════════════════════════════════════════════════════════════════════════════
# Boot / status messages
# ══════════════════════════════════════════════════════════════════════════════


def print_boot_info(modules: list[str], exit_phrases: list[str], interaction_mode: str = "voice", sticky: bool = True, welcome_message: Optional[str] = None, show_divider: bool = True) -> None:
    """Display a compact system status line."""
    global _sticky_header_shown
    
    mod_str = " + ".join(f"{C.CY}{m}{C.R}" for m in modules)
    exits = ", ".join(sorted(exit_phrases)[:2])
    
    # Get user's name for personalized welcome
    user_name = None
    try:
        from utils.user_profile import get_user_profile
        profile = get_user_profile()
        user_name = profile.get_name()
    except Exception:
        pass
    
    # Show mode-specific instructions
    if interaction_mode.lower() == "chat":
        mode_text = f"{C.GN}CHAT MODE{C.R}"
    else:
        mode_text = f"{C.YL}VOICE MODE{C.R}"
    
    # Determine welcome message
    if welcome_message:
        welcome_text = welcome_message
    elif user_name and user_name != "User":
        welcome_text = f"Welcome back, {user_name}!"
    else:
        welcome_text = "Welcome to Jarvis!"
    
    global _last_boot_info
    _last_boot_info = {
        "modules": modules,
        "exit_phrases": exit_phrases,
        "interaction_mode": interaction_mode,
        "sticky": sticky,
        "welcome_message": welcome_message,
        "show_divider": show_divider,
    }

    bullet = "●" if _unicode_ui() else "*"
    sep = "»" if _unicode_ui() else ">"

    # Display status lines (the header art is rendered by `display_header()`).
    _write(f"  {C.GN}{bullet} {C.R}{C.B}JARVIS ONLINE{C.R} {C.D}{sep}{C.R} {C.WH}{welcome_text}{C.R} {C.D}{sep}{C.R} {mod_str} {C.D}|{C.R} {mode_text} {C.D}|{C.R} {C.GR}Ctrl+Q:Mode{C.R} {C.D}|{C.R} {C.GR}V:Visual{C.R} {C.D}|{C.R} {C.GR}ESC:Quit{C.R}\n")
    _write(f"  {C.D}Stop phrases: {exits}, ...{C.R}\n")
    _write("\n")

    if show_divider:
        _rule("─")
        _write("\n")

    if sticky:
        _sticky_header_shown = True

    return


def print_status_bar(
    modules: list[str],
    exit_phrases: list[str],
    interaction_mode: str = "voice",
    welcome_message: Optional[str] = None,
    sticky: bool = True,
) -> None:
    """
    Render the compact status bar layout (top rule + status lines + bottom rule).

    Intended for the post-setup UX (no big ASCII header).
    """
    global _last_header_url
    _last_header_url = None

    _rule("─")
    _write("\n")
    print_boot_info(
        modules=modules,
        exit_phrases=exit_phrases,
        interaction_mode=interaction_mode,
        sticky=sticky,
        welcome_message=welcome_message,
        show_divider=True,
    )
    _write("\n")
    return


def print_system(msg: str) -> None:
    """Print a faint informational / status line (startup messages, etc.)."""
    _write(f"  {C.GR}{msg}{C.R}\n")


# ══════════════════════════════════════════════════════════════════════════════
# Per-turn conversation display
# ══════════════════════════════════════════════════════════════════════════════

# Column widths — keep labels aligned
_USER_LABEL = "  You     ›  "  # 14 chars
_JARVIS_LABEL = "  JARVIS  ›  "  # 14 chars
_INDENT = " " * 14  # continuation-line indent


def print_divider() -> None:
    """Print a subtle dotted divider between conversation turns."""
    if os.getenv("JARVIS_SHOW_DIVIDER", "0") != "1":
        return
    w = _width()
    _write(f"\n  {C.GR}{'_' * (w - 4)}{C.R}\n\n")


def print_user(text: str) -> None:
    """
    Display the transcribed user input with the appropriate label.

    Parameters
    ----------
    text : str
        The transcribed speech text.
    """
    # Get user's name for personalized label
    user_label = _get_user_label()
    caret = "›" if _unicode_ui() else ">"
    
    if get_ui_mode() == "visual":
        _write(f"\n  {C.WH}{C.B}{user_label}{C.R}     {C.D}{caret}{C.R}  {C.GLOW_3}{'━' * 20:^40}{C.R}\n\n")
        return
    _write(f"\n  {C.WH}{C.B}{user_label}{C.R}     {C.D}{caret}{C.R}  {C.WH}{text}{C.R}\n\n")


def print_jarvis_stream(
    text: str,
    char_delay: float = 0.014,
) -> None:
    """
    Stream JARVIS's response with a typewriter character-by-character effect.

    Wrapping always occurs at word boundaries — words are never split across
    lines.  Explicit newlines in *text* are honoured and continuation lines
    are indented to align with the JARVIS label column.

    Parameters
    ----------
    text       : str
        The full response text to stream.
    char_delay : float
        Seconds between each character.  Set to ``0`` for instant output.
        Default ``0.014`` ≈ ~70 chars/second — readable but not sluggish.
    """
    w = _width()

    # Print the JARVIS label first
    _write(f"  {C.CY}{C.B}JARVIS{C.R}  {C.D}›{C.R}  ")

    col = len(_JARVIS_LABEL)  # tracks current column (ANSI codes ignored)
    char_count = 0

    # Split into alternating [word, whitespace, word, whitespace, …] tokens
    # so we can make wrap decisions at word boundaries, never mid-word.
    tokens = re.split(r"(\s+)", text)

    for token in tokens:
        if not token:
            continue

        # ── Explicit newline embedded in the text ─────────────────────────────
        if "\n" in token:
            _write(f"\n{_INDENT}")
            col = len(_INDENT)
            continue

        # ── Whitespace token (the space(s) between words) ─────────────────────
        if token.isspace():
            if col + 1 >= w - 1:
                # At the edge — absorb the space and wrap instead
                _write(f"\n{_INDENT}")
                col = len(_INDENT)
            else:
                _write(C.WH + " " + C.R)
                col += 1
                if char_delay:
                    time.sleep(char_delay)
            continue

        # ── Word token — never break mid-word ─────────────────────────────────
        word_len = len(token)

        # If the word won't fit on the current line (and we are not already
        # at the start of the indent), wrap before printing it.
        if col + word_len > w - 1 and col > len(_INDENT):
            _write(f"\n{_INDENT}")
            col = len(_INDENT)

        for ch in token:
            _write(C.WH + ch + C.R)
            col += 1
            char_count += 1

            # Flush every 4 chars to reduce syscall overhead while keeping
            # the streaming animation smooth.
            if char_delay and char_count % 4 == 0:
                sys.stdout.flush()

            if char_delay:
                time.sleep(char_delay)

    _write("\n\n")
    sys.stdout.flush()


def print_visualizer(text: str, char_delay: float = 0.05) -> None:
    """
    Display a glowing, pulsing waveform visualizer instead of the typewriter.
    The duration is estimated based on the text length and char_delay.
    """
    duration = len(text) * char_delay
    start_time = time.time()
    
    _hide_cursor()
    try:
        while time.time() - start_time < duration:
            t = time.time() * 10
            amplitude = abs(math.sin(t) * math.cos(t * 0.5))
            bar_width = 4 + int(36 * amplitude)
            bar = '━' * bar_width
            _write(f"\r  {C.CY}{C.B}JARVIS{C.R}  {C.D}›{C.R}  \033[K{C.GLOW_5}{bar:^40}{C.R}")
            time.sleep(0.05)
    finally:
        _write(f"\r  {C.CY}{C.B}JARVIS{C.R}  {C.D}›{C.R}  \033[K{C.GLOW_3}{'━' * 20:^40}{C.R}\n\n")
        _show_cursor()


# ══════════════════════════════════════════════════════════════════════════════
# Error / warning display
# ══════════════════════════════════════════════════════════════════════════════


def print_error(msg: str) -> None:
    """Display a formatted error message in red."""
    _write(f"\n  {C.RE}✗{C.R}  {C.RE}{msg}{C.R}\n\n")


def print_warning(msg: str) -> None:
    """Display a formatted warning message in yellow."""
    _write(f"  {C.YL}⚠{C.R}  {C.GR}{msg}{C.R}\n\n")


# ══════════════════════════════════════════════════════════════════════════════
# Shutdown
# ══════════════════════════════════════════════════════════════════════════════


def get_user_input() -> str:
    """
    Get user input from the keyboard with a styled prompt.
    ESC key triggers KeyboardInterrupt for quitting.
    
    Returns
    -------
    str
        The user's input text (may be empty).
    """
    # Get user's name for personalized label
    user_label = _get_user_label()
    caret = "›" if _unicode_ui() else ">"
    _write(f"  {C.WH}{C.B}{user_label}{C.R}     {C.D}{caret}{C.R}  ")
    _show_cursor()
    init_hotkeys()
    
    try:
        user_input = _get_input_with_esc_detection()

        # Remove the raw prompt+echo line so the user's input only appears once
        # in the formatted conversation log (via `print_user()`).
        try:
            _move_up(1)
            _clear_line()
            _move_down(1)
            _write("\r")
        except Exception:
            pass

        return user_input.strip()
    except (EOFError, KeyboardInterrupt):
        _write("\n")
        raise


def _get_input_with_esc_detection() -> str:
    """
    Get input with ESC key detection on Windows.
    Returns the entered text, raises KeyboardInterrupt on ESC.
    """
    if sys.platform == "win32":
        result = []
        while True:
            pending = consume_mode_toggle_request()
            if pending is not None and not is_llm_busy():
                raise InteractionModeToggle(pending)

            if msvcrt.kbhit():
                char = msvcrt.getch()

                # Extended keys (arrows, function keys, Alt+ combos, etc.)
                if char in (b"\x00", b"\xe0"):
                    code = msvcrt.getch()
                    # Alt+Q toggles interaction mode (scan code 0x10 in most console hosts).
                    if code == b"\x10" and not is_llm_busy():
                        raise InteractionModeToggle()
                    continue

                # ESC / Alt-modified keys
                # Many terminals send Alt+<key> as ESC + <key>. We treat ESC+Q as the
                # mode toggle, otherwise ESC alone quits.
                if char == b"\x1b":
                    if msvcrt.kbhit():
                        nxt = msvcrt.getch()

                        # Alt+Q often arrives as ESC + 'q'
                        if nxt in (b"q", b"Q") and not is_llm_busy():
                            raise InteractionModeToggle()

                        # Some hosts send ESC + 0x00/0xE0 + scan-code for Alt+ combos
                        if nxt in (b"\x00", b"\xe0"):
                            code = msvcrt.getch()
                            if code == b"\x10" and not is_llm_busy():
                                raise InteractionModeToggle()
                            continue

                        # Not our hotkey — swallow the sequence and treat as ESC quit

                    raise KeyboardInterrupt()
                
                # Handle Enter key
                if char == b'\r' or char == b'\n':
                    break

                # Fallback: Ctrl+Q (some terminals intercept Alt+ combos)
                if char == b"\x11" and not is_llm_busy():
                    raise InteractionModeToggle()
                
                # Handle backspace
                if char == b'\x08':  # Backspace
                    if result:
                        result.pop()
                        _write("\b \b")  # Erase character
                        sys.stdout.flush()
                    continue
                
                # Handle regular characters
                try:
                    decoded = char.decode('utf-8')
                    if decoded.isprintable():
                        result.append(decoded)
                        _write(decoded)
                        sys.stdout.flush()
                except UnicodeDecodeError:
                    pass
            else:
                time.sleep(0.01)
        
        _write("\n")
        return ''.join(result)
    else:
        # Fallback to regular input for non-Windows systems
        return input()


def _get_user_label() -> str:
    """
    Get the appropriate user label based on profile configuration.
    Returns user's name if configured, otherwise 'user'.
    """
    try:
        from utils.user_profile import get_user_profile
        profile = get_user_profile()
        user_name = profile.get_name()
        if user_name and user_name.strip():
            return user_name.strip()
    except Exception:
        pass
    return "user"


def preserve_sticky_header() -> None:
    """Ensure the sticky header is visible at the top."""
    global _sticky_header_shown
    if _sticky_header_shown:
        # Don't clear screen, just ensure header tracking is active
        try:
            from config.settings import EXIT_PHRASES
            from utils.user_profile import get_user_profile
            profile = get_user_profile()
            user_name = profile.get_name()
            
            # Determine welcome message for sticky header
            if user_name and user_name != "User":
                welcome_msg = f"Welcome back, {user_name}!"
            else:
                welcome_msg = "Welcome to Jarvis!"
            
            # Redraw header without clearing screen
            _write("\033[1;0H")  # Move to top line
            print_boot_info(
                modules=[get_interaction_mode()],
                exit_phrases=EXIT_PHRASES,
                interaction_mode=get_interaction_mode(),
                welcome_message=welcome_msg,
                sticky=True,
                show_divider=True
            )
        except Exception:
            pass


def print_goodbye() -> None:
    """Display the shutdown footer."""
    w = _width()
    _write("\n")
    _centre("JARVIS is offline.  Goodbye.", C.GR)
    _write("\n")
