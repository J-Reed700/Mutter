from dataclasses import dataclass
from typing import Optional
from PySide6.QtGui import QKeySequence

@dataclass
class HotkeySettings:
    record_key: QKeySequence
    pause_key: Optional[QKeySequence] = None

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
class Settings:
    hotkeys: HotkeySettings
    audio: AudioSettings
    transcription: TranscriptionSettings 