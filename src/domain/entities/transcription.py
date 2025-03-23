"""
Transcription entity represents a text transcription of an audio recording.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict
from uuid import UUID

from ..value_objects.transcription_metadata import TranscriptionMetadata


@dataclass
class Transcription:
    """Represents a speech-to-text transcription result."""
    id: UUID  # Unique identifier
    recording_id: UUID  # Reference to recording
    text: str  # The transcribed text
    created_at: datetime  # When the transcription was created
    metadata: TranscriptionMetadata  # Transcription metadata
    llm_result_id: Optional[UUID] = None  # Reference to LLM processing result
    segments: Optional[List[Dict]] = None  # Optional segmentation data
    
    def is_processed(self) -> bool:
        """Check if the transcription has been processed by an LLM."""
        return self.llm_result_id is not None
    
    def word_count(self) -> int:
        """Count the number of words in the transcription."""
        return len(self.text.split())
    
    def contains_keyword(self, keyword: str) -> bool:
        """Check if the transcription contains a specific keyword."""
        return keyword.lower() in self.text.lower()
    
    def get_summary(self, max_length: int = 100) -> str:
        """Get a summary of the transcription text."""
        if len(self.text) <= max_length:
            return self.text
        return f"{self.text[:max_length-3]}..." 