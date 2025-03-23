from dataclasses import dataclass
from typing import Optional, Dict, List
from PySide6.QtGui import QKeySequence

@dataclass
class HotkeySettings:
    record_key: QKeySequence
    pause_key: Optional[QKeySequence] = None
    process_text_key: Optional[QKeySequence] = None  # New hotkey for LLM processing

@dataclass
class AudioSettings:
    input_device: str
    sample_rate: int = 44100
    channels: int = 1

@dataclass
class TranscriptionSettings:
    model: str = "base"
    language: str = "en"
    device: str = "cpu"

@dataclass
class LLMSettings:
    """Settings for LLM text processing"""
    api_url: str = "http://localhost:8080/v1"
    model: str = "llama3"
    enabled: bool = False
    default_processing_type: str = "summarize"  # "summarize" or "custom"
    custom_prompt_templates: Dict[str, str] = None
    use_embedded_model: bool = False  # Whether to use the embedded model instead of API
    embedded_model_name: str = "distilbart-cnn-12-6"  # Default embedded model
    
    def __post_init__(self):
        if self.custom_prompt_templates is None:
            self.custom_prompt_templates = {
                "summarize": "Please summarize the following text concisely: {text}",
                "action_items": "Extract key action items from the following text: {text}",
                "key_points": "What are the key points from this text: {text}"
            }

@dataclass
class AppearanceSettings:
    """Settings for application appearance and behavior"""
    show_notifications: bool = True  # Whether to show system tray notifications
    mute_notifications: bool = True  # Whether to mute notification sounds
    auto_copy_to_clipboard: bool = True  # Whether to automatically copy transcription to clipboard
    auto_paste: bool = True  # Whether to automatically paste transcription to active window
    theme: str = "Light"  # Theme name

@dataclass
class Settings:
    hotkeys: HotkeySettings
    audio: AudioSettings
    transcription: TranscriptionSettings
    llm: LLMSettings = None
    appearance: AppearanceSettings = None
    
    def __post_init__(self):
        if self.llm is None:
            self.llm = LLMSettings()
        if self.appearance is None:
            self.appearance = AppearanceSettings()