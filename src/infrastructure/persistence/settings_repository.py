import json
from pathlib import Path
from typing import Optional
import logging
from PySide6.QtGui import QKeySequence
from ...domain.settings import Settings, HotkeySettings, AudioSettings, TranscriptionSettings

logger = logging.getLogger(__name__)

class SettingsRepository:
    def __init__(self):
        self.settings_file = Path.home() / ".voicerecorder" / "settings.json"
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Settings repository initialized with file path: {self.settings_file}")
        
    def load(self) -> Settings:
        logger.info(f"Loading settings from {self.settings_file}")
        if not self.settings_file.exists():
            logger.warning(f"Settings file does not exist at {self.settings_file}, creating default settings")
            return self._create_default_settings()
        
        try:
            with open(self.settings_file, 'r') as f:
                data = json.load(f)
                logger.debug(f"Raw settings loaded from file: {data}")
                settings = self._deserialize_settings(data)
                # Log key settings values
                logger.info(f"Settings loaded successfully. Key values: "
                           f"quit_key={settings.hotkeys.quit_key.toString() if settings.hotkeys.quit_key else 'None'}, "
                           f"record_key={settings.hotkeys.record_key.toString()}")
                return settings
        except Exception as e:
            logger.error(f"Error loading settings: {e}", exc_info=True)
            return self._create_default_settings()
    
    def save(self, settings: Settings) -> None:
        logger.info(f"Saving settings to {self.settings_file}")
        try:
            # Log key settings values being saved
            logger.info(f"Saving settings. Key values: "
                       f"quit_key={settings.hotkeys.quit_key.toString() if settings.hotkeys.quit_key else 'None'}, "
                       f"record_key={settings.hotkeys.record_key.toString()}")
            
            serialized_data = self._serialize_settings(settings)
            logger.debug(f"Serialized settings: {serialized_data}")
            
            with open(self.settings_file, 'w') as f:
                json.dump(serialized_data, f, indent=2)
            logger.info("Settings saved successfully")
        except Exception as e:
            logger.error(f"Error saving settings: {e}", exc_info=True)
            raise  # Re-raise to allow UI to show error message
    
    def _create_default_settings(self) -> Settings:
        logger.info("Creating default settings")
        return Settings(
            hotkeys=HotkeySettings(
                record_key=QKeySequence("Ctrl+Shift+R"),
                quit_key=QKeySequence("Ctrl+Shift+Q")
            ),
            audio=AudioSettings(
                input_device="default",
                sample_rate=44100,
                channels=1
            ),
            transcription=TranscriptionSettings()
        )
    
    def _serialize_settings(self, settings: Settings) -> dict:
        # Serialize settings to a dictionary
        return {
            "hotkeys": {
                "record_key": settings.hotkeys.record_key.toString(),
                "quit_key": settings.hotkeys.quit_key.toString() if settings.hotkeys.quit_key else None,
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
        
        # Create appearance settings if present
        appearance_settings = None
        if "appearance" in data:
            appearance_settings = AppearanceSettings(
                show_notifications=data["appearance"].get("show_notifications", True),
                auto_copy_to_clipboard=data["appearance"].get("auto_copy_to_clipboard", True),
                theme=data["appearance"].get("theme", "Light")
            )
            
        return Settings(
            hotkeys=HotkeySettings(
                record_key=QKeySequence(data["hotkeys"]["record_key"]),
                quit_key=QKeySequence(data["hotkeys"]["quit_key"]) if data["hotkeys"].get("quit_key") else None,
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
            llm=llm_settings,
            appearance=appearance_settings
        ) 