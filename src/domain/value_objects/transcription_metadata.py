"""
TranscriptionMetadata contains information about a transcription process.
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class TranscriptionMetadata:
    """Value object representing metadata for a transcription."""
    model_name: str  # Name of the model used for transcription
    language: str  # Language code (e.g., 'en', 'es')
    confidence_score: float  # Overall confidence score (0-1)
    processing_time_ms: int  # Time taken to process in milliseconds
    device: str  # Device used for processing (e.g., 'cpu', 'cuda')
    word_timestamps: bool  # Whether word-level timestamps were generated
    model_version: Optional[str] = None  # Version of the model
    additional_params: Optional[Dict[str, Any]] = None  # Additional parameters used
    
    def __post_init__(self):
        """Validate the transcription metadata."""
        if not 0 <= self.confidence_score <= 1:
            raise ValueError("Confidence score must be between 0 and 1")
        if self.processing_time_ms < 0:
            raise ValueError("Processing time cannot be negative") 