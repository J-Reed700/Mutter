import sys
import platform
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
import logging
from PySide6.QtGui import QKeySequence, QIcon
import traceback

# Import from application layer only
from src.presentation.system_tray import SystemTrayIcon
from src.application.app_service import ApplicationService
from src.presentation.windows.settings import SettingsDialog
from src.presentation.theme import AppTheme

# Set up logging
log_dir = Path.home() / ".voicerecorder" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "voicerecorder.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Custom exception hook to log unhandled exceptions
def exception_hook(exc_type, exc_value, exc_traceback):
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

# Install the exception hook
sys.excepthook = exception_hook

class Application:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("Memo")
        
        # Apply the modern theme
        AppTheme.apply(self.app)
        
        # Connect the aboutToQuit signal to our shutdown method
        self.app.aboutToQuit.connect(self.shutdown)
        
        # Set application icon if available
        icon_path = Path(__file__).parent.parent / "resources" / "images" / "microphone.png"
        if icon_path.exists():
            self.app.setWindowIcon(QIcon(str(icon_path)))
        
        # Initialize UI first so we can show loading message
        self.tray = SystemTrayIcon()
        self.tray.show()
        self.tray.show_notification(
            "Memo",
            "Loading...",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
        
        try:
            # Initialize application service
            logger.info("Starting application service initialization")
            self.app_service = ApplicationService()
            logger.info("Application service initialized successfully")
            
            # Apply settings to the UI
            self._apply_settings_to_ui()
            
            # Initialize the rest of the UI
            self.settings_dialog = None  # Create on demand
            self.settings_window = None  # Create settings window on demand
            
            # Connect signals
            self.app_service.recording_service.recording_started.connect(self.tray.on_recording_started)
            self.app_service.recording_service.recording_stopped.connect(self.tray.on_recording_stopped)
            self.app_service.recording_service.recording_failed.connect(self.tray.on_recording_failed)
            self.app_service.recording_service.transcription_complete.connect(self.tray.on_transcription_complete)
            
            # Connect the stop_requested signal to show toast before processing starts
            self.app_service.recording_service.stop_requested.connect(self.tray.on_stop_hotkey_pressed)
            
            # Connect hotkey signals - but not redundantly to on_stop_hotkey_pressed
            logger.debug("Connecting hotkey signals")
            # Don't connect hotkey_released to on_stop_hotkey_pressed anymore, we use stop_requested instead
            # self.app_service.recording_service.hotkey_handler.hotkey_released.connect(self.tray.on_stop_hotkey_pressed)
            logger.debug("Connection established for hotkey signals")
            
            # Connect LLM processing signal
            self.app_service.recording_service.llm_processing_complete.connect(self.tray.on_llm_processing_complete)
            
            # Connect settings
            self.tray.settings_action.triggered.connect(self.show_full_settings)
            
            # Register initial hotkey
            self._setup_hotkeys()
            
        except Exception as e:
            logger.critical(f"Failed to initialize application: {e}", exc_info=True)
            self._show_error(f"Failed to initialize application: {str(e)}\n\nPlease check your internet connection and try again.")
            sys.exit(1)
    
    def _apply_settings_to_ui(self):
        """Apply the current settings to the UI components"""
        if hasattr(self.app_service.settings, 'appearance'):
            # Update system tray notification settings
            self.tray.update_settings(self.app_service.settings)
            logger.debug("Applied appearance settings to UI components")
    
    def _setup_hotkeys(self):
        """Set up all application hotkeys with enhanced error handling"""
        logger.info("Setting up application hotkeys")
        
        # 1. Set up record hotkey
        record_success = False
        
        # Changed order - try Ctrl+Shift+R first, then fall back to other options
        alternative_hotkeys = [
            QKeySequence("Ctrl+Shift+R"),  # Try this first (our preferred hotkey)
            QKeySequence("F9"),
            QKeySequence("Ctrl+Alt+R"),
            QKeySequence("Alt+R"),
            QKeySequence("Ctrl+Alt+S")
        ]
        
        # First check if we have a configured hotkey
        record_hotkey = self.app_service.settings.hotkeys.record_key
        if record_hotkey and not record_hotkey.isEmpty():
            # If the configured hotkey isn't Ctrl+Shift+R, add it to the start of alternatives
            if record_hotkey.toString() != "Ctrl+Shift+R":
                logger.info(f"Attempting to register configured record hotkey: {record_hotkey.toString()}")
                record_success = self.app_service.recording_service.set_hotkey(record_hotkey)
                if record_success:
                    logger.info(f"Successfully registered configured record hotkey: {record_hotkey.toString()}")
                    self.tray.show_notification(
                        "Ready",
                        f"Record hotkey: {record_hotkey.toString()}",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000
                    )
        
        # If configured hotkey failed or doesn't exist, try alternatives
        if not record_success:
            for alt_hotkey in alternative_hotkeys:
                logger.info(f"Trying alternative record hotkey: {alt_hotkey.toString()}")
                
                # Call the set_hotkey method
                try:
                    # Try to register the hotkey
                    # The actual Windows registration might succeed but saving to settings might fail
                    registration_result = self.app_service.recording_service.hotkey_handler.register_hotkey(alt_hotkey)
                    
                    if registration_result:
                        # Update our internal state even if saving fails
                        self.app_service.settings.hotkeys.record_key = alt_hotkey
                        
                        # Update the recording service's settings
                        self.app_service.recording_service.settings.hotkeys.record_key = alt_hotkey
                        
                        # Try to save settings but don't fail if it doesn't work
                        try:
                            self.app_service.settings_repository.save(self.app_service.settings)
                        except Exception as e:
                            logger.error(f"Error saving settings after hotkey registration: {e}")
                        
                        self.tray.show_notification(
                            "Ready",
                            f"Using hotkey: {alt_hotkey.toString()}",
                            QSystemTrayIcon.MessageIcon.Information,
                            3000
                        )
                        record_success = True
                        break
                except Exception as e:
                    logger.error(f"Error registering hotkey {alt_hotkey.toString()}: {e}")
                    continue
            
            if not record_success:
                logger.error("Failed to register any record hotkey")
                self.tray.show_notification(
                    "Warning",
                    "Failed to register record hotkey. Please configure a different hotkey in settings.",
                    QSystemTrayIcon.MessageIcon.Warning,
                    5000
                )
        
        # 2. Set up process text hotkey in the same way, prioritizing Ctrl+Shift+P
        process_success = False
        process_hotkeys = [
            QKeySequence("Ctrl+Shift+P"),  # Try this first
            QKeySequence("F10"),
            QKeySequence("Ctrl+Alt+P"),
            QKeySequence("Alt+P")
        ]
        
        for process_hotkey in process_hotkeys:
            logger.info(f"Trying process text hotkey: {process_hotkey.toString()}")
            try:
                registration_result = self.app_service.recording_service.hotkey_handler.register_process_text_hotkey(process_hotkey)
                
                if registration_result:
                    # Update our settings
                    self.app_service.settings.hotkeys.process_text_key = process_hotkey
                    self.app_service.recording_service.settings.hotkeys.process_text_key = process_hotkey
                    
                    # Try to save settings but don't fail if it doesn't work
                    try:
                        self.app_service.settings_repository.save(self.app_service.settings)
                    except Exception as e:
                        logger.error(f"Error saving settings after process hotkey registration: {e}")
                    
                    logger.info(f"Successfully registered process text hotkey: {process_hotkey.toString()}")
                    self.tray.show_notification(
                        "LLM Processing",
                        f"Hotkey: {process_hotkey.toString()}",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000
                    )
                    process_success = True
                    break
            except Exception as e:
                logger.error(f"Error registering process text hotkey {process_hotkey.toString()}: {e}")
                continue
        
        # 3. Set up exit hotkey
        exit_success = False
        exit_hotkeys = [
            QKeySequence("Ctrl+Shift+Q"),
            QKeySequence("F12"),
            QKeySequence("Ctrl+Alt+Q"),
            QKeySequence("Ctrl+Alt+X")
        ]
        
        for exit_hotkey in exit_hotkeys:
            logger.info(f"Attempting to register exit hotkey: {exit_hotkey.toString()}")
            if self._register_exit_hotkey(exit_hotkey):
                logger.info(f"Successfully registered exit hotkey: {exit_hotkey.toString()}")
                exit_success = True
                break
        
        if not exit_success:
            logger.error("Failed to register any exit hotkey")
    
    def _register_exit_hotkey(self, key_sequence):
        """Register a hotkey to exit the application"""
        if self.app_service.recording_service.hotkey_handler.register_hotkey(key_sequence):
            # Connect signal manually to quit function
            def on_exit_hotkey():
                logger.info("Exit hotkey pressed, shutting down application")
                self.app.quit()
            
            # Get the instance of the hotkey handler
            hotkey_handler = self.app_service.recording_service.hotkey_handler
            
            # Connect our exit handler to the exit_hotkey_pressed signal
            hotkey_handler.exit_hotkey_pressed.connect(on_exit_hotkey)
            
            return True
        return False
    
    def run(self):
        """Run the application main loop"""
        return self.app.exec()

    def show_settings(self):
        """Show the settings dialog"""
        if not self.settings_dialog:
            self.settings_dialog = SettingsDialog(settings=self.app_service.settings, 
                                                  settings_repository=self.app_service.settings_repository)
            self.settings_dialog.hotkey_changed.connect(self.app_service.recording_service.set_hotkey)
            self.settings_dialog.accepted.connect(self._on_settings_accepted)
        
        # Set current hotkey if available
        if self.app_service.recording_service.hotkey_handler.registered_hotkeys:
            current_hotkey = list(self.app_service.recording_service.hotkey_handler.registered_hotkeys.keys())[0]
            self.settings_dialog.set_current_hotkey(current_hotkey)
        
        self.settings_dialog.show()
    
    def show_full_settings(self):
        """Show the full settings window"""
        from src.presentation.windows.settings import SettingsWindow
        
        # Create a new window only if it doesn't exist or was closed
        if self.settings_window is None or not self.settings_window.isVisible():
            self.settings_window = SettingsWindow(
                settings=self.app_service.settings,
                settings_repository=self.app_service.settings_repository
            )
            
            # Connect to settings_saved signal
            self.settings_window.settings_saved.connect(self._on_settings_saved)
        
        # Show and activate the window
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
    
    def _on_settings_accepted(self):
        """Handle when settings dialog is accepted"""
        # Reload settings to apply any changes
        self.app_service.reload_settings()
        
        # Show notification about hotkeys
        self.tray.show_notification(
            "Settings Updated",
            f"Recording hotkey: {self.app_service.settings.hotkeys.record_key.toString()}",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
    
    def _on_settings_saved(self):
        """Handle when full settings window is saved"""
        logger.info("Settings saved, applying changes to running services")
        
        # Store current settings for comparison
        old_settings = self.app_service.settings
        
        # Get the new hotkeys before reloading settings
        record_hotkey = self.app_service.settings.hotkeys.record_key
        process_text_hotkey = self.app_service.settings.hotkeys.process_text_key
        
        # Reload settings to apply any changes
        self.app_service.reload_settings()
        
        # Explicitly register hotkeys - this is critical to make the changes work
        if record_hotkey:
            logger.info(f"Applying new record hotkey from settings: {record_hotkey.toString()}")
            self.app_service.recording_service.set_hotkey(record_hotkey)
        
        # Also apply process text hotkey if set
        if process_text_hotkey:
            logger.info(f"Applying new process text hotkey from settings: {process_text_hotkey.toString()}")
            self.app_service.recording_service.set_process_text_hotkey(process_text_hotkey)
        
        # Apply appearance settings to the UI components
        self._apply_settings_to_ui()
        
        # Show notifications about the changes
        
        # Transcription changes
        if (old_settings.transcription.model != self.app_service.settings.transcription.model or
            old_settings.transcription.device != self.app_service.settings.transcription.device):
            self.tray.show_notification(
                "Transcription Settings Updated",
                f"Model: {self.app_service.settings.transcription.model}\nDevice: {self.app_service.settings.transcription.device}",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
        
        # LLM changes
        if self.app_service.settings.llm.enabled:
            # LLM settings enabled or changed
            if self.app_service.settings.llm.use_embedded_model:
                self.tray.show_notification(
                    "LLM Processing Enabled",
                    f"Using embedded model: {self.app_service.settings.llm.embedded_model_name}\nProcessing type: {self.app_service.settings.llm.default_processing_type}",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
            else:
                self.tray.show_notification(
                    "LLM Processing Enabled",
                    f"Using external model: {self.app_service.settings.llm.model}\nProcessing type: {self.app_service.settings.llm.default_processing_type}",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
        elif old_settings.llm.enabled and not self.app_service.settings.llm.enabled:
            # LLM settings were disabled
            self.tray.show_notification(
                "LLM Processing Disabled",
                "LLM processing has been disabled",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
    
    def _show_error(self, message):
        """Show an error message box"""
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Critical)
        error_box.setWindowTitle("Error")
        error_box.setText(message)
        error_box.exec()
    
    def shutdown(self):
        """Clean up resources before shutdown"""
        logger.info("Shutting down application")
        if hasattr(self, 'app_service'):
            self.app_service.shutdown()

def main():
    # Create and run the application
    app = Application()
    
    try:
        # Connect to global exception handling for debug info
        app.app_service.recording_service.recording_started.connect(
            lambda: logger.info("Recording started")
        )
        app.app_service.recording_service.recording_stopped.connect(
            lambda path: logger.info(f"Recording saved to: {path}")
        )
        app.app_service.recording_service.recording_failed.connect(
            lambda error: logger.error(f"Recording failed: {error}")
        )
        app.app_service.recording_service.llm_processing_complete.connect(
            lambda result: logger.info(f"LLM processing complete: {result.processing_type}")
        )
        
        # Run the application
        exit_code = app.run()
        
        # Clean up
        app.shutdown()
        
        sys.exit(exit_code)
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main() 