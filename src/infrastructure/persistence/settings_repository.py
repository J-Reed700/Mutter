import json
from pathlib import Path
from typing import Optional
import logging
from PySide6.QtGui import QKeySequence
from ...domain.settings import (
    Settings,
    HotkeySettings,
    AudioSettings,
    TranscriptionSettings,
    LLMSettings,
    AppearanceSettings,
)

logger = logging.getLogger(__name__)

# Older versions stored full language names (e.g. "English") or "Auto-detect";
# the app now stores ISO codes (None = auto-detect). Used to migrate on load.
_LEGACY_LANGUAGE_NAMES = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "dutch": "nl",
    "russian": "ru",
    "arabic": "ar",
    "hindi": "hi",
    "chinese": "zh",
    "japanese": "ja",
    "korean": "ko",
    "auto-detect": None,
    "auto": None,
}


def _key_to_str(key: Optional[QKeySequence]) -> Optional[str]:
    """Serialize a key sequence; empty/None sequences become None."""
    if key is None or key.isEmpty():
        return None
    return key.toString()


def _str_to_key(value: Optional[str]) -> Optional[QKeySequence]:
    """Deserialize a key sequence string; empty/None become None."""
    if not value:
        return None
    key = QKeySequence(value)
    return None if key.isEmpty() else key


def _normalize_language(value: Optional[str]) -> Optional[str]:
    """Convert legacy language names to ISO codes; None means auto-detect."""
    if not value:
        return None
    return _LEGACY_LANGUAGE_NAMES.get(value.strip().lower(), value)


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
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Raw settings loaded from file: {data}")
                settings = self._deserialize_settings(data)
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
            logger.info(f"Saving settings. Key values: "
                       f"quit_key={settings.hotkeys.quit_key.toString() if settings.hotkeys.quit_key else 'None'}, "
                       f"record_key={settings.hotkeys.record_key.toString()}")

            serialized_data = self._serialize_settings(settings)
            logger.debug(f"Serialized settings: {serialized_data}")

            # Write to a temp file first so a crash mid-write can't corrupt
            # the only copy of the user's settings.
            tmp_file = self.settings_file.with_suffix('.json.tmp')
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(serialized_data, f, indent=2)
            tmp_file.replace(self.settings_file)
            logger.info("Settings saved successfully")
        except Exception as e:
            logger.error(f"Error saving settings: {e}", exc_info=True)
            raise  # Re-raise to allow UI to show error message

    def _create_default_settings(self) -> Settings:
        logger.info("Creating default settings")
        import platform
        if platform.system() == "Darwin":
            record_hotkey = QKeySequence("Command+Shift+R")
            quit_hotkey = QKeySequence("Command+Q")
        else:
            record_hotkey = QKeySequence("Ctrl+Shift+R")
            quit_hotkey = QKeySequence("Ctrl+Shift+Q")
        return Settings(
            hotkeys=HotkeySettings(
                record_key=record_hotkey,
                quit_key=quit_hotkey
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
                "quit_key": _key_to_str(settings.hotkeys.quit_key),
                "process_text_key": _key_to_str(settings.hotkeys.process_text_key)
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
                "enabled": settings.llm.enabled,
                "api_url": settings.llm.api_url,
                "model": settings.llm.model,
                "custom_prompt": settings.llm.custom_prompt,
                "api_username": settings.llm.api_username,
                "api_password": settings.llm.api_password
            },
            "appearance": {
                "show_notifications": settings.appearance.show_notifications,
                "auto_copy_to_clipboard": settings.appearance.auto_copy_to_clipboard,
                "auto_paste": settings.appearance.auto_paste,
                "theme": settings.appearance.theme
            }
        }

    def _deserialize_settings(self, data: dict) -> Settings:
        defaults = self._create_default_settings()

        # Hotkeys — fall back to platform defaults if the record key is
        # missing or unparseable (it is required for the app to function).
        hotkeys_data = data.get("hotkeys", {})
        record_key = _str_to_key((hotkeys_data.get("record_key") or "").split(",")[0].strip())
        if record_key is None:
            logger.warning("Record key missing/invalid in settings file, using default")
            record_key = defaults.hotkeys.record_key

        hotkey_settings = HotkeySettings(
            record_key=record_key,
            quit_key=_str_to_key(hotkeys_data.get("quit_key")),
            process_text_key=_str_to_key(hotkeys_data.get("process_text_key"))
        )
        logger.debug(f"Parsed hotkeys from settings: record_key={hotkey_settings.record_key.toString()}, "
                    f"quit_key={hotkey_settings.quit_key.toString() if hotkey_settings.quit_key else 'None'}, "
                    f"process_text_key={hotkey_settings.process_text_key.toString() if hotkey_settings.process_text_key else 'None'}")

        audio_data = data.get("audio", {})
        audio_settings = AudioSettings(
            input_device=audio_data.get("input_device", "default"),
            sample_rate=int(audio_data.get("sample_rate", 44100)),
            channels=int(audio_data.get("channels", 1))
        )

        transcription_data = data.get("transcription", {})
        transcription_defaults = TranscriptionSettings()
        # An explicit null means auto-detect; a missing key means "never set",
        # which falls back to the default language.
        if "language" in transcription_data:
            language = _normalize_language(transcription_data["language"])
        else:
            language = transcription_defaults.language
        transcription_settings = TranscriptionSettings(
            model=transcription_data.get("model", transcription_defaults.model),
            language=language,
            device=transcription_data.get("device", transcription_defaults.device)
        )

        llm_data = data.get("llm", {})
        llm_defaults = LLMSettings()
        llm_settings = LLMSettings(
            enabled=llm_data.get("enabled", llm_defaults.enabled),
            api_url=llm_data.get("api_url") or llm_defaults.api_url,
            model=llm_data.get("model") or llm_defaults.model,
            custom_prompt=llm_data.get("custom_prompt") or llm_defaults.custom_prompt,
            api_username=llm_data.get("api_username", ""),
            api_password=llm_data.get("api_password", "")
        )

        appearance_data = data.get("appearance", {})
        appearance_defaults = AppearanceSettings()
        appearance_settings = AppearanceSettings(
            show_notifications=appearance_data.get("show_notifications", appearance_defaults.show_notifications),
            auto_copy_to_clipboard=appearance_data.get("auto_copy_to_clipboard", appearance_defaults.auto_copy_to_clipboard),
            auto_paste=appearance_data.get("auto_paste", appearance_defaults.auto_paste),
            theme=appearance_data.get("theme", appearance_defaults.theme)
        )

        return Settings(
            hotkeys=hotkey_settings,
            audio=audio_settings,
            transcription=transcription_settings,
            llm=llm_settings,
            appearance=appearance_settings
        )
