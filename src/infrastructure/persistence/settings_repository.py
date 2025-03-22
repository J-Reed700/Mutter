import json
from pathlib import Path
from typing import Optional
from PySide6.QtGui import QKeySequence
from ...domain.settings import Settings, HotkeySettings, AudioSettings, TranscriptionSettings

class SettingsRepository:
    def __init__(self):
        self.settings_file = Path.home() / ".voicerecorder" / "settings.json"
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        
    def load(self) -> Settings:
        if not self.settings_file.exists():
            return self._create_default_settings()
        
        try:
            with open(self.settings_file, 'r') as f:
                data = json.load(f)
                return self._deserialize_settings(data)
        except Exception as e:
            print(f"Error loading settings: {e}")
            return self._create_default_settings()
    
    def save(self, settings: Settings) -> None:
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self._serialize_settings(settings), f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def _create_default_settings(self) -> Settings:
        return Settings(
            hotkeys=HotkeySettings(
                record_key=QKeySequence("Ctrl+Shift+R"),
                pause_key=QKeySequence("Ctrl+Shift+P")
            ),
            audio=AudioSettings(
                input_device="default",
                sample_rate=44100,
                channels=1
            ),
            transcription=TranscriptionSettings()
        )
    
    def _serialize_settings(self, settings: Settings) -> dict:
        return {
            "hotkeys": {
                "record_key": settings.hotkeys.record_key.toString(),
                "pause_key": settings.hotkeys.pause_key.toString() if settings.hotkeys.pause_key else None
            },
            "audio": {
                "input_device": settings.audio.input_device,
                "sample_rate": settings.audio.sample_rate,
                "channels": settings.audio.channels
            },
            "transcription": {
                "model": settings.transcription.model,
                "language": settings.transcription.language,
                "device": settings.transcription.device
            }
        }
    
    def _deserialize_settings(self, data: dict) -> Settings:
        return Settings(
            hotkeys=HotkeySettings(
                record_key=QKeySequence(data["hotkeys"]["record_key"]),
                pause_key=QKeySequence(data["hotkeys"]["pause_key"]) if data["hotkeys"].get("pause_key") else None
            ),
            audio=AudioSettings(
                input_device=data["audio"]["input_device"],
                sample_rate=data["audio"]["sample_rate"],
                channels=data["audio"]["channels"]
            ),
            transcription=TranscriptionSettings(
                model=data["transcription"]["model"],
                language=data["transcription"]["language"],
                device=data["transcription"]["device"]
            )
        ) 