"""
LLMResult entity represents the result of processing a transcription with a language model.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Dict, Optional
from uuid import UUID


class ProcessingType(Enum):
    """Types of LLM processing that can be performed on transcriptions."""
    SUMMARIZE = auto()
    ACTION_ITEMS = auto()
    KEY_POINTS = auto()
    CUSTOM = auto()
    
    @classmethod
    def from_string(cls, value: str) -> 'ProcessingType':
        """Convert a string to a ProcessingType enum value."""
        value = value.upper()
        for member in cls:
            if member.name == value:
                return member
        raise ValueError(f"Unknown processing type: {value}")
    
    def __str__(self) -> str:
        """Return a display-friendly string representation."""
        return self.name.lower().replace('_', ' ')


@dataclass
class LLMResult:
    """Represents the result of LLM processing on a transcription."""
    id: UUID  # Unique identifier
    transcription_id: UUID  # Reference to transcription
    processing_type: ProcessingType  # Type of processing performed
    result_text: str  # The processed text result
    created_at: datetime  # When the processing was completed
    model_used: str  # Name of the model used
    prompt_used: str  # The prompt that was used
    processing_time_ms: int  # Time taken to process in milliseconds
    token_count: Optional[int] = None  # Number of tokens processed
    metadata: Optional[Dict] = None  # Additional processing metadata
    
    def is_summary(self) -> bool:
        """Check if this result is a summary."""
        return self.processing_type == ProcessingType.SUMMARIZE
    
    def is_action_items(self) -> bool:
        """Check if this result contains action items."""
        return self.processing_type == ProcessingType.ACTION_ITEMS
    
    def is_key_points(self) -> bool:
        """Check if this result contains key points."""
        return self.processing_type == ProcessingType.KEY_POINTS
    
    def is_custom(self) -> bool:
        """Check if this result is from a custom prompt."""
        return self.processing_type == ProcessingType.CUSTOM 