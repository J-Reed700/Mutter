# Quick test script (test.py)
import sys
from pathlib import Path
from src.main import Application

def setup_test_environment():
    # Create necessary directories
    (Path.home() / ".voicerecorder" / "recordings").mkdir(parents=True, exist_ok=True)
    
    # Create empty settings file if it doesn't exist
    settings_file = Path.home() / ".voicerecorder" / "settings.json"
    if not settings_file.exists():
        settings_file.write_text("{}")

if __name__ == "__main__":
    setup_test_environment()
    app = Application()
    sys.exit(app.run())