"""
AudioMetadata contains information about an audio recording.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AudioMetadata:
    """Value object representing metadata for an audio recording."""
    sample_rate: int  # Sample rate in Hz
    channels: int  # Number of audio channels
    bit_depth: int  # Bit depth (e.g., 16, 24)
    format: str  # Audio format (e.g., WAV, MP3)
    device_name: str  # Name of the recording device used
    file_size_bytes: int  # Size of the file in bytes
    is_compressed: bool = False  # Whether the audio is compressed
    compression_rate: Optional[float] = None  # Compression rate if applicable
    
    def __post_init__(self):
        """Validate the audio metadata."""
        if self.sample_rate <= 0:
            raise ValueError("Sample rate must be positive")
        if self.channels <= 0:
            raise ValueError("Channels must be positive")
        if self.bit_depth <= 0:
            raise ValueError("Bit depth must be positive")
        if self.file_size_bytes < 0:
            raise ValueError("File size cannot be negative")
        if self.is_compressed and self.compression_rate is None:
            object.__setattr__(self, "compression_rate", 1.0) 