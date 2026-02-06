from typing import Optional, Callable
from pathlib import Path
import logging
from datetime import datetime
from uuid import uuid4
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence
import platform
import os

# Domain imports
from ...domain.settings import Settings
from ...domain.entities.recording import Recording
from ...domain.entities.transcription import Transcription
from ...domain.value_objects.audio_metadata import AudioMetadata
from ...domain.value_objects.transcription_metadata import TranscriptionMetadata
from ...domain.events.recording_events import RecordingStopped, RecordingFailed
from ...domain.events.processing_events import (
    TranscriptionStarted,
    TranscriptionCompleted,
    TranscriptionFailed,
)

# Infrastructure imports
from ..audio.recorder import AudioRecorder
from ..hotkeys.base import HotkeyHandler
from ..transcription.transcriber import Transcriber
from ..llm.processor import TextProcessor, LLMProcessingResult

logger = logging.getLogger(__name__)

class RecordingService(QObject):
    recording_started = Signal()
    recording_stopped = Signal(Path)  # Emits the path to the recording
    recording_failed = Signal(str)  # Emits error message
    transcription_complete = Signal(str)  # Emits the transcribed text
    llm_processing_complete = Signal(LLMProcessingResult)  # Emits the processed text result
    
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
            
            # Connect recording state reset signal (emitted when stale keys are cleaned up)
            if hasattr(self.hotkey_handler, 'recording_state_reset'):
                self.hotkey_handler.recording_state_reset.connect(self._on_hotkey_state_reset)
        
        # Initialize LLM processor if enabled
        self.text_processor = None
        if self.settings.llm and self.settings.llm.enabled:
            self._initialize_llm_processor()
        
        # State flags
        self.is_recording = False
        self.last_transcription = ""
        
        # Log current audio settings
        self._log_audio_settings()
    
    def set_audio_recorder(self, audio_recorder):
        """Update the audio recorder instance.
        
        Args:
            audio_recorder: New AudioRecorder instance
        """
        logger.info("Hot-swapping AudioRecorder")
        self.audio_recorder = audio_recorder
        
    def set_transcriber(self, transcriber):
        """Update the transcriber instance.
        
        Args:
            transcriber: New Transcriber instance
        """
        logger.info("Hot-swapping Transcriber")
        self.transcriber = transcriber

    def _log_audio_settings(self):
        """Log current audio settings for debugging"""
        logger.debug(f"Current audio settings: device={self.settings.audio.input_device}, "
                     f"sample_rate={self.settings.audio.sample_rate}, "
                     f"channels={self.settings.audio.channels}")
        if self.audio_recorder:
            logger.debug(f"AudioRecorder: device={self.audio_recorder.device}, "
                         f"sample_rate={self.audio_recorder.sample_rate}, "
                         f"channels={self.audio_recorder.channels}")
        else:
            logger.warning("AudioRecorder is not initialized")
    
    def _initialize_llm_processor(self):
        """Initialize the LLM processor based on settings"""
        if not self.settings.llm or not self.settings.llm.enabled:
            logger.info("LLM processing is disabled in settings")
            self.text_processor = None
            return

        try:
            api_url = self.settings.llm.api_url or "http://localhost:11434/v1"
            username = getattr(self.settings.llm, 'api_username', '') or ''
            password = getattr(self.settings.llm, 'api_password', '') or ''

            logger.info(f"Initializing LLM processor at {api_url}" + (" (with auth)" if username else ""))
            self.text_processor = TextProcessor(api_url=api_url, username=username, password=password)
            if self.text_processor.available:
                logger.info("LLM processor initialized successfully")
            else:
                logger.warning(f"LLM API not available at {api_url}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM processor: {e}")
            self.text_processor = None
    
    def _register_hotkeys(self):
        """Register the hotkeys from settings"""
        # Log all hotkeys being registered
        logger.info(f"Registering hotkeys from settings: "
                   f"record_key={self.settings.hotkeys.record_key.toString()}, "
                   f"quit_key={self.settings.hotkeys.quit_key.toString() if self.settings.hotkeys.quit_key else 'None'}, "
                   f"process_text_key={self.settings.hotkeys.process_text_key.toString() if self.settings.hotkeys.process_text_key else 'None'}")
        
        # Register record hotkey
        self.hotkey_handler.register_hotkey(self.settings.hotkeys.record_key)
        
        # Register process text key if configured
        # Avoid registering as both a regular hotkey and a process text hotkey
        if self.settings.hotkeys.process_text_key:
            # First check if this key is already registered as a regular hotkey
            if self.settings.hotkeys.process_text_key in self.hotkey_handler.registered_hotkeys:
                logger.warning(f"Process text key {self.settings.hotkeys.process_text_key.toString()} "
                               f"is already registered as a regular hotkey. Unregistering first.")
                self.hotkey_handler.unregister_hotkey(self.settings.hotkeys.process_text_key)
                
            # Now register it as a process text hotkey
            self.hotkey_handler.register_process_text_hotkey(self.settings.hotkeys.process_text_key)
            
        # Register the exit/quit hotkey
        if self.settings.hotkeys.quit_key:
            exit_hotkey = self.settings.hotkeys.quit_key
            logger.info(f"Using quit_key from settings: {exit_hotkey.toString()}")
            if exit_hotkey not in self.hotkey_handler.registered_hotkeys:
                success = self.hotkey_handler.register_hotkey(exit_hotkey)
                if success:
                    # Set the exit_hotkey property so the handler knows this is the exit hotkey
                    self.hotkey_handler.exit_hotkey = exit_hotkey
                    logger.info(f"Successfully registered exit hotkey ({exit_hotkey.toString()})")
                else:
                    logger.warning(f"Failed to register exit hotkey ({exit_hotkey.toString()})")
        else:
            # Use default Ctrl+Shift+Q if no quit key is configured
            exit_hotkey = QKeySequence("Ctrl+Shift+Q")
            logger.info(f"No quit_key in settings, using default: {exit_hotkey.toString()}")
            if exit_hotkey not in self.hotkey_handler.registered_hotkeys:
                success = self.hotkey_handler.register_hotkey(exit_hotkey)
                if success:
                    # Set the exit_hotkey property so the handler knows this is the exit hotkey
                    self.hotkey_handler.exit_hotkey = exit_hotkey
                    logger.info("Successfully registered default exit hotkey (Ctrl+Shift+Q)")
                else:
                    logger.warning("Failed to register default exit hotkey (Ctrl+Shift+Q)")
                # Save this default to settings
                self.settings.hotkeys.quit_key = exit_hotkey
                self.settings_repository.save(self.settings)
    
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
                    
                if key == self.settings.hotkeys.quit_key:  # Quit hotkey
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
        """Set a new hotkey for processing text
        
        Args:
            key_sequence: The new key sequence to use
            
        Returns:
            bool: True if the hotkey was successfully registered, False otherwise
        """
        logger.debug(f"Setting new process text hotkey: {key_sequence.toString()}")
        
        try:
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
    
    def set_quit_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Set a new hotkey for quitting the application
        
        Args:
            key_sequence: The new key sequence to use
            
        Returns:
            bool: True if the hotkey was successfully registered, False otherwise
        """
        logger.debug(f"Setting new quit hotkey: {key_sequence.toString()}")
        
        try:
            # Find and unregister the old exit hotkey if it exists
            old_exit_hotkey = None
            for key in list(self.hotkey_handler.registered_hotkeys.keys()):
                if key == self.settings.hotkeys.quit_key:
                    old_exit_hotkey = key
                    break
            
            if old_exit_hotkey:
                logger.debug(f"Unregistering old quit hotkey: {old_exit_hotkey.toString()}")
                self.hotkey_handler.unregister_hotkey(old_exit_hotkey)
            
            # Register the new quit hotkey
            success = self.hotkey_handler.register_hotkey(key_sequence)
            
            if success:
                # Update settings
                self.settings.hotkeys.quit_key = key_sequence
                # Set the exit_hotkey property so the handler knows this is the exit hotkey
                self.hotkey_handler.exit_hotkey = key_sequence
                # Make sure the settings are saved
                self.settings_repository.save(self.settings)
                logger.info(f"Successfully registered quit hotkey: {key_sequence.toString()}")
            else:
                logger.warning(f"Failed to register quit hotkey: {key_sequence.toString()}")
                
            return success
                
        except Exception as e:
            logger.error(f"Error setting quit hotkey: {e}", exc_info=True)
            return False
    
    def _on_hotkey_pressed(self):
        """Handle hotkey press event"""
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def _on_hotkey_released(self):
        """Handle hotkey release event.

        Recording uses toggle-on-press behavior (_on_hotkey_pressed handles start/stop).
        Release events are logged but do not affect recording state.
        """
        logger.debug("Hotkey released (no action - using toggle-on-press mode)")
    
    def _on_hotkey_state_reset(self):
        """Handle hotkey state reset signal from stale key cleanup.
        
        This is called when the hotkey handler detects that keys have been 'held' 
        for too long (e.g., due to sleep/wake or USB disconnect) and resets its state.
        We need to sync our recording state accordingly.
        """
        logger.warning("Hotkey handler state was reset due to stale key cleanup")
        
        # If we think we're recording but the hotkey handler reset its state,
        # we should stop the recording to maintain consistency
        if self.is_recording:
            logger.warning("Recording was in progress during hotkey state reset - stopping recording")
            self.stop_recording()
    
    def _delete_recording_file(self, file_path: Path):
        """Delete the recording file after it's been transcribed.
        
        Args:
            file_path: Path to the recording file
        """
        try:
            if file_path and file_path.exists():
                logger.debug(f"Deleting recording file: {file_path}")
                file_path.unlink()
                logger.info(f"Successfully deleted recording file: {file_path}")
            else:
                logger.debug(f"Recording file not found or invalid path: {file_path}")
        except Exception as e:
            logger.error(f"Error deleting recording file {file_path}: {e}")
            
    def stop_recording(self):
        """Stop current recording and transcribe the audio."""
        if not self.is_recording:
            logger.debug("No recording in progress to stop")
            return None
            
        logger.info("Stopping recording")
        
        if not self.audio_recorder:
            logger.warning("No audio recorder available to stop")
            self.is_recording = False
            return None
        
        try:
            recording_path = self.audio_recorder.stop_recording()
            self.is_recording = False
            
            if recording_path is None:
                logger.warning("No audio recorded or save failed")
                self.recording_failed.emit("No audio recorded")
                # Create and emit a domain event
                recording_failed_event = RecordingFailed(
                    error_message="No audio recorded or save failed"
                )
                logger.debug(f"Created domain event: {recording_failed_event}")
                return None
                
            # Emit UI signal
            self.recording_stopped.emit(recording_path)
            
            # Create and use domain entity and events
            # Get duration and other metadata
            duration_seconds = self.audio_recorder.get_last_recording_duration()
            audio_info = self.audio_recorder.get_last_recording_info()
            
            # Create AudioMetadata value object
            audio_metadata = AudioMetadata(
                sample_rate=self.audio_recorder.sample_rate,
                channels=self.audio_recorder.channels,
                bit_depth=16,  # Typically 16-bit for WAV
                format="WAV",
                device_name=str(self.audio_recorder.device),
                file_size_bytes=recording_path.stat().st_size if recording_path.exists() else 0
            )
            
            # Create Recording entity
            recording_id = uuid4()
            recording = Recording(
                id=recording_id,
                file_path=recording_path,
                created_at=datetime.now(),
                duration_seconds=duration_seconds,
                metadata=audio_metadata
            )
            
            # Create and log domain event
            recording_stopped_event = RecordingStopped(
                recording_id=recording_id,
                file_path=recording_path,
                duration_seconds=duration_seconds
            )
            logger.debug(f"Created domain event: {recording_stopped_event}")
            
            # Store recording entity for later reference
            self.last_recording = recording
            
            # Transcribe the recording
            logger.info(f"Transcribing recording from {recording_path}")
            
            # Create and log domain event
            transcription_started_event = TranscriptionStarted(
                recording_id=recording_id
            )
            logger.debug(f"Created domain event: {transcription_started_event}")
            
            # Actual transcription
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
                
                # Create transcription entity
                processing_time_ms = self.transcriber.get_last_processing_time() if hasattr(self.transcriber, 'get_last_processing_time') else 0
                
                # Create TranscriptionMetadata value object
                transcription_metadata = TranscriptionMetadata(
                    model_name=self.settings.transcription.model,
                    language=self.settings.transcription.language,
                    confidence_score=0.9,  # Placeholder
                    processing_time_ms=processing_time_ms,
                    device=self.settings.transcription.device,
                    word_timestamps=False,
                    model_version=self.transcriber.model_version if hasattr(self.transcriber, 'model_version') else None
                )
                
                # Create Transcription entity
                transcription_id = uuid4()
                transcription = Transcription(
                    id=transcription_id,
                    recording_id=recording_id,
                    text=transcribed_text,
                    created_at=datetime.now(),
                    metadata=transcription_metadata
                )
                
                # Store for later reference
                self.last_transcription = transcribed_text
                self.last_transcription_entity = transcription
                
                # Update recording with transcription reference
                recording.transcription_id = transcription_id
                
                # Create and log domain event
                transcription_completed_event = TranscriptionCompleted(
                    recording_id=recording_id,
                    transcription_id=transcription_id,
                    text_length=len(transcribed_text),
                    processing_time_ms=processing_time_ms
                )
                logger.debug(f"Created domain event: {transcription_completed_event}")
                
                # Process with LLM if enabled
                final_text = transcribed_text
                llm_exists = self.settings.llm is not None
                llm_enabled = self.settings.llm.enabled if llm_exists else False
                logger.debug(f"LLM check: llm_exists={llm_exists}, llm_enabled={llm_enabled}")
                if self.settings.llm and self.settings.llm.enabled:
                    logger.info("LLM processing is enabled - processing transcription")
                    llm_result = self._process_text_with_llm_sync(transcribed_text, transcription_id)
                    if llm_result and llm_result.processed_text:
                        final_text = llm_result.processed_text
                        logger.info(f"LLM processed text: {final_text[:50]}...")
                        self.llm_processing_complete.emit(llm_result)
                
                # Emit UI signal with final text (LLM processed or original)
                logger.info(f"Transcription complete: {final_text[:50]}...")
                self.transcription_complete.emit(final_text)
                
                # Delete the recording file after successful transcription
                self._delete_recording_file(recording_path)
                
            else:
                logger.warning("Transcription failed")
                self.recording_failed.emit("Transcription failed")
                
                # Create and log domain event
                transcription_failed_event = TranscriptionFailed(
                    recording_id=recording_id,
                    error_message="Transcription failed or returned empty result"
                )
                logger.debug(f"Created domain event: {transcription_failed_event}")
                
                # Delete the recording file even if transcription failed
                self._delete_recording_file(recording_path)
            
            return recording_path
                
        except Exception as e:
            logger.error(f"Error stopping recording: {e}", exc_info=True)
            self.is_recording = False
            self.recording_failed.emit(str(e))
            
            # Create and log domain event
            recording_failed_event = RecordingFailed(
                error_message=str(e),
                exception=e
            )
            logger.debug(f"Created domain event: {recording_failed_event}")
            
            return None
    
    def _on_process_text_hotkey(self):
        """Handle process text hotkey press event"""
        if not self.last_transcription:
            logger.warning("No transcription available to process")
            return
            
        self._process_text_with_llm(self.last_transcription)
    
    def _process_text_with_llm_sync(self, text, transcription_id=None) -> Optional[LLMProcessingResult]:
        """Process text using the LLM synchronously
        
        Args:
            text: Text to process
            transcription_id: ID of the transcription entity if available
            
        Returns:
            LLMProcessingResult or None if processing failed
        """
        if not self.settings.llm or not self.settings.llm.enabled:
            logger.info("LLM processing is disabled - skipping")
            return None
            
        if not self.text_processor or not self.text_processor.available:
            logger.warning("LLM processor not available - trying to initialize")
            self._initialize_llm_processor()
            if not self.text_processor or not self.text_processor.available:
                logger.error("Failed to initialize LLM processor")
                return None
        
        try:
            # Get the custom prompt from settings
            prompt_template = self.settings.llm.custom_prompt or "Fix any grammar, spelling, and punctuation errors in the following text. Keep the meaning exactly the same. Only output the corrected text, nothing else:\n\n{text}"
            model = self.settings.llm.model or "llama3.2"
            
            logger.info(f"Processing text with LLM (model: {model})")
            logger.debug(f"Prompt template: {prompt_template[:100]}...")
            
            result = self.text_processor.process_with_prompt(text, prompt_template, model)
            
            if result and result.processed_text:
                logger.info("LLM processing completed successfully")
                return result
            else:
                logger.warning("LLM processing returned empty result")
                return None
                
        except Exception as e:
            logger.error(f"Error processing text with LLM: {e}")
            return None
    
    def _process_text_with_llm(self, text, transcription_id=None):
        """Process text using the LLM (async version that emits signals)
        
        Args:
            text: Text to process
            transcription_id: ID of the transcription entity if available
        """
        result = self._process_text_with_llm_sync(text, transcription_id)
        
        if result:
            self.llm_processing_complete.emit(result)
        else:
            # Emit result with original text if processing failed
            model = self.settings.llm.model if self.settings.llm else "unknown"
            fallback_result = LLMProcessingResult(
                original_text=text,
                processed_text=text,
                processing_type="error",
                model_name=model
            )
            self.llm_processing_complete.emit(fallback_result)
    
    def shutdown(self):
        """Clean up resources before shutdown.
        
        Note: The service_manager handles stopping any active recording before
        calling this method, so we only need to clean up resources here.
        """
        logger.debug("Shutting down recording service")
        
        # Stop any ongoing recording first (defensive - service_manager should handle this)
        if self.is_recording:
            logger.info("Stopping ongoing recording during shutdown")
            try:
                self.audio_recorder.stop_recording()
            except Exception as e:
                logger.error(f"Error stopping recording during shutdown: {e}")
            self.is_recording = False
        
        # Clear audio recorder buffer to free memory
        if self.audio_recorder:
            try:
                self.audio_recorder._clear_audio_buffer()
            except Exception as e:
                logger.error(f"Error clearing audio recorder buffer: {e}")
        
        # Shutdown hotkey handler (stops listener, cleanup timer, sleep/wake observer)
        if self.hotkey_handler and hasattr(self.hotkey_handler, 'shutdown'):
            try:
                self.hotkey_handler.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down hotkey handler: {e}")
        
        logger.debug("Recording service shutdown complete")
    
    def _create_hotkey_handler(self):
        """Create the appropriate hotkey handler for the current platform"""
        system = platform.system()
        
        if system == 'Windows':
            from ..hotkeys.windows import WindowsHotkeyHandler
            return WindowsHotkeyHandler()
        elif system == 'Darwin':  # macOS
            from ..hotkeys.macos import MacOSHotkeyHandler
            return MacOSHotkeyHandler()
        elif system == 'Linux':
            session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
            
            if session_type == 'wayland':
                logger.info("Detected Wayland session, using evdev hotkey handler")
                from ..hotkeys.linux_wayland import WaylandHotkeyHandler
                return WaylandHotkeyHandler()
            
            try:
                from ..hotkeys.linux import LinuxHotkeyHandler
                return LinuxHotkeyHandler()
            except ImportError as e:
                logger.warning(f"pynput failed ({e}), trying evdev handler")
                from ..hotkeys.linux_wayland import WaylandHotkeyHandler
                return WaylandHotkeyHandler()
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

    def update_settings(self, settings):
        """Update the service with new settings.
        
        Args:
            settings: New application settings object
        """
        logger.debug("Updating recording service settings")
        
        # Store previous hotkey settings for comparison
        old_record_key = self.settings.hotkeys.record_key
        old_quit_key = self.settings.hotkeys.quit_key
        old_process_text_key = self.settings.hotkeys.process_text_key
        
        # Update service settings
        self.settings = settings
        
        # Update components that depend on settings
        if self.settings.llm and self.settings.llm.enabled:
            self._initialize_llm_processor()
        else:
            self.text_processor = None
        
        # Update audio recorder settings if they changed
        if (self.audio_recorder.sample_rate != self.settings.audio.sample_rate or
            self.audio_recorder.channels != self.settings.audio.channels or
            self.audio_recorder.device != self.settings.audio.input_device):
            
            logger.debug(f"Updating audio recorder settings: "
                        f"device={self.settings.audio.input_device}, "
                        f"sample_rate={self.settings.audio.sample_rate}, "
                        f"channels={self.settings.audio.channels}")
            
            self.audio_recorder.update_settings(
                sample_rate=self.settings.audio.sample_rate,
                channels=self.settings.audio.channels,
                device=self.settings.audio.input_device
            )
        
        # Check if any hotkeys changed and re-register if needed
        if (old_record_key != self.settings.hotkeys.record_key or
            old_quit_key != self.settings.hotkeys.quit_key or
            old_process_text_key != self.settings.hotkeys.process_text_key):
            logger.info("Hotkey settings changed, re-registering hotkeys")
            
            # Unregister all existing hotkeys first
            if self.hotkey_handler:
                for key in list(self.hotkey_handler.registered_hotkeys.keys()):
                    logger.debug(f"Unregistering hotkey: {key.toString()}")
                    self.hotkey_handler.unregister_hotkey(key)
                
                # Also unregister process text hotkey if it exists
                if self.hotkey_handler.registered_process_text_hotkey:
                    logger.debug(f"Unregistering process text hotkey: {self.hotkey_handler.registered_process_text_hotkey.toString()}")
                    hotkey_id = self.hotkey_handler.process_text_hotkey_id
                    if hotkey_id is not None:
                        self.hotkey_handler.unregister_hotkey(self.hotkey_handler.registered_process_text_hotkey)
                    self.hotkey_handler.registered_process_text_hotkey = None
                    self.hotkey_handler.process_text_hotkey_id = None
            
            # Register new hotkeys
            self._register_hotkeys()
        
        # Log updated settings
        self._log_audio_settings()
        
        return True
