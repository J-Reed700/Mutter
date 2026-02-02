"""
ServiceManager is responsible for orchestrating application functionality by coordinating
infrastructure services and domain entities.
"""

import logging
import platform
from typing import Optional, Dict, Any

from PySide6.QtCore import QObject

from ..domain.settings import Settings, LLMSettings
from ..infrastructure.persistence.settings_repository import SettingsRepository
from ..infrastructure.audio.recorder import AudioRecorder
from ..infrastructure.transcription.transcriber import Transcriber
from ..infrastructure.llm.processor import TextProcessor
from ..infrastructure.llm.embedded_processor import EmbeddedTextProcessor
from ..infrastructure.llm.download_manager import DownloadManager
from ..infrastructure.recording.recording_service import RecordingService


logger = logging.getLogger(__name__)


class ServiceManager(QObject):
    """
    Central orchestrator for application functionality.
    
    Responsibilities:
    1. Initialization and configuration of infrastructure services
    2. Provide access to services through a clean API
    3. Handle dependencies between services
    4. Coordinate application shutdown
    """
    
    def __init__(self):
        """Initialize the service manager and all infrastructure services."""
        super().__init__()
        logger.info("Initializing service manager")
        
        # Core dependencies
        self._settings_repository = None
        self._settings = None
        
        # Services
        self._recording_service = None
        
        # Infrastructure components
        self._audio_recorder = None
        self._transcriber = None
        self._text_processor = None
        self._embedded_processor = None
        self._download_manager = None
        
        # Initialize everything
        self._initialize_core_dependencies()
        self._initialize_infrastructure()
        self._initialize_services()
        
        logger.info("Service manager initialization complete")
    
    def _initialize_core_dependencies(self):
        """Initialize core dependencies like settings."""
        logger.debug("Initializing core dependencies")
        
        # Initialize settings repository
        self._settings_repository = SettingsRepository()
        
        # Load settings
        self._settings = self._settings_repository.load()
        
        # Ensure all settings sections are initialized
        if not hasattr(self._settings, 'llm') or self._settings.llm is None:
            self._settings.llm = LLMSettings()
    
    def _initialize_infrastructure(self):
        """Initialize infrastructure components."""
        logger.debug("Initializing infrastructure components")
        
        # Initialize download manager first
        self._download_manager = DownloadManager()
        
        # Initialize audio recorder
        self._audio_recorder = AudioRecorder(
            sample_rate=self._settings.audio.sample_rate,
            channels=self._settings.audio.channels,
            device=self._settings.audio.input_device
        )
        
        # Initialize transcriber
        self._transcriber = Transcriber(
            model_size=self._settings.transcription.model,
            device=self._settings.transcription.device,
            compute_type="int8"
        )
        
        # Set LLM settings to disabled
        if hasattr(self._settings, 'llm'):
            self._settings.llm.enabled = False
            logger.info("LLM features have been disabled")
    
    def _initialize_llm_processors(self):
        """Initialize LLM processors based on settings."""
        logger.debug("Initializing LLM processors")
        
        # Initialize external API processor if not using embedded model
        if not self._settings.llm.use_embedded_model:
            self._text_processor = TextProcessor(
                api_url=self._settings.llm.api_url
            )
        else:
            # Initialize embedded processor if available and enabled
            try:
                self._embedded_processor = EmbeddedTextProcessor(
                    model_name=self._settings.llm.embedded_model_name,
                    progress_callback=self._download_manager.get_progress_callback()
                )
            except Exception as e:
                logger.error(f"Failed to initialize embedded LLM processor: {e}")
    
    def _initialize_services(self):
        """Initialize application services."""
        logger.debug("Initializing services")
        
        # Initialize recording service
        self._recording_service = RecordingService(
            settings=self._settings,
            settings_repository=self._settings_repository,
            audio_recorder=self._audio_recorder,
            transcriber=self._transcriber
        )
    
    def reload_settings(self):
        """Reload settings and update all services."""
        logger.info("Reloading settings")
        
        # Reload settings from repository
        self._settings = self._settings_repository.load()
        
        # Log key settings values after reload
        logger.info(f"Reloaded settings with values: "
                   f"quit_key={self._settings.hotkeys.quit_key.toString() if self._settings.hotkeys.quit_key else 'None'}, "
                   f"record_key={self._settings.hotkeys.record_key.toString()}")
        
        # Update services with new settings
        if self._recording_service:
            # Check if update_settings method exists
            if hasattr(self._recording_service, 'update_settings'):
                self._recording_service.update_settings(self._settings)
            else:
                # If update_settings doesn't exist, assign the new settings directly
                self._recording_service.settings = self._settings
        
        # Reinitialize LLM processors if needed
        if self._settings.llm.enabled:
            llm_settings_changed = (
                not hasattr(self, '_previous_llm_settings') or
                self._settings.llm.model != getattr(self, '_previous_llm_settings', {}).get('model') or
                self._settings.llm.api_url != getattr(self, '_previous_llm_settings', {}).get('api_url') or
                self._settings.llm.use_embedded_model != getattr(self, '_previous_llm_settings', {}).get('use_embedded_model') or
                self._settings.llm.embedded_model_name != getattr(self, '_previous_llm_settings', {}).get('embedded_model_name')
            )
            
            if llm_settings_changed:
                # Clear existing processors
                self._text_processor = None
                self._embedded_processor = None
                
                # Reinitialize
                self._initialize_llm_processors()
                
                # Let the recording service re-initialize its LLM processors
                if hasattr(self._recording_service, '_initialize_llm_processor'):
                    self._recording_service._initialize_llm_processor()
            
            # Store current LLM settings for future comparisons
            self._previous_llm_settings = {
                'model': self._settings.llm.model,
                'api_url': self._settings.llm.api_url,
                'use_embedded_model': self._settings.llm.use_embedded_model,
                'embedded_model_name': self._settings.llm.embedded_model_name
            }
    
    def save_settings(self):
        """Save current settings to storage."""
        logger.info("Saving settings")
        self._settings_repository.save(self._settings)
    
    @property
    def settings(self) -> Settings:
        """Get the current settings."""
        return self._settings
    
    @property
    def recording_service(self) -> RecordingService:
        """Get the recording service."""
        return self._recording_service
    
    @property
    def text_processor(self) -> Optional[TextProcessor]:
        """Get the LLM text processor if available."""
        return self._text_processor
    
    @property
    def embedded_processor(self) -> Optional[EmbeddedTextProcessor]:
        """Get the embedded LLM processor if available."""
        return self._embedded_processor
    
    @property
    def download_manager(self) -> Optional[DownloadManager]:
        """Get the download manager"""
        return self._download_manager
    
    def shutdown(self):
        """Perform clean shutdown of all services."""
        logger.info("Shutting down service manager")
        
        # Shutdown recording service (which will handle transcription and LLM)
        if self._recording_service:
            logger.debug("Shutting down recording service")
            try:
                self._recording_service.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down recording service: {e}")
        
        # Clean up audio recorder explicitly
        if self._audio_recorder:
            logger.debug("Cleaning up audio recorder")
            try:
                if hasattr(self._audio_recorder, 'cleanup'):
                    self._audio_recorder.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up audio recorder: {e}")
        
        # Clean up any resources held by processors
        self._text_processor = None
        self._embedded_processor = None
        
        # Save settings on shutdown
        try:
            self.save_settings()
        except Exception as e:
            logger.error(f"Error saving settings during shutdown: {e}")
        
        logger.info("Service manager shutdown complete") 