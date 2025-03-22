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
    
    def __post_init__(self):
        if self.custom_prompt_templates is None:
            self.custom_prompt_templates = {
                "summarize": "Please summarize the following text concisely: {text}",
                "action_items": "Extract key action items from the following text: {text}",
                "key_points": "What are the key points from this text: {text}"
            }

@dataclass
class Settings:
    hotkeys: HotkeySettings
    audio: AudioSettings
    transcription: TranscriptionSettings
    llm: LLMSettings = None
    
    def __post_init__(self):
        if self.llm is None:
            self.llm = LLMSettings()