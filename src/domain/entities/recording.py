"""
Recording entity represents an audio recording in the system.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from ..value_objects.audio_metadata import AudioMetadata


@dataclass
class Recording:
    """Represents an audio recording in the domain."""
    id: UUID  # Unique identifier
    file_path: Path  # Path to the audio file
    created_at: datetime  # When the recording was created
    duration_seconds: float  # Duration in seconds
    metadata: AudioMetadata  # Audio metadata
    transcription_id: Optional[UUID] = None  # Reference to associated transcription
    
    def is_transcribed(self) -> bool:
        """Check if the recording has been transcribed."""
        return self.transcription_id is not None
    
    def get_file_name(self) -> str:
        """Get the file name without the path."""
        return self.file_path.name
    
    def get_age_seconds(self) -> float:
        """Get the age of the recording in seconds."""
        return (datetime.now() - self.created_at).total_seconds()
    
    def is_valid(self) -> bool:
        """Check if the recording is valid."""
        return (
            self.duration_seconds > 0 and
            self.file_path.exists() and
            self.file_path.is_file()
        ) 