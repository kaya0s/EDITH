"""

config/settings.py

==================

Central configuration for the Jarvis platform.



Every value that can reasonably change between environments or users is

read from the environment (via .env).  Nothing domain-specific is

hardcoded here — change behaviour by editing .env, not source code.



Loading order

-------------

1. System environment variables  (highest priority)

2. .env file in the project root

3. Typed defaults defined below  (fallback / documentation)



Type helpers

------------

_str()   — required string, raises if missing/empty

_opt()   — optional string, returns None if not set

_int()   — integer with default

_float() — float with default

_bool()  — boolean with default  ("true"/"1"/"yes" → True)

"""



from __future__ import annotations



import os

from pathlib import Path



from dotenv import load_dotenv



# ══════════════════════════════════════════════════════════════════════════════

# Path resolution for bundled executables

# ══════════════════════════════════════════════════════════════════════════════



def _get_resource_path(relative_path: Path) -> Path:

    """

    Get absolute path to resource, works for dev and for PyInstaller.

    

    In development, returns the normal path.

    In PyInstaller bundle, returns the path to the bundled resource.

    """

    try:

        # PyInstaller creates a temp folder and stores path in _MEIPASS

        import sys

        base_path = Path(sys._MEIPASS)

    except (AttributeError, ImportError):

        # Running in normal Python environment

        base_path = BASE_DIR
    
    return base_path / relative_path



# ══════════════════════════════════════════════════════════════════════════════

# Directory layout  (these are derived from __file__ — not env-configurable)

# ══════════════════════════════════════════════════════════════════════════════



#: Absolute path to the project root  (…/JARVIS2.0/)

BASE_DIR: Path = Path(__file__).resolve().parent.parent



#: Runtime audio artefacts (input recordings, TTS output)

AUDIO_DIR: Path = BASE_DIR / "audio"



#: Persistent log files

LOG_DIR: Path = BASE_DIR / "logs"



# Guarantee runtime directories exist before anything else runs

AUDIO_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR.mkdir(parents=True, exist_ok=True)



# ══════════════════════════════════════════════════════════════════════════════

# Load .env

# ══════════════════════════════════════════════════════════════════════════════



load_dotenv(BASE_DIR / ".env")



# ══════════════════════════════════════════════════════════════════════════════

# Private type-casting helpers

# ══════════════════════════════════════════════════════════════════════════════





def _str(key: str) -> str:

    """Return a required string env-var.  Raises ``EnvironmentError`` if absent."""

    value = os.getenv(key, "").strip()

    if not value:

        raise EnvironmentError(

            f"\n[Jarvis] ❌  Required environment variable '{key}' is not set.\n"

            "  Steps to fix:\n"

            "    1. Copy  .env.example  →  .env\n"

            "    2. Fill in the missing value.\n"

        )

    return value





def _opt(key: str, default: str | None = None) -> str | None:

    """Return an optional string env-var, or *default* if not set."""

    value = os.getenv(key, "").strip()

    return value if value else default





def _int(key: str, default: int) -> int:

    """Return an integer env-var, falling back to *default*."""

    raw = os.getenv(key, "").strip()

    if not raw:

        return default

    try:

        return int(raw)

    except ValueError:

        raise ValueError(f"[Jarvis] '{key}' must be an integer, got '{raw}'.")





def _float(key: str, default: float) -> float:

    """Return a float env-var, falling back to *default*."""

    raw = os.getenv(key, "").strip()

    if not raw:

        return default

    try:

        return float(raw)

    except ValueError:

        raise ValueError(f"[Jarvis] '{key}' must be a float, got '{raw}'.")





def _bool(key: str, default: bool) -> bool:

    """Return a boolean env-var.  Truthy values: '1', 'true', 'yes' (case-insensitive)."""

    raw = os.getenv(key, "").strip().lower()

    if not raw:

        return default

    if raw in {"1", "true", "yes", "on"}:

        return True

    if raw in {"0", "false", "no", "off"}:

        return False

    raise ValueError(

        f"[Jarvis] '{key}' must be a boolean (true/false/yes/no/1/0), got '{raw}'."

    )





# ══════════════════════════════════════════════════════════════════════════════

# ── API Keys  (required — no defaults possible)

# ══════════════════════════════════════════════════════════════════════════════



#: Groq Cloud API key — used for both LLM and STT endpoints

#: Get yours free at https://console.groq.com/

GROQ_API_KEY: str = _str("GROQ_API_KEY")



# ══════════════════════════════════════════════════════════════════════════════

# ── Model identifiers

# ══════════════════════════════════════════════════════════════════════════════



#: Groq chat/completion model

#: Options: llama-3.1-8b-instant | llama-3.3-70b-versatile | mixtral-8x7b-32768

#: Full list: https://console.groq.com/docs/models

LLM_MODEL: str = _opt("LLM_MODEL") or "llama-3.1-8b-instant"



#: Groq speech-to-text model

#: Options: whisper-large-v3 | whisper-large-v3-turbo | distil-whisper-large-v3-en

STT_MODEL: str = _opt("STT_MODEL") or "whisper-large-v3"



#: Microsoft Edge TTS neural voice

#: Browse all voices: https://github.com/rany2/edge-tts#usage

#: Run `edge-tts --list-voices` for the full catalogue

TTS_VOICE: str = _opt("TTS_VOICE") or "en-US-AriaNeural"



#: Speaking rate adjustment relative to default.

#: Format: +N%  or  -N%  (e.g. "+20%", "-10%", "+0%")

TTS_RATE: str = _opt("TTS_RATE") or "+0%"



#: Pitch adjustment relative to default.

#: Format: +NHz  or  -NHz  (e.g. "+5Hz", "-10Hz", "+0Hz")

TTS_PITCH: str = _opt("TTS_PITCH") or "+0Hz"



#: Volume adjustment relative to default.

#: Format: +N%  or  -N%  (e.g. "+10%", "-10%", "+0%")

TTS_VOLUME: str = _opt("TTS_VOLUME") or "+0%"



# ══════════════════════════════════════════════════════════════════════════════

# ── LLM generation parameters

# ══════════════════════════════════════════════════════════════════════════════



#: Sampling temperature — 0.0 = deterministic, 1.0 = very creative

LLM_TEMPERATURE: float = _float("LLM_TEMPERATURE", 0.7)



#: Hard cap on tokens generated per response

LLM_MAX_TOKENS: int = _int("LLM_MAX_TOKENS", 512)



#: Max chat messages kept in rolling context window (each turn = 2 messages)

LLM_HISTORY_LIMIT: int = _int("LLM_HISTORY_LIMIT", 20)



#: System-level instruction injected at the start of every conversation.

#: Override this to give Jarvis a different persona or set of constraints.

LLM_SYSTEM_PROMPT: str = _opt("LLM_SYSTEM_PROMPT") or (

    "You are Jarvis, a highly intelligent, precise, and helpful AI assistant. "

    "Respond concisely and accurately. "

    "Avoid unnecessary filler phrases like 'Certainly!' or 'Of course!'. "

    "Get straight to the point."

)



# ══════════════════════════════════════════════════════════════════════════════

# ── STT parameters

# ══════════════════════════════════════════════════════════════════════════════



#: BCP-47 language code sent to Whisper.  Empty string = auto-detect.

#: Examples: "en", "tr", "de", "fr", "es"

STT_LANGUAGE: str = _opt("STT_LANGUAGE") or "en"



# ══════════════════════════════════════════════════════════════════════════════

# ── Audio recording parameters

# ══════════════════════════════════════════════════════════════════════════════



#: Microphone sample rate in Hz

#: 44100 = CD quality | 16000 = minimal for speech recognition

SAMPLE_RATE: int = _int("SAMPLE_RATE", 44_100)



#: Key used to trigger Push-To-Talk

PTT_KEY: str = _opt("PTT_KEY") or "space"



#: Number of input channels (1 = mono, 2 = stereo).

#: Mono is recommended — halves file size and is sufficient for speech.

AUDIO_CHANNELS: int = _int("AUDIO_CHANNELS", 1)



#: Sensitivity for local silence detection (RMS volume).

#: Lower = more sensitive (hears quiet sounds).

#: Higher = less sensitive (ignores background noise).

SILENCE_THRESHOLD: float = _float("SILENCE_THRESHOLD", 0.001)



# ══════════════════════════════════════════════════════════════════════════════

# ── Audio file paths

# ══════════════════════════════════════════════════════════════════════════════



#: Where microphone recordings are stored before being sent to STT

INPUT_AUDIO_PATH: str = _opt("INPUT_AUDIO_PATH") or str(_get_resource_path(Path("audio") / "input.wav"))



#: Where TTS synthesis output is stored before playback

OUTPUT_AUDIO_PATH: str = _opt("OUTPUT_AUDIO_PATH") or str(_get_resource_path(Path("audio") / "response.mp3"))



#: Notification sound played before Jarvis starts listening

PING_AUDIO_PATH: str = _opt("PING_AUDIO_PATH") or str(_get_resource_path(Path("audio") / "ping.wav"))



# ══════════════════════════════════════════════════════════════════════════════

# ── Resilience / retry

# ══════════════════════════════════════════════════════════════════════════════



#: Number of times to retry a failed API call before giving up

MAX_RETRIES: int = _int("MAX_RETRIES", 3)



#: Base delay between retry attempts in seconds.

#: Actual delay = RETRY_DELAY × attempt_number  (linear back-off)

RETRY_DELAY: float = _float("RETRY_DELAY", 1.0)



# ══════════════════════════════════════════════════════════════════════════════

# ── Logging

# ══════════════════════════════════════════════════════════════════════════════



#: Root logging level: DEBUG | INFO | WARNING | ERROR | CRITICAL

LOG_LEVEL: str = (_opt("LOG_LEVEL") or "INFO").upper()



#: Log filename written inside the logs/ directory.

#: Set to empty string or "none" to disable file logging (console only).

_raw_log_file = _opt("LOG_FILE") or "jarvis.log"

LOG_FILE: str | None = None if _raw_log_file.lower() in {"", "none"} else _raw_log_file



# ══════════════════════════════════════════════════════════════════════════════

# ── Voice module behaviour

# ══════════════════════════════════════════════════════════════════════════════



#: Comma-separated list of lowercase exit phrases for the continuous voice loop.

#: Example:  EXIT_PHRASES=goodbye,bye,exit,quit

_raw_exits = _opt("EXIT_PHRASES") or ""

EXIT_PHRASES: list[str] = (

    [p.strip() for p in _raw_exits.split(",") if p.strip()]

    if _raw_exits

    else [

        "goodbye jarvis",

        "goodbye",

        "exit",

        "quit",

        "stop",

        "shut down",

        "shutdown",

        "turn off",

        "bye",

    ]

)


# ══════════════════════════════════════════════════════════════════════════════
# ── Interaction mode
# ══════════════════════════════════════════════════════════════════════════════

#: Interaction mode: "voice" for voice input, "chat" for text-only input
#: Options: voice, chat
INTERACTION_MODE: str = _opt("INTERACTION_MODE") or "voice"
