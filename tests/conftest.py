# tests/conftest.py
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
CHATBOT_DIR = Path(__file__).resolve().parents[1] / "chatbot"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(CHATBOT_DIR))
