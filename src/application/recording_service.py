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
        
        # Initialize LLM processor if enabled
        self.text_processor = None
        if self.settings.llm.enabled:
            self._initialize_llm_processor()
        
        # State flags
        self.is_recording = False
        self.last_transcription = ""
    
    def _initialize_llm_processor(self):
        """Initialize the LLM processor"""
        try:
            self.text_processor = TextProcessor(api_url=self.settings.llm.api_url)
            logger.info("LLM processor initialized")
        except Exception as e:
            logger.error(f"Failed to initialize LLM processor: {e}")
            self.text_processor = None
    
    def _register_hotkeys(self):
        """Register the hotkeys from settings"""
        self.hotkey_handler.register_hotkey(self.settings.hotkeys.record_key)
        if self.settings.hotkeys.pause_key:
            self.hotkey_handler.register_hotkey(self.settings.hotkeys.pause_key)
        if self.settings.hotkeys.process_text_key:
            self.hotkey_handler.register_process_text_hotkey(self.settings.hotkeys.process_text_key)
    
    def set_hotkey(self, key_sequence: QKeySequence):
        """Set a new hotkey for recording
        
        Args:
            key_sequence: The new key sequence to use
        """
        logger.debug(f"Setting new hotkey: {key_sequence.toString()}")
        
        # Unregister old hotkeys
        for key in list(self.hotkey_handler.registered_hotkeys.keys()):
            self.hotkey_handler.unregister_hotkey(key)
        
        # Register new hotkey
        self.hotkey_handler.register_hotkey(key_sequence)
        
        # Update settings
        self.settings.hotkeys.record_key = key_sequence
    
    def set_process_text_hotkey(self, key_sequence: QKeySequence):
        """Set a new hotkey for text processing
        
        Args:
            key_sequence: The new key sequence to use
        """
        logger.debug(f"Setting new process text hotkey: {key_sequence.toString()}")
        
        # Register new hotkey
        self.hotkey_handler.register_process_text_hotkey(key_sequence)
        
        # Update settings
        self.settings.hotkeys.process_text_key = key_sequence
    
    def _on_hotkey_pressed(self):
        """Handle hotkey press event"""
        logger.debug("Hotkey pressed, starting recording")
        self.audio_recorder.start_recording()
        self.recording_started.emit()
    
    def _on_hotkey_released(self):
        """Handle hotkey release event"""
        logger.debug("Hotkey released, stopping recording")
        recording_path = self.audio_recorder.stop_recording()
        
        if recording_path is None:
            self.recording_failed.emit("No audio recorded")
            return
            
        self.recording_stopped.emit(recording_path)
        
        # Transcribe the recording
        result = self.transcriber.transcribe(
            recording_path,
            language=self.settings.transcription.language if self.settings.transcription.language != "auto" else None
        )
        
        if result:
            self.last_transcription = result.text
            self.transcription_complete.emit(result.text)
            
            # Auto-process with LLM if enabled
            if self.settings.llm.enabled and self.settings.llm.default_processing_type and self.text_processor:
                self._process_text_with_llm(result.text)
        else:
            self.recording_failed.emit("Transcription failed")
    
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
        if not self.text_processor:
            logger.warning("LLM processor not initialized")
            return
            
        logger.debug(f"Processing text with LLM: {text[:50]}...")
        
        try:
            processing_type = self.settings.llm.default_processing_type
            
            if processing_type == "summarize":
                result = self.text_processor.summarize(text, model=self.settings.llm.model)
            elif processing_type == "custom":
                # Get the first custom prompt template
                template_name = next(iter(self.settings.llm.custom_prompt_templates.keys()))
                template = self.settings.llm.custom_prompt_templates[template_name]
                result = self.text_processor.process_with_prompt(text, template, model=self.settings.llm.model)
            else:
                # Default to summarize
                result = self.text_processor.summarize(text, model=self.settings.llm.model)
                
            if result:
                logger.info(f"LLM processing complete: {result.processing_type}")
                self.llm_processing_complete.emit(result)
            else:
                logger.warning("LLM processing returned no result")
        except Exception as e:
            logger.error(f"Error processing text with LLM: {e}")
    
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