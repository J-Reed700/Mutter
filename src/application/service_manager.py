"""
ServiceManager is responsible for orchestrating application functionality by coordinating
infrastructure services and domain entities.
"""

import logging
import platform
import threading
from typing import Optional, Dict, Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ..domain.settings import Settings, LLMSettings
from ..infrastructure.persistence.settings_repository import SettingsRepository
from ..infrastructure.audio.recorder import AudioRecorder
from ..infrastructure.transcription.transcriber import Transcriber
from ..infrastructure.llm.processor import TextProcessor
from ..infrastructure.recording.recording_service import RecordingService
from ..infrastructure.diagnostics import process_memory


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

    # Memory watchdog dumps Python object-type counts each time RSS has grown
    # by this much since the previous dump.
    MEMWATCH_DUMP_STEP_MB = 512

    def __init__(self):
        """Initialize the service manager and all infrastructure services."""
        super().__init__()
        logger.info("Initializing service manager")

        # Connect health check signal
        self.health_check_complete.connect(self._on_health_check_complete)

        # Memory at the last object-type dump (None until the first snapshot)
        self._memwatch_last_dump_mb = None
        self._memwatch_tick = 0
        self._memwatch_obj_count = 0
        
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
        """Log process memory, thread count, and Python object count for leak diagnostics.

        Works on Windows, macOS and Linux (see process_memory). Also records what
        the recorder was doing so a growth step can be tied to an activity.
        """
        try:
            mem = process_memory.sample()
            if mem is None:
                return

            thread_count = threading.active_count()
            recording = bool(self._recording_service and self._recording_service.is_recording)
            finalizing = bool(self._recording_service and self._recording_service.is_busy() and not recording)
            recorder = self._audio_recorder
            buffered_mb = (recorder._audio_data_size / (1024 * 1024)) if recorder else 0.0

            # Walking every Python object touches the whole heap, which under
            # memory pressure forces it all to be decompressed; do it once a
            # minute rather than every snapshot.
            self._memwatch_tick += 1
            import gc
            if self._memwatch_tick % 6 == 1:
                self._memwatch_obj_count = len(gc.get_objects())

            logger.warning(
                f"[MEMWATCH] {mem.describe()}  threads={thread_count}  py_objects={self._memwatch_obj_count}  "
                f"recording={recording}  finalizing={finalizing}  audio_buffer={buffered_mb:.1f}MB"
            )

            # Whenever memory has stepped up noticeably since the last dump,
            # record *where* it went: the top Python object types (a leak of
            # ordinary objects) and, on macOS, the kernel's per-region
            # breakdown (malloc vs. IOKit/CoreAudio/GPU/stacks), so the log
            # names the allocator before the OS runs out of memory. Uses the
            # task-manager figure (footprint on macOS), not RSS: pages the
            # compressor has swallowed leave RSS but still count against us.
            if self._memwatch_last_dump_mb is None:
                self._memwatch_last_dump_mb = mem.headline_mb
            elif mem.headline_mb - self._memwatch_last_dump_mb >= self.MEMWATCH_DUMP_STEP_MB:
                self._memwatch_last_dump_mb = mem.headline_mb
                from collections import Counter
                type_counts = Counter(type(o).__name__ for o in gc.get_objects())
                top = type_counts.most_common(15)
                logger.warning(f"[MEMWATCH] memory grew to {mem.headline_mb:.0f}MB; top object types: {top}")
                threading.Thread(target=self._log_memory_regions, daemon=True, name="MemRegionDump").start()
        except Exception as e:
            logger.debug(f"memory snapshot failed: {e}")

    @staticmethod
    def _log_memory_regions():
        """Log the OS's per-region memory breakdown for this process (macOS only)."""
        try:
            summary = process_memory.region_summary()
            if summary:
                logger.warning(f"[MEMWATCH] memory regions: {summary}")
        except Exception as e:
            logger.debug(f"memory region dump failed: {e}")

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

        old_settings = self._settings

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

        # The transcriber bakes in model size and device at construction time,
        # so a change requires a rebuild. Done in the background — loading a
        # Whisper model can take several seconds and must not block the UI.
        if old_settings and (
            old_settings.transcription.model != self._settings.transcription.model or
            old_settings.transcription.device != self._settings.transcription.device
        ):
            logger.info(
                f"Transcription settings changed "
                f"(model: {old_settings.transcription.model} -> {self._settings.transcription.model}, "
                f"device: {old_settings.transcription.device} -> {self._settings.transcription.device}); "
                f"rebuilding transcriber in background"
            )
            threading.Thread(
                target=self._recover_transcription_service,
                daemon=True,
                name="TranscriberRebuild"
            ).start()
    
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