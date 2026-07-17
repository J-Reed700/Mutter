"""
ServiceManager is responsible for orchestrating application functionality by coordinating
infrastructure services and domain entities.
"""

import logging
import platform
import sys
import threading

try:
    import resource  # Unix-only; unavailable on Windows
except ImportError:
    resource = None
from typing import Optional, Dict, Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ..domain.settings import Settings, LLMSettings
from ..infrastructure.persistence.settings_repository import SettingsRepository
from ..infrastructure.audio.recorder import AudioRecorder
from ..infrastructure.transcription.transcriber import Transcriber
from ..infrastructure.llm.processor import TextProcessor
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
    
    # Signal to report health check results from background thread
    health_check_complete = Signal(bool, bool)  # audio_healthy, transcriber_healthy

    def __init__(self):
        """Initialize the service manager and all infrastructure services."""
        super().__init__()
        logger.info("Initializing service manager")
        
        # Connect health check signal
        self.health_check_complete.connect(self._on_health_check_complete)
        
        # Core dependencies
        self._settings_repository = None
        self._settings = None
        
        # Thread safety lock for service access
        self._service_lock = threading.RLock()
        
        # Services
        self._recording_service = None
        
        # Infrastructure components
        self._audio_recorder = None
        self._transcriber = None
        self._text_processor = None
        
        # Initialize everything
        self._initialize_core_dependencies()
        self._initialize_infrastructure()
        self._initialize_services()
        
        # Setup health monitoring
        self._setup_health_monitoring()
        
        logger.info("Service manager initialization complete")
    
    def _setup_health_monitoring(self):
        """Setup periodic health checks for services."""
        logger.debug("Setting up service health monitoring")
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._check_health)
        self._health_timer.start(30000)  # Check every 30 seconds

        # Memory watchdog — logs RSS and thread/object counts every 10s so we can
        # correlate any leak with activity that was happening in the same window.
        self._memory_timer = QTimer(self)
        self._memory_timer.timeout.connect(self._log_memory_snapshot)
        self._memory_timer.start(10000)

        # Connect to recording service failure signal
        if self._recording_service:
            self._recording_service.recording_failed.connect(self._handle_recording_failure)

    def _log_memory_snapshot(self):
        """Log RSS, thread count, and Python object count for leak diagnostics."""
        if resource is None:
            return
        try:
            rusage = resource.getrusage(resource.RUSAGE_SELF)
            # macOS reports ru_maxrss in bytes; Linux reports in KB.
            if sys.platform == "darwin":
                rss_mb = rusage.ru_maxrss / (1024 * 1024)
            else:
                rss_mb = rusage.ru_maxrss / 1024

            import gc
            obj_count = len(gc.get_objects())
            thread_count = threading.active_count()

            logger.warning(
                f"[MEMWATCH] RSS={rss_mb:.1f}MB  threads={thread_count}  py_objects={obj_count}"
            )

            # If we're deep into runaway territory, dump the top object types so we
            # can see which allocator is growing before the OS kills us.
            if rss_mb > 2000:
                from collections import Counter
                type_counts = Counter(type(o).__name__ for o in gc.get_objects())
                top = type_counts.most_common(15)
                logger.warning(f"[MEMWATCH] top object types: {top}")
        except Exception as e:
            logger.debug(f"memory snapshot failed: {e}")

    def _check_health(self):
        """Check health of critical services in a background thread."""
        logger.debug("Starting periodic service health check")
        
        def check_task():
            audio_healthy = True
            transcriber_healthy = True
            
            with self._service_lock:
                # Capture references safely within lock
                audio_recorder = self._audio_recorder
                transcriber = self._transcriber
            
            # Check Audio Recorder
            if audio_recorder:
                try:
                    if not audio_recorder.is_healthy():
                        audio_healthy = False
                except Exception as e:
                    logger.error(f"Error checking audio health: {e}")
                    audio_healthy = False
            
            # Check Transcriber
            if transcriber:
                try:
                    if not transcriber.is_healthy():
                        transcriber_healthy = False
                except Exception as e:
                    logger.error(f"Error checking transcriber health: {e}")
                    transcriber_healthy = False
            
            self.health_check_complete.emit(audio_healthy, transcriber_healthy)
            
        # Run check in background thread to avoid blocking UI
        threading.Thread(target=check_task, daemon=True).start()

    @Slot(bool, bool)
    def _on_health_check_complete(self, audio_healthy, transcriber_healthy):
        """Handle health check results on the main thread."""
        if not audio_healthy:
            logger.warning("Audio recorder health check failed - attempting recovery")
            self._recover_audio_service()
            
        if not transcriber_healthy:
            logger.warning("Transcriber health check failed - attempting recovery")
            self._recover_transcription_service()
            
    def _handle_recording_failure(self, error_message):
        """Handle failure reported by recording service.

        Only rebuild services that are actually unhealthy — failures like an
        empty recording are transient and must not tear down a working recorder.
        """
        logger.warning(f"Recording service reported failure: {error_message}")

        with self._service_lock:
            recorder = self._audio_recorder
            transcriber = self._transcriber

        recovered = False
        if recorder is None or not recorder.is_healthy():
            logger.info("Audio recorder is unhealthy, recovering audio service")
            self._recover_audio_service()
            recovered = True

        if transcriber is None or not transcriber.is_healthy():
            logger.info("Transcriber is unhealthy, recovering transcription service")
            self._recover_transcription_service()
            recovered = True

        # A transcription failure with a loaded model still warrants a rebuild:
        # is_healthy() only checks the model is loaded, not that it works, and
        # transcribe() failures are exceptions rather than device problems.
        if not recovered and "transcri" in error_message.lower():
            logger.info("Transcription failed despite loaded model - rebuilding transcriber")
            self._recover_transcription_service()
            recovered = True

        if not recovered:
            logger.info("Services are healthy; treating failure as transient (no recovery needed)")

    def _recover_audio_service(self):
        """Recover the audio recording service."""
        # Never tear down the recorder while it's recording or still being
        # stopped/saved — a transient device blip is handled by the recorder's
        # own retry loop, and cleanup() here would destroy the buffered audio.
        # Recovery re-runs on the next health check.
        if self._recording_service and self._recording_service.is_busy():
            logger.info("Recorder is busy - deferring audio service recovery")
            return

        logger.info("Recovering audio service...")

        # Cleanup old recorder to prevent resource leaks
        with self._service_lock:
            old_recorder = self._audio_recorder
            
        if old_recorder:
            try:
                logger.info("Shutting down unhealthy audio recorder")
                old_recorder.cleanup()
            except Exception as e:
                logger.warning(f"Error shutting down old recorder: {e}")

        try:
            # Re-initialize audio recorder with current settings
            # If specific device failed, we might want to fall back to default,
            # but for now let's try to reload with configured settings first.
            # If that fails, AudioRecorder logic (which we improved) handles device resolution.
            
            new_recorder = AudioRecorder(
                sample_rate=self._settings.audio.sample_rate,
                channels=self._settings.audio.channels,
                device=self._settings.audio.input_device
            )
            
            if new_recorder.is_healthy():
                with self._service_lock:
                    self._audio_recorder = new_recorder
                    if self._recording_service:
                        self._recording_service.set_audio_recorder(new_recorder)
                logger.info("Audio service recovered successfully")
            else:
                logger.error("Failed to recover audio service - new recorder is unhealthy")
                
        except Exception as e:
            logger.error(f"Exception during audio service recovery: {e}")

    def _recover_transcription_service(self):
        """Recover the transcription service."""
        logger.info("Recovering transcription service...")
        try:
            new_transcriber = Transcriber(
                model_size=self._settings.transcription.model,
                device=self._settings.transcription.device,
                compute_type="int8"
            )
            
            if new_transcriber.is_healthy():
                with self._service_lock:
                    self._transcriber = new_transcriber
                    if self._recording_service:
                        self._recording_service.set_transcriber(new_transcriber)
                logger.info("Transcription service recovered successfully")
            else:
                logger.error("Failed to recover transcription service - new transcriber is unhealthy")
                
        except Exception as e:
            logger.error(f"Exception during transcription service recovery: {e}")
            
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
        
        with self._service_lock:
            # Initialize audio recorder
            try:
                self._audio_recorder = AudioRecorder(
                    sample_rate=self._settings.audio.sample_rate,
                    channels=self._settings.audio.channels,
                    device=self._settings.audio.input_device
                )
            except Exception as e:
                logger.error(f"Failed to initialize audio recorder: {e}")
                # Create a dummy or broken recorder to prevent attribute errors later
                # Ideally AudioRecorder should be robust enough to init even if broken
                self._audio_recorder = None

            # Initialize transcriber
            try:
                self._transcriber = Transcriber(
                    model_size=self._settings.transcription.model,
                    device=self._settings.transcription.device,
                    compute_type="int8"
                )
            except Exception as e:
                logger.error(f"Failed to initialize transcriber: {e}")
                self._transcriber = None
        
        # Log LLM status
        if hasattr(self._settings, 'llm') and self._settings.llm:
            logger.info(f"LLM settings: enabled={self._settings.llm.enabled}")
    
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
        # Note: update_settings() handles LLM, audio, and hotkey updates internally
        if self._recording_service:
            self._recording_service.update_settings(self._settings)
    
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

    def shutdown(self):
        """Perform clean shutdown of all services.
        
        Shutdown order is important to prevent race conditions:
        1. Disable hotkeys first to prevent new recordings from starting
        2. Stop any active recording
        3. Shutdown recording service (hotkey handler, audio recorder)
        4. Clean up other resources
        """
        logger.info("Shutting down service manager")
        
        # STEP 1: Disable hotkeys first to prevent new recordings during shutdown
        if self._recording_service and self._recording_service.hotkey_handler:
            logger.debug("Disabling hotkeys during shutdown")
            try:
                if hasattr(self._recording_service.hotkey_handler, 'set_hotkeys_enabled'):
                    self._recording_service.hotkey_handler.set_hotkeys_enabled(False)
            except Exception as e:
                logger.warning(f"Error disabling hotkeys during shutdown: {e}")
        
        # STEP 2/3: Shutdown recording service — it stops any active recording
        # synchronously (saving the audio) and shuts down the hotkey handler.
        # We deliberately don't call recording_service.stop_recording() here:
        # that would kick off a background transcription the quitting app
        # would kill mid-flight.
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
        
        # STEP 4: Clean up any resources held by processors
        self._text_processor = None
        
        # Save settings on shutdown
        try:
            self.save_settings()
        except Exception as e:
            logger.error(f"Error saving settings during shutdown: {e}")
        
        logger.info("Service manager shutdown complete") 