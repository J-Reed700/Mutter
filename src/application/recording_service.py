from typing import Optional, Callable
from pathlib import Path
import logging
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence

from ..domain.settings import Settings
from ..infrastructure.audio.recorder import AudioRecorder
from ..infrastructure.hotkeys.base import HotkeyHandler
from ..infrastructure.transcription.transcriber import Transcriber
from ..infrastructure.llm.processor import TextProcessor, LLMProcessingResult
from ..infrastructure.llm.embedded_processor import EmbeddedTextProcessor, TORCH_AVAILABLE, TRANSFORMERS_AVAILABLE

logger = logging.getLogger(__name__)

class RecordingService(QObject):
    recording_started = Signal()
    recording_stopped = Signal(Path)  # Emits the path to the recording
    recording_failed = Signal(str)  # Emits error message
    transcription_complete = Signal(str)  # Emits the transcribed text
    llm_processing_complete = Signal(LLMProcessingResult)  # Emits the processed text result
    stop_requested = Signal()  # New signal to indicate stop was requested before processing begins
    
    def __init__(self, settings, settings_repository, transcriber, audio_recorder):
        """Initialize the recording service.
        
        Args:
            settings: Application settings object
            settings_repository: Repository for saving settings
            transcriber: Transcription service
            audio_recorder: Audio recorder instance
        """
        logger.debug("Initializing recording service")
        super().__init__()
        self.settings = settings
        self.settings_repository = settings_repository
        self.transcriber = transcriber
        self.audio_recorder = audio_recorder
        
        # Create platform-specific hotkey handler
        self.hotkey_handler = self._create_hotkey_handler()
        
        # Connect signals
        if self.hotkey_handler:
            self.hotkey_handler.hotkey_pressed.connect(self._on_hotkey_pressed)
            self.hotkey_handler.hotkey_released.connect(self._on_hotkey_released)
            self.hotkey_handler.process_text_hotkey_pressed.connect(self._on_process_text_hotkey)
        
        # Initialize LLM processor if enabled
        self.text_processor = None
        self.embedded_processor = None
        if self.settings.llm.enabled:
            self._initialize_llm_processor()
        
        # State flags
        self.is_recording = False
        self.last_transcription = ""
        
        # Log current audio settings
        self._log_audio_settings()
    
    def _log_audio_settings(self):
        """Log current audio settings for debugging"""
        logger.debug(f"Current audio settings: device={self.settings.audio.input_device}, "
                     f"sample_rate={self.settings.audio.sample_rate}, "
                     f"channels={self.settings.audio.channels}")
        if self.audio_recorder:
            logger.debug(f"AudioRecorder: device={self.audio_recorder.device}, "
                         f"sample_rate={self.audio_recorder.sample_rate}, "
                         f"channels={self.audio_recorder.channels}")
    
    def _initialize_llm_processor(self):
        """Initialize the LLM processor"""
        try:
            # Check if we're supposed to use embedded model but dependencies aren't available
            if self.settings.llm.use_embedded_model and (not TORCH_AVAILABLE or not TRANSFORMERS_AVAILABLE):
                logger.warning("Embedded LLM dependencies (PyTorch/Transformers) not available. "
                              "Automatically falling back to external API.")
                # Automatically switch to external API
                self.settings.llm.use_embedded_model = False
                # Try to save this change to settings for future runs
                try:
                    self.settings_repository.save(self.settings)
                    logger.info("Updated settings to use external API for future runs")
                except Exception as e:
                    logger.error(f"Could not save updated LLM settings: {e}")
            
            if self.settings.llm.use_embedded_model:
                # Initialize embedded processor
                logger.info("Initializing embedded LLM processor")
                self.embedded_processor = EmbeddedTextProcessor()
                if self.settings.llm.embedded_model_name:
                    self.embedded_processor.model_name = self.settings.llm.embedded_model_name
                # Make sure to set text_processor to None when using embedded
                self.text_processor = None
                logger.info(f"Embedded LLM processor initialized with model: {self.settings.llm.embedded_model_name}")
            else:
                # Initialize external API processor
                logger.info("Initializing external LLM processor")
                self.text_processor = TextProcessor(api_url=self.settings.llm.api_url)
                # Make sure to set embedded_processor to None when using external
                self.embedded_processor = None
                logger.info(f"External LLM processor initialized with API URL: {self.settings.llm.api_url}")
            
            logger.info("LLM processor initialized")
        except Exception as e:
            logger.error(f"Failed to initialize LLM processor: {e}")
            self.text_processor = None
            self.embedded_processor = None
    
    def _register_hotkeys(self):
        """Register the hotkeys from settings"""
        self.hotkey_handler.register_hotkey(self.settings.hotkeys.record_key)
        if self.settings.hotkeys.pause_key:
            self.hotkey_handler.register_hotkey(self.settings.hotkeys.pause_key)
        if self.settings.hotkeys.process_text_key:
            self.hotkey_handler.register_process_text_hotkey(self.settings.hotkeys.process_text_key)
    
    def set_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Set a new hotkey for recording
        
        Args:
            key_sequence: The new key sequence to use
            
        Returns:
            bool: True if the hotkey was successfully registered, False otherwise
        """
        logger.debug(f"Setting new record hotkey: {key_sequence.toString()}")
        
        try:
            # Unregister old record hotkeys only (keep other hotkeys)
            old_hotkeys = []
            for key in list(self.hotkey_handler.registered_hotkeys.keys()):
                # Skip process text hotkey and exit hotkey
                if (self.hotkey_handler.registered_process_text_hotkey is not None and 
                    key == self.hotkey_handler.registered_process_text_hotkey):
                    continue
                    
                if key.toString() == "Ctrl+Shift+Q":  # Exit hotkey
                    continue
                    
                old_hotkeys.append(key)
                
            # Unregister old recording hotkeys
            for key in old_hotkeys:
                logger.debug(f"Unregistering old hotkey: {key.toString()}")
                self.hotkey_handler.unregister_hotkey(key)
            
            # Register new hotkey
            success = self.hotkey_handler.register_hotkey(key_sequence)
            
            if success:
                # Update settings
                self.settings.hotkeys.record_key = key_sequence
                # Make sure the settings are saved
                self.settings_repository.save(self.settings)
                logger.info(f"Successfully registered record hotkey: {key_sequence.toString()}")
            else:
                logger.warning(f"Failed to register record hotkey: {key_sequence.toString()}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error setting record hotkey: {e}", exc_info=True)
            return False
    
    def set_process_text_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Set a new hotkey for processing clipboard text
        
        Args:
            key_sequence: The new key sequence to use
            
        Returns:
            bool: True if the hotkey was successfully registered, False otherwise
        """
        logger.debug(f"Setting new process text hotkey: {key_sequence.toString()}")
        
        try:
            # Unregister old process text hotkey if it exists
            if (self.hotkey_handler.registered_process_text_hotkey is not None and
                self.hotkey_handler.registered_process_text_hotkey in self.hotkey_handler.registered_hotkeys):
                logger.debug(f"Unregistering old process text hotkey: {self.hotkey_handler.registered_process_text_hotkey.toString()}")
                self.hotkey_handler.unregister_hotkey(self.hotkey_handler.registered_process_text_hotkey)
            
            # Register new process text hotkey
            success = self.hotkey_handler.register_process_text_hotkey(key_sequence)
            
            if success:
                # Update settings
                self.settings.hotkeys.process_text_key = key_sequence
                # Make sure the settings are saved
                self.settings_repository.save(self.settings)
                logger.info(f"Successfully registered process text hotkey: {key_sequence.toString()}")
            else:
                logger.warning(f"Failed to register process text hotkey: {key_sequence.toString()}")
                
            return success
                
        except Exception as e:
            logger.error(f"Error setting process text hotkey: {e}", exc_info=True)
            return False
    
    def _on_hotkey_pressed(self):
        """Handle hotkey press event"""
        logger.debug("Hotkey pressed, starting recording")
        self.start_recording()
    
    def _on_hotkey_released(self):
        """Handle hotkey release event"""
        logger.debug("Hotkey released, stopping recording - emitting stop_requested signal first")
        
        # Emit signal to show toast notification before any processing begins
        self.stop_requested.emit()
        
        # Now stop the recording
        self.stop_recording()
    
    def stop_recording(self):
        """Stop current recording and transcribe the audio."""
        if not self.is_recording:
            logger.debug("No recording in progress to stop")
            return None
            
        logger.info("Stopping recording")
        
        try:
            recording_path = self.audio_recorder.stop_recording()
            self.is_recording = False
            
            if recording_path is None:
                logger.warning("No audio recorded or save failed")
                self.recording_failed.emit("No audio recorded")
                return None
                
            self.recording_stopped.emit(recording_path)
            
            # Transcribe the recording
            logger.info(f"Transcribing recording from {recording_path}")
            result = self.transcriber.transcribe(
                recording_path,
                language=self.settings.transcription.language
            )
            
            if result:
                # Handle both TranscriptionResult object and string returns
                if hasattr(result, 'text'):
                    transcribed_text = result.text
                else:
                    # Assume result is already a string
                    transcribed_text = result
                
                self.last_transcription = transcribed_text
                logger.info(f"Transcription complete: {transcribed_text[:50]}...")
                self.transcription_complete.emit(transcribed_text)
                
                # If LLM processing is enabled and we have a processing method available, process the text
                if (self.settings.llm.enabled and 
                    (self.text_processor is not None or self.embedded_processor is not None)):
                    self._process_text_with_llm(transcribed_text)
            else:
                logger.warning("Transcription failed")
                self.recording_failed.emit("Transcription failed")
            
            return recording_path
                
        except Exception as e:
            logger.error(f"Error stopping recording: {e}", exc_info=True)
            self.is_recording = False
            self.recording_failed.emit(str(e))
            return None
    
    def _on_process_text_hotkey(self):
        """Handle process text hotkey press event"""
        logger.debug("Process text hotkey pressed")
        if not self.last_transcription:
            logger.warning("No transcription available to process")
            return
            
        self._process_text_with_llm(self.last_transcription)
    
    def _process_text_with_llm(self, text: str):
        """Process text using the LLM
        
        Args:
            text: Text to process
        """
        # First check if we're using the embedded model
        if self.settings.llm.use_embedded_model and self.embedded_processor:
            logger.debug(f"Processing text with embedded LLM: {text[:50]}...")
            
            try:
                processing_type = self.settings.llm.default_processing_type
                
                if processing_type == "summarize" or processing_type == "custom":
                    # For embedded processor, we just always use summarize
                    result = self.embedded_processor.summarize(text)
                else:
                    # Default to summarize for embedded processor
                    result = self.embedded_processor.summarize(text)
                    
                if result:
                    logger.info(f"Embedded LLM processing complete: {result.processing_type}")
                    self.llm_processing_complete.emit(result)
                else:
                    logger.warning("Embedded LLM processing returned no result")
                    # Try fallback to external API if embedded processing failed
                    if self.text_processor:
                        logger.info("Falling back to external API for LLM processing")
                        self._process_with_external_api(text)
            except Exception as e:
                logger.error(f"Error processing text with embedded LLM: {e}")
                # Try fallback to external API if embedded processing failed
                if self.text_processor:
                    logger.info("Falling back to external API for LLM processing after error")
                    self._process_with_external_api(text)
            
            return
            
        # If not using embedded model, try external processor
        if not self.text_processor:
            logger.warning("LLM processor not initialized")
            return
            
        self._process_with_external_api(text)
    
    def _process_with_external_api(self, text: str):
        """Process text using the external API processor"""
        try:
            processing_type = self.settings.llm.default_processing_type
            
            if processing_type == "summarize":
                result = self.text_processor.summarize(text)
                if result:
                    logger.info("Text summarization complete")
                    self.llm_processing_complete.emit(result)
                else:
                    logger.warning("Text summarization failed")
            elif processing_type == "custom" and self.settings.llm.custom_prompt:
                # Use custom prompt if provided
                result = self.text_processor.process_with_prompt(
                    text, 
                    self.settings.llm.custom_prompt
                )
                if result:
                    logger.info("Custom text processing complete")
                    self.llm_processing_complete.emit(result)
                else:
                    logger.warning("Custom text processing failed")
            else:
                # Default to summarize if no valid processing type
                result = self.text_processor.summarize(text)
                if result:
                    logger.info("Default text summarization complete")
                    self.llm_processing_complete.emit(result)
                else:
                    logger.warning("Default text processing failed")
        except Exception as e:
            logger.error(f"Error processing text with external LLM API: {e}")
    
    def shutdown(self):
        """Clean up resources before shutdown"""
        logger.debug("Shutting down recording service")
        # Unregister all hotkeys
        if hasattr(self.hotkey_handler, 'shutdown'):
            self.hotkey_handler.shutdown()
    
    def _create_hotkey_handler(self):
        """Create the appropriate hotkey handler for the current platform"""
        import platform
        system = platform.system()
        
        if system == 'Windows':
            from ..infrastructure.hotkeys.windows import WindowsHotkeyHandler
            return WindowsHotkeyHandler()
        elif system == 'Darwin':  # macOS
            # Future implementation
            logger.warning("macOS hotkey handler not implemented")
            return None
        elif system == 'Linux':
            # Future implementation
            logger.warning("Linux hotkey handler not implemented")
            return None
        else:
            logger.warning(f"Unsupported platform: {system}")
            return None
    
    def start_recording(self):
        """Start recording audio and transcribing it."""
        if self.is_recording:
            logger.debug("Recording already in progress")
            return
            
        logger.info("Starting recording")
        
        # First verify the audio recorder is initialized correctly
        if not self.audio_recorder:
            logger.error("Audio recorder not initialized")
            self.recording_failed.emit("Audio recorder not initialized")
            return
            
        # Log audio settings for debugging
        self._log_audio_settings()
            
        try:
            # Start the actual recording
            self.audio_recorder.start_recording()
            self.is_recording = True
            self.recording_started.emit()
        except Exception as e:
            logger.error(f"Error starting recording: {e}", exc_info=True)
            self.is_recording = False
            self.recording_failed.emit(str(e)) 