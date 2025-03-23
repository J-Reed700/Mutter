"""
Events related to recording operations.
"""
from dataclasses import dataclass, field, InitVar
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID


@dataclass
class RecordingEvent:
    """Base class for recording events."""
    # Make timestamp a required field with no default in the class definition
    timestamp: datetime
    
    def __init__(self, timestamp: datetime = None):
        """Initialize with an optional timestamp that defaults to now."""
        self.timestamp = timestamp or datetime.now()


@dataclass
class RecordingStarted(RecordingEvent):
    """Event raised when a recording has started."""
    
    def __init__(self, timestamp: datetime = None):
        """Initialize with optional timestamp."""
        super().__init__(timestamp)


@dataclass
class RecordingStopped(RecordingEvent):
    """Event raised when a recording has stopped."""
    recording_id: UUID
    file_path: Path
    duration_seconds: float
    
    def __init__(self, recording_id: UUID, file_path: Path, duration_seconds: float, timestamp: datetime = None):
        """Initialize with required fields and optional timestamp."""
        super().__init__(timestamp)
        self.recording_id = recording_id
        self.file_path = file_path
        self.duration_seconds = duration_seconds


@dataclass
class RecordingFailed(RecordingEvent):
    """Event raised when a recording has failed."""
    error_message: str
    exception: Optional[Exception] = None
    
    def __init__(self, error_message: str, exception: Optional[Exception] = None, timestamp: datetime = None):
        """Initialize with required fields and optional timestamp."""
        super().__init__(timestamp)
        self.error_message = error_message
        self.exception = exception


@dataclass
class RecordingDeleted(RecordingEvent):
    """Event raised when a recording has been deleted."""
    recording_id: UUID
    
    def __init__(self, recording_id: UUID, timestamp: datetime = None):
        """Initialize with required fields and optional timestamp."""
        super().__init__(timestamp)
        self.recording_id = recording_id 