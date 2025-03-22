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
        self.app.setApplicationName("Voice Recorder")
        
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
        self.tray.showMessage(
            "Voice Recorder",
            "Loading...",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
        
        try:
            # Initialize application service
            logger.info("Starting application service initialization")
            self.app_service = ApplicationService()
            logger.info("Application service initialized successfully")
            
            # Initialize the rest of the UI
            self.settings_dialog = None  # Create on demand
            
            # Connect signals
            self.app_service.recording_service.recording_started.connect(self.tray.on_recording_started)
            self.app_service.recording_service.recording_stopped.connect(self.tray.on_recording_stopped)
            self.app_service.recording_service.recording_failed.connect(self.tray.on_recording_failed)
            self.app_service.recording_service.transcription_complete.connect(self.tray.on_transcription_complete)
            
            # Connect settings
            self.tray.settings_action.triggered.connect(self.show_settings)
            
            # Register initial hotkey
            if not self.app_service.settings.hotkeys.record_key.isEmpty():
                self.app_service.recording_service.set_hotkey(self.app_service.settings.hotkeys.record_key)
                self.tray.showMessage(
                    "Ready",
                    f"Hotkey: {self.app_service.settings.hotkeys.record_key.toString()}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
            else:
                # Set default hotkey if none is configured
                default_hotkey = QKeySequence("Ctrl+Shift+R")
                self.app_service.recording_service.set_hotkey(default_hotkey)
                logger.info(f"Using default hotkey: {default_hotkey.toString()}")
                self.tray.showMessage(
                    "Ready",
                    f"Hotkey: {default_hotkey.toString()}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
            
            # Register a hotkey for exiting the application
            exit_hotkey = QKeySequence("Ctrl+Shift+Q")
            self._register_exit_hotkey(exit_hotkey)
            logger.info(f"Registered exit hotkey: {exit_hotkey.toString()}")
            
            # Don't show a message about exit hotkey, it's annoying
                
        except Exception as e:
            logger.critical(f"Failed to initialize application: {e}", exc_info=True)
            self._show_error(f"Failed to initialize application: {str(e)}\n\nPlease check your internet connection and try again.")
            sys.exit(1)
    
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
        
        # Set current hotkey if available
        if self.app_service.recording_service.hotkey_handler.registered_hotkeys:
            current_hotkey = list(self.app_service.recording_service.hotkey_handler.registered_hotkeys.keys())[0]
            self.settings_dialog.set_current_hotkey(current_hotkey)
        
        self.settings_dialog.show()
    
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