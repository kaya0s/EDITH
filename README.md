# EDITH — Modular AI Platform

> A scalable, extensible AI assistant platform designed to grow beyond voice.
> Voice interaction is **Feature #1** — not the whole system.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [Quick Start](#-quick-start)
- [Environment Setup](#-environment-setup)
- [Running the Voice Module](#-running-the-voice-module)
- [How to Add New Modules](#-how-to-add-new-modules)
- [Services Reference](#-services-reference)
- [Audio Layer](#-audio-layer)
- [Configuration Reference](#-configuration-reference)
- [Dependencies](#-dependencies)
- [Roadmap](#-roadmap)

---

## 🌐 Overview

Edith is a **modular AI assistant platform** built for extensibility. The architecture is designed from day one to support multiple independent features — voice, automation, memory, browser control, smart home, and more — without ever rewriting the core.

The system is built around three principles:

| Principle | Meaning |
|-----------|---------|
| **Modularity** | Every feature is an isolated, plug-and-play module |
| **Separation of Concerns** | Services, audio I/O, config, and feature logic are fully decoupled |
| **Future-Readiness** | New capabilities slot in without touching existing code |

### Feature #1 — Voice Assistant

The first module implements a full speech-to-speech pipeline:

```
Microphone → Groq Whisper (STT) → LLaMA 3.1 8B (LLM) → Edge TTS → Speaker
```

---

## 🧱 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      app/main.py                        │
│              (entry point — boots platform)             │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              core/orchestrator.py                       │
│   Central brain — module registry + execution router    │
│   Knows NOTHING about voice, LLMs, or any feature       │
└──────┬──────────────┬───────────────┬───────────────────┘
       │              │               │
       ▼              ▼               ▼
  [voice]       [automation]      [memory]     ← future modules
  module         module            module
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│           modules/voice/voice_module.py                 │
│   Orchestrates the pipeline — calls services only       │
└──────┬──────────┬──────────────┬───────────────────────┘
       │          │              │
       ▼          ▼              ▼
  STTService  LLMService    TTSService
  (Whisper)   (LLaMA 3.1)   (Edge TTS)
       │                        │
       ▼                        ▼
  AudioRecorder            AudioPlayer
  (sounddevice)            (pygame / OS)
```

### Layer Responsibilities

| Layer | Path | Responsibility |
|-------|------|----------------|
| **Entry Point** | `app/main.py` | Boot sequence, module registration |
| **Orchestrator** | `core/orchestrator.py` | Module lifecycle, routing, registry |
| **Modules** | `modules/*/` | Feature logic — assembles services into pipelines |
| **Services** | `services/` | Reusable, stateless API wrappers |
| **Audio** | `audio/` | Hardware I/O — microphone recording and playback |
| **Config** | `config/settings.py` | All constants, env vars, paths in one place |
| **Utils** | `utils/` | Shared helpers (logging, etc.) |

---

## 📁 Project Structure

```
Edith2.0/
│
├── app/
│   ├── __init__.py
│   └── main.py                  # ← run this to start Edith
│
├── core/
│   ├── __init__.py
│   └── orchestrator.py          # Central brain (module registry + router)
│
├── modules/                     # ← add new features here
│   ├── __init__.py
│   └── voice/
│       ├── __init__.py
│       └── voice_module.py      # Feature #1: speech ↔ LLM pipeline
│
├── services/                    # Reusable API wrappers
│   ├── __init__.py
│   ├── llm_service.py           # Groq LLaMA 3.1 8B Instant
│   ├── stt_service.py           # Groq Whisper-large-v3
│   └── tts_service.py           # Edge TTS (en-US-AriaNeural)
│
├── audio/                       # Hardware I/O
│   ├── __init__.py
│   ├── recorder.py              # Microphone → WAV
│   └── player.py                # MP3/WAV → Speaker
│
├── config/
│   ├── __init__.py
│   └── settings.py              # All env vars, model names, paths, constants
│
├── utils/
│   ├── __init__.py
│   └── logger.py                # Centralised logging setup
│
├── logs/                        # Runtime log files (auto-created)
│   └── Edith.log
│
├── audio/                       # Runtime audio artefacts (auto-created)
│   ├── input.wav                # Microphone recording (overwritten each cycle)
│   └── response.mp3             # TTS output (overwritten each cycle)
│
├── .env                         # ← your secrets (never commit this)
├── .env.example                 # Template for .env
├── requirements.txt
└── README.md
```

---

## 🚀 Quick Start

### 1. Clone / download the project

```bash
cd Edith2.0
```

### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up your environment variables

```bash
cp .env.example .env
# Now open .env and paste your Groq API key
```

### 5. Run Edith

```bash
python app/main.py
```

---

## ⚙️ Environment Setup

### Get a Groq API Key

1. Visit [https://console.groq.com/](https://console.groq.com/)
2. Create a free account
3. Navigate to **API Keys** → **Create API Key**
4. Copy the key

### Configure `.env`

```env
GROQ_API_KEY=gsk_your_actual_key_here
```

> ⚠️ **Never commit your `.env` file.** It is listed in `.gitignore` by default.

### What `settings.py` loads

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | *(required)* | Your Groq API key |
| `LLM_MODEL` | `llama-3.1-8b-instant` | Groq chat model |
| `STT_MODEL` | `whisper-large-v3` | Groq transcription model |
| `TTS_VOICE` | `en-US-AriaNeural` | Edge TTS neural voice |

| `MAX_RETRIES` | `3` | API retry attempts |
| `RETRY_DELAY` | `1.0` | Base delay between retries (seconds) |

---

## 🎤 Running the Voice Module

Once the environment is configured:

```bash
python app/main.py
```

You will see:

```
╔══════════════════════════════════════════════════════════════╗
║         🤖  Edith — Modular AI Platform  🤖                 ║
╚══════════════════════════════════════════════════════════════╝

✅  Voice module initialised — all services online.

╔══════════════════════════════════════════════════════════╗
║       🤖  Edith Voice Assistant  —  Listening Active    ║
╠══════════════════════════════════════════════════════════╣
║  Exit phrases : bye / exit / goodbye / quit / …          ║
║  Press        : Ctrl-C to quit immediately               ║
╚══════════════════════════════════════════════════════════╝

┌────────────────────────────────────────────────────┐
│  ●  Hold [SPACE] to speak…                         │
└────────────────────────────────────────────────────┘

🧠  Transcribing…
📝  You said : What is the capital of France?

💬  Thinking…
🤖  Edith    : The capital of France is Paris.

🔈  Synthesising speech…
🔊  Playing response…
```

### Stopping Edith

Say any of these phrases:
- `"goodbye"` / `"goodbye Edith"`
- `"exit"` / `"quit"` / `"stop"`
- `"shut down"` / `"turn off"`
- `"bye"`

Or press **Ctrl-C** at any time.



## 🔌 How to Add New Modules

Adding a new capability to Edith requires **three steps** and touches **zero existing files** (except `app/main.py` for registration).

### Step 1 — Create the module file

```
modules/
└── automation/
    ├── __init__.py
    └── automation_module.py     ← your new file
```

### Step 2 — Implement `BaseModule`

```python
# modules/automation/automation_module.py

from core.orchestrator import BaseModule

class AutomationModule(BaseModule):

    @property
    def name(self) -> str:
        return "automation"           # unique lowercase ID

    def on_load(self) -> None:
        print("✅  Automation module ready.")

    def run(self, **kwargs):
        task = kwargs.get("task")
        # ... your logic here ...
        return {"status": "done", "task": task}

    def on_unload(self) -> None:
        print("Automation module unloaded.")
```

### Step 3 — Register in `app/main.py`

```python
from modules.automation.automation_module import AutomationModule

def build_orchestrator() -> Orchestrator:
    orch = Orchestrator()
    orch.register(VoiceModule())
    orch.register(AutomationModule())   # ← add this line
    return orch
```

That's it. The orchestrator handles the full lifecycle automatically.

### Calling a module

```python
# Via orchestrator (recommended)
result = orchestrator.run("automation", task="send_email")

# Direct reference (for module-specific methods)
auto = orchestrator.get("automation")
auto.run_scheduled_tasks()
```

---

## 🔌 Services Reference

Services are **reusable, stateless API wrappers** that any module can import.

### `LLMService`

| Method | Signature | Description |
|--------|-----------|-------------|
| `generate_response` | `(prompt: str, system_prompt: str = None) → str` | Generate a chat response |
| `reset_history` | `() → None` | Clear conversation context |
| `history` | *(property)* | Read current conversation history |

```python
from services.llm_service import LLMService

llm = LLMService()
reply = llm.generate_response("Explain quantum entanglement simply.")
```

### `STTService`

| Method | Signature | Description |
|--------|-----------|-------------|
| `transcribe` | `(file_path: str) → str` | Transcribe an audio file to text |

```python
from services.stt_service import STTService

stt = STTService()
text = stt.transcribe("audio/input.wav")
```

### `TTSService`

| Method | Signature | Description |
|--------|-----------|-------------|
| `synthesize` | `(text: str, output_path: str = None) → str` | Sync TTS synthesis |
| `synthesize_async` | `async (text: str, output_path: str = None) → str` | Async TTS synthesis |

```python
from services.tts_service import TTSService

tts = TTSService()
path = tts.synthesize("Hello, I am Edith.")
```

---

## 🎵 Audio Layer

### `AudioRecorder`

Records from the default system microphone.

```python
from audio.recorder import AudioRecorder

recorder = AudioRecorder()
path = recorder.record()          # default duration
path = recorder.record(duration=10)  # 10 seconds
```

### `AudioPlayer`

Plays MP3 or WAV files. Uses `pygame` if available, falls back to OS-native methods.

```python
from audio.player import AudioPlayer

player = AudioPlayer()
player.play("audio/response.mp3")
```

**Playback backend priority:**

| Priority | Backend | Platform |
|----------|---------|----------|
| 1 | `pygame.mixer` | All platforms |
| 2 | `afplay` | macOS |
| 3 | PowerShell / WMP | Windows |
| 4 | `mpg123` / `ffplay` | Linux |

---

## 📦 Dependencies

```
groq          — Groq Python SDK (LLM + Whisper API)
edge-tts      — Microsoft Edge neural TTS (free, no API key needed)
python-dotenv — Load .env variables
sounddevice   — Cross-platform microphone access
scipy         — WAV file writing
numpy         — Audio buffer handling
pygame        — Cross-platform audio playback (MP3 + WAV)
```

Install all at once:

```bash
pip install -r requirements.txt
```

### Linux extras

```bash
sudo apt install portaudio19-dev   # required by sounddevice
sudo apt install mpg123            # CLI fallback if pygame is unavailable
```

---

## 🗺️ Roadmap

The following modules are planned. Each will be an independent `BaseModule` subclass:

| Module | Feature |
|--------|---------|
| `voice` | ✅ Speech ↔ LLM ↔ TTS pipeline *(current)* |
| `memory` | 🔲 Long-term memory with vector storage |
| `automation` | 🔲 Task scheduling and system automation |
| `browser` | 🔲 Web search and page summarisation |
| `smart_home` | 🔲 IoT device control (Home Assistant / MQTT) |
| `vision` | 🔲 Image / screen understanding |
| `plugin_loader` | 🔲 Dynamic plugin discovery from a `plugins/` directory |

---

## 🛡️ Security

- **Never** hardcode API keys — always use `.env`
- **Never** commit `.env` to version control
- The `.env.example` file is safe to commit — it contains no real secrets
- All API keys are loaded exclusively through `config/settings.py`

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-new-module`
3. Implement your `BaseModule` subclass in `modules/your_feature/`
4. Add tests (coming soon — `tests/` directory)
5. Register the module in `app/main.py`
6. Submit a pull request

---

## 📄 License

MIT License — see `LICENSE` for details.

---

*Built with ❤️ — Designed to grow.*
