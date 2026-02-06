from dataclasses import dataclass
from typing import Optional
from PySide6.QtGui import QKeySequence

@dataclass
class HotkeySettings:
    record_key: QKeySequence
    quit_key: Optional[QKeySequence] = None
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
    api_url: str = "http://localhost:11434/v1"  # Default to Ollama
    model: str = "llama3.2"
    enabled: bool = False
    custom_prompt: str = """You are an intelligent text processing assistant. The user has dictated text using voice transcription.

Your task:
1. If the text contains instructions like "make this more descriptive", "enhance this", "add adjectives", "rewrite this professionally", etc., apply those instructions to the REST of the text (the part BEFORE the instruction).
2. If there are no instructions, simply fix grammar, spelling, and punctuation errors.
3. Remove any meta-instructions from the final output (phrases like "can you...", "make this...", etc.).
4. Output ONLY the final processed text - no explanations, no preambles.

Examples:
- Input: "I need error handling. Make this more professional."
  Output: "We require comprehensive error handling mechanisms."

- Input: "The project is delayed. Add more descriptive words."
  Output: "The critical project timeline has experienced significant delays."

- Input: "I went to the store yesterday"
  Output: "I went to the store yesterday."

Text to process:

{text}"""
    # Authentication for external LLM endpoint (Basic Auth)
    api_username: str = ""  # Username for HTTP Basic Auth
    api_password: str = ""  # Password for HTTP Basic Auth

@dataclass
class AppearanceSettings:
    """Settings for application appearance and behavior"""
    show_notifications: bool = True  # Whether to show system tray notifications
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