"""
Events related to transcription and LLM processing operations.
"""
from dataclasses import dataclass, InitVar
from datetime import datetime
from typing import Optional
from uuid import UUID

from ..entities.llm_result import ProcessingType


@dataclass
class ProcessingEvent:
    """Base class for processing events."""
    timestamp: datetime
    
    def __init__(self, timestamp: datetime = None):
        """Initialize with an optional timestamp that defaults to now."""
        self.timestamp = timestamp or datetime.now()


# Transcription Events

@dataclass
class TranscriptionStarted(ProcessingEvent):
    """Event raised when a transcription process has started."""
    recording_id: UUID
    
    def __init__(self, recording_id: UUID, timestamp: datetime = None):
        """Initialize with required fields and optional timestamp."""
        super().__init__(timestamp)
        self.recording_id = recording_id


@dataclass
class TranscriptionCompleted(ProcessingEvent):
    """Event raised when a transcription has completed."""
    recording_id: UUID
    transcription_id: UUID
    text_length: int
    processing_time_ms: int
    
    def __init__(self, recording_id: UUID, transcription_id: UUID, text_length: int, 
                 processing_time_ms: int, timestamp: datetime = None):
        """Initialize with required fields and optional timestamp."""
        super().__init__(timestamp)
        self.recording_id = recording_id
        self.transcription_id = transcription_id
        self.text_length = text_length
        self.processing_time_ms = processing_time_ms


@dataclass
class TranscriptionFailed(ProcessingEvent):
    """Event raised when a transcription has failed."""
    recording_id: UUID
    error_message: str
    exception: Optional[Exception] = None
    
    def __init__(self, recording_id: UUID, error_message: str, 
                 exception: Optional[Exception] = None, timestamp: datetime = None):
        """Initialize with required fields and optional timestamp."""
        super().__init__(timestamp)
        self.recording_id = recording_id
        self.error_message = error_message
        self.exception = exception


# LLM Processing Events

@dataclass
class LLMProcessingStarted(ProcessingEvent):
    """Event raised when LLM processing has started."""
    transcription_id: UUID
    processing_type: ProcessingType
    
    def __init__(self, transcription_id: UUID, processing_type: ProcessingType, timestamp: datetime = None):
        """Initialize with required fields and optional timestamp."""
        super().__init__(timestamp)
        self.transcription_id = transcription_id
        self.processing_type = processing_type


@dataclass
class LLMProcessingCompleted(ProcessingEvent):
    """Event raised when LLM processing has completed."""
    transcription_id: UUID
    result_id: UUID
    processing_type: ProcessingType
    result_length: int
    processing_time_ms: int
    
    def __init__(self, transcription_id: UUID, result_id: UUID, processing_type: ProcessingType,
                 result_length: int, processing_time_ms: int, timestamp: datetime = None):
        """Initialize with required fields and optional timestamp."""
        super().__init__(timestamp)
        self.transcription_id = transcription_id
        self.result_id = result_id
        self.processing_type = processing_type
        self.result_length = result_length
        self.processing_time_ms = processing_time_ms


@dataclass
class LLMProcessingFailed(ProcessingEvent):
    """Event raised when LLM processing has failed."""
    transcription_id: UUID
    processing_type: ProcessingType
    error_message: str
    exception: Optional[Exception] = None
    
    def __init__(self, transcription_id: UUID, processing_type: ProcessingType,
                 error_message: str, exception: Optional[Exception] = None, timestamp: datetime = None):
        """Initialize with required fields and optional timestamp."""
        super().__init__(timestamp)
        self.transcription_id = transcription_id
        self.processing_type = processing_type
        self.error_message = error_message
        self.exception = exception 