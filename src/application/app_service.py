"""
ApplicationService orchestrates the various components of the application.
It's responsible for initializing and coordinating the infrastructure components
while protecting the higher layers from direct dependencies on infrastructure details.
"""

import platform
import logging
import sounddevice as sd
import numpy as np
from PySide6.QtCore import QObject
from typing import Optional

from ..domain.settings import Settings, LLMSettings
from ..infrastructure.persistence.settings_repository import SettingsRepository
from ..infrastructure.audio.recorder import AudioRecorder
from ..infrastructure.hotkeys.windows import WindowsHotkeyHandler
from ..infrastructure.hotkeys.base import HotkeyHandler
from ..infrastructure.transcription.transcriber import Transcriber
from ..infrastructure.llm.processor import TextProcessor
from .recording_service import RecordingService

logger = logging.getLogger(__name__)

class ApplicationService(QObject):
    """Application service that coordinates other services and components."""
    
    def __init__(self):
        """Initialize the application service and all dependencies"""
        super().__init__()
        logger.info("Initializing application service")
        
        # Load settings
        self.settings_repository = SettingsRepository()
        self.settings = self.settings_repository.load()
        
        # If LLM settings not initialized, set default values
        if not hasattr(self.settings, 'llm') or self.settings.llm is None:
            self.settings.llm = LLMSettings()
        
        # Test microphone access
        self._test_microphone_access()
        
        # Create audio recorder
        self.audio_recorder = AudioRecorder(
            sample_rate=self.settings.audio.sample_rate,
            channels=self.settings.audio.channels,
            device=self.settings.audio.input_device
        )
        
        # Initialize transcription service
        self.transcriber = Transcriber(
            model_size=self.settings.transcription.model,
            device=self.settings.transcription.device,
            compute_type="int8"
        )
        
        # Initialize LLM processor if enabled
        self.text_processor = None
        if self.settings.llm.enabled:
            try:
                self.text_processor = TextProcessor(api_url=self.settings.llm.api_url)
                logger.info(f"Initialized LLM processor with API at {self.settings.llm.api_url}")
            except Exception as e:
                logger.error(f"Error initializing LLM processor: {e}")
        
        # Initialize recording service
        self.recording_service = RecordingService(
            settings=self.settings,
            settings_repository=self.settings_repository,
            transcriber=self.transcriber,
            audio_recorder=self.audio_recorder
        )
    
    def _test_microphone_access(self):
        """Test microphone access to ensure we can record audio"""
        logger.info("Testing microphone access")
        try:
            # Convert 'default' to None for sounddevice
            device = None if self.settings.audio.input_device == 'default' else self.settings.audio.input_device
            sample_rate = self.settings.audio.sample_rate
            channels = self.settings.audio.channels
            
            # Get device info
            if device is None:
                default_device_idx = sd.default.device[0]
                device_info = sd.query_devices(default_device_idx) if default_device_idx is not None else None
                logger.info(f"Using default input device: {device_info['name'] if device_info else 'Unknown'}")
            else:
                device_info = sd.query_devices(device, 'input')
                logger.info(f"Using specified input device: {device_info['name']}")
            
            # Brief recording test
            logger.info(f"Testing recording with sample_rate={sample_rate}, channels={channels}, device={device_info['name'] if device_info else 'system default'}")
            duration = 0.1  # very short duration for test
            recording = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=channels,
                device=device,
                dtype='float32'
            )
            sd.wait()
            
            # Check if we got any data
            if recording is not None and len(recording) > 0:
                audio_min = np.min(recording)
                audio_max = np.max(recording)
                audio_mean = np.mean(np.abs(recording))
                logger.info(f"Microphone test successful - levels: min={audio_min:.6f}, max={audio_max:.6f}, mean={audio_mean:.6f}")
                
                # Check if audio is all zeros or very low level
                if audio_mean < 0.0001:
                    logger.warning("Microphone test indicates very low audio level - might be muted or unavailable")
            else:
                logger.warning("Microphone test failed - no data received")
                
        except Exception as e:
            logger.error(f"Error testing microphone: {e}", exc_info=True)
            logger.warning("Application may have problems with audio recording")
    
    def _create_hotkey_handler(self) -> HotkeyHandler:
        """Create the appropriate hotkey handler for the platform."""
        system = platform.system()
        
        if system == 'Windows':
            return WindowsHotkeyHandler()
        elif system == 'Darwin':
            # TODO: Implement MacOS hotkey handler
            raise NotImplementedError("MacOS support coming soon")
        else:
            raise NotImplementedError(f"Unsupported platform: {system}")
    
    def save_settings(self):
        """Save current settings."""
        logger.debug("Saving settings")
        self.settings_repository.save(self.settings)
    
    def reload_settings(self):
        """Reload settings from disk."""
        logger.debug("Reloading settings")
        old_settings = self.settings
        self.settings = self.settings_repository.load()
        
        # Track if transcription model needs reinitializing
        transcription_model_changed = (
            old_settings.transcription.model != self.settings.transcription.model or
            old_settings.transcription.device != self.settings.transcription.device
        )
        
        # Check if audio settings changed
        if (old_settings.audio.sample_rate != self.settings.audio.sample_rate or
            old_settings.audio.channels != self.settings.audio.channels or
            old_settings.audio.input_device != self.settings.audio.input_device):
            
            logger.debug("Audio settings changed, recreating audio recorder")
            # Create new audio recorder with updated settings
            self.audio_recorder = AudioRecorder(
                sample_rate=self.settings.audio.sample_rate,
                channels=self.settings.audio.channels,
                device=self.settings.audio.input_device
            )
            
            # Update recording service with new audio recorder
            self.recording_service.audio_recorder = self.audio_recorder
        
        # Update transcription settings and reinitialize model if needed
        if transcription_model_changed:
            logger.debug(f"Transcription settings changed, reinitializing model. Model: {self.settings.transcription.model}, Device: {self.settings.transcription.device}")
            try:
                # Reinitialize the transcription model with new settings
                self.transcriber = Transcriber(
                    model_size=self.settings.transcription.model,
                    device=self.settings.transcription.device,
                    compute_type="int8"
                )
                
                # Update the recording service's transcriber
                self.recording_service.transcriber = self.transcriber
                logger.info(f"Successfully reinitialized transcription model: {self.settings.transcription.model} on {self.settings.transcription.device}")
            except Exception as e:
                logger.error(f"Error reinitializing transcription model: {e}")
        else:
            # Just update the properties without reloading
            self.transcriber.model_size = self.settings.transcription.model
            self.transcriber.device = self.settings.transcription.device
        
        # Check if LLM settings changed
        if not hasattr(old_settings, 'llm') or old_settings.llm is None:
            old_llm_enabled = False
            old_llm_api_url = None
            old_use_embedded = False
            old_embedded_model_name = None
        else:
            old_llm_enabled = old_settings.llm.enabled
            old_llm_api_url = old_settings.llm.api_url
            old_use_embedded = old_settings.llm.use_embedded_model
            old_embedded_model_name = old_settings.llm.embedded_model_name
            
        if not hasattr(self.settings, 'llm') or self.settings.llm is None:
            self.settings.llm = LLMSettings()
            
        # Check if we need to update the LLM processor
        llm_settings_changed = (
            old_llm_enabled != self.settings.llm.enabled or 
            old_use_embedded != self.settings.llm.use_embedded_model or
            (self.settings.llm.enabled and not self.settings.llm.use_embedded_model and 
             old_llm_api_url != self.settings.llm.api_url) or
            (self.settings.llm.enabled and self.settings.llm.use_embedded_model and
             old_embedded_model_name != self.settings.llm.embedded_model_name)
        )
            
        # Update LLM processor if needed
        if llm_settings_changed:
            logger.debug(f"LLM settings changed, updating text processor. Use embedded: {self.settings.llm.use_embedded_model}")
            
            # Reset processors
            self.recording_service.text_processor = None
            self.recording_service.embedded_processor = None
            
            if self.settings.llm.enabled:
                # We need to update the recording service settings too
                self.recording_service.settings = self.settings
                # Re-initialize the appropriate processor based on settings
                self.recording_service._initialize_llm_processor()
        else:
            # Even if specific LLM settings didn't change, update the recording service settings
            # to ensure any other settings changes are propagated
            self.recording_service.settings = self.settings
        
        # Update appearance settings in the UI
        self._apply_appearance_settings()
            
        # Re-register hotkeys
        self.recording_service._register_hotkeys()
    
    def _apply_appearance_settings(self):
        """Apply appearance settings to any UI components managed by this service"""
        # This method can be used to propagate appearance settings changes
        # to UI components managed by this service
        logger.debug("Applying appearance settings from app service")
        # For now, this is a placeholder as most UI components are handled directly in main.py
        # but could be expanded if needed
    
    def shutdown(self):
        """Shutdown all services"""
        logger.debug("Shutting down application service")
        if hasattr(self, 'recording_service'):
            self.recording_service.shutdown()
        
        # Save settings before exit
        self.save_settings() 