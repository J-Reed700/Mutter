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
                "pause_key": settings.hotkeys.pause_key.toString() if settings.hotkeys.pause_key else None,
                "process_text_key": settings.hotkeys.process_text_key.toString() if settings.hotkeys.process_text_key else None
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
            },
            "llm": {
                "enabled": settings.llm.enabled if hasattr(settings, 'llm') and settings.llm else False,
                "api_url": settings.llm.api_url if hasattr(settings, 'llm') and settings.llm else "http://localhost:8080/v1",
                "model": settings.llm.model if hasattr(settings, 'llm') and settings.llm else "llama3",
                "default_processing_type": settings.llm.default_processing_type if hasattr(settings, 'llm') and settings.llm else "summarize",
                "custom_prompt_templates": settings.llm.custom_prompt_templates if hasattr(settings, 'llm') and settings.llm and settings.llm.custom_prompt_templates else None,
                "use_embedded_model": settings.llm.use_embedded_model if hasattr(settings, 'llm') and settings.llm else False,
                "embedded_model_name": settings.llm.embedded_model_name if hasattr(settings, 'llm') and settings.llm else "distilbart-cnn-12-6"
            },
            "appearance": {
                "show_notifications": settings.appearance.show_notifications if hasattr(settings, 'appearance') and settings.appearance else True,
                "auto_copy_to_clipboard": settings.appearance.auto_copy_to_clipboard if hasattr(settings, 'appearance') and settings.appearance else True,
                "theme": settings.appearance.theme if hasattr(settings, 'appearance') and settings.appearance else "Light"
            }
        }
    
    def _deserialize_settings(self, data: dict) -> Settings:
        from ...domain.settings import LLMSettings, AppearanceSettings
        
        # Create LLM settings if present in data
        llm_settings = None
        if "llm" in data:
            llm_settings = LLMSettings(
                enabled=data["llm"].get("enabled", False),
                api_url=data["llm"].get("api_url", "http://localhost:8080/v1"),
                model=data["llm"].get("model", "llama3"),
                default_processing_type=data["llm"].get("default_processing_type", "summarize"),
                custom_prompt_templates=data["llm"].get("custom_prompt_templates", None),
                use_embedded_model=data["llm"].get("use_embedded_model", False),
                embedded_model_name=data["llm"].get("embedded_model_name", "distilbart-cnn-12-6")
            )
        
        return Settings(
            hotkeys=HotkeySettings(
                record_key=QKeySequence(data["hotkeys"]["record_key"]),
                pause_key=QKeySequence(data["hotkeys"]["pause_key"]) if data["hotkeys"].get("pause_key") else None,
                process_text_key=QKeySequence(data["hotkeys"]["process_text_key"]) if data["hotkeys"].get("process_text_key") else None
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
            ),
            llm=llm_settings
        ) 