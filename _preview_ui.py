import os
import sys
import time

os.environ["GROQ_API_KEY"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import ui

# ── Full session simulation ────────────────────────────────────────────────────

ui.clear_screen()
ui.display_header(github_url="github.com/kaya0s/J.git")

ui.print_system("All systems online.")
ui.print_boot_info(
    modules=["voice"],
    exit_phrases=["bye", "exit", "goodbye", "stop"],
)

# ── Turn 1 ────────────────────────────────────────────────────────────────────

ui.print_divider()
ui.print_listening(5)

sp = ui.Spinner("Transcribing")
sp.start()
time.sleep(0.7)
sp.stop()

ui.print_user("What is the capital of France?")

sp2 = ui.Spinner("Thinking")
sp2.start()
time.sleep(0.7)
sp2.stop()

ui.print_jarvis_stream(
    "The capital of France is Paris — a city renowned for its art, "
    "gastronomy, and rich culture. It has served as the country's "
    "capital since the 10th century and remains one of the most "
    "visited cities in the world.",
    char_delay=0.007,
)

sp3 = ui.Spinner("Synthesising")
sp3.start()
time.sleep(0.4)
sp3.stop()

# ── Turn 2 ────────────────────────────────────────────────────────────────────

ui.print_divider()
ui.print_listening(5)

sp4 = ui.Spinner("Transcribing")
sp4.start()
time.sleep(0.5)
sp4.stop()

ui.print_user("Who invented the telephone?")

sp5 = ui.Spinner("Thinking")
sp5.start()
time.sleep(0.6)
sp5.stop()

ui.print_jarvis_stream(
    "The telephone was invented by Alexander Graham Bell, who was "
    "awarded the first patent for it on March 7, 1876. However, "
    "Italian inventor Antonio Meucci had developed an early voice "
    "communication device years prior and is also credited by the "
    "US Congress as a contributor to the invention.",
    char_delay=0.007,
)

sp6 = ui.Spinner("Synthesising")
sp6.start()
time.sleep(0.4)
sp6.stop()

# ── Turn 3 — exit ─────────────────────────────────────────────────────────────

ui.print_divider()
ui.print_listening(5)

sp7 = ui.Spinner("Transcribing")
sp7.start()
time.sleep(0.4)
sp7.stop()

ui.print_user("Goodbye JARVIS.")

sp8 = ui.Spinner("Thinking")
sp8.start()
time.sleep(0.3)
sp8.stop()

ui.print_jarvis_stream(
    "Goodbye! It was a pleasure assisting you. Have a great day.",
    char_delay=0.007,
)

ui.print_goodbye()
