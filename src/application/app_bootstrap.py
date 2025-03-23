"""
AppBootstrap handles application initialization and lifecycle.
"""

import logging
import sys
from pathlib import Path
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from PySide6.QtGui import QIcon

from .service_manager import ServiceManager
from ..presentation.system_tray import SystemTrayIcon
from ..presentation.windows.settings import SettingsDialog, SettingsWindow
from ..presentation.theme import AppTheme


logger = logging.getLogger(__name__)


class AppBootstrap:
    """
    Bootstraps the application by initializing all major components and handling lifecycle.
    
    Responsibilities:
    1. Initialize Qt application
    2. Set up error handling and logging
    3. Initialize service manager
    4. Initialize UI components
    5. Connect signals between services and UI
    6. Handle application lifecycle (startup, shutdown)
    """
    
    def __init__(self):
        """Initialize the application bootstrap."""
        # Create Qt application
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("Memo")
        
        # Apply theme
        AppTheme.apply(self.app)
        
        # Connect quit signal
        self.app.aboutToQuit.connect(self.shutdown)
        
        # Set application icon if available
        icon_path = Path(__file__).parent.parent.parent / "resources" / "images" / "microphone.png"
        if icon_path.exists():
            self.app.setWindowIcon(QIcon(str(icon_path)))
        
        # Initialize UI first to show loading message
        self.tray = SystemTrayIcon()
        self.tray.show()
        self.tray.show_notification(
            "Memo",
            "Loading...",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
        
        # Initialize settings window container
        self.settings_window = None
        
        try:
            # Initialize service manager
            logger.info("Initializing service manager")
            self.service_manager = ServiceManager()
            logger.info("Service manager initialized successfully")
            
            # Connect signals between components
            self._connect_signals()
            
            # Initialize hotkeys
            self._setup_hotkeys()
            
            # Show ready notification
            self.tray.show_notification(
                "Memo",
                "Ready",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
            
        except Exception as e:
            logger.critical(f"Failed to initialize application: {e}", exc_info=True)
            self._show_error(f"Failed to initialize application: {str(e)}\n\nPlease check your internet connection and try again.")
            sys.exit(1)
    
    def _connect_signals(self):
        """Connect signals between services and UI components."""
        logger.debug("Connecting signals between components")
        
        # Get the recording service
        recording_service = self.service_manager.recording_service
        
        # Connect recording service signals to UI
        recording_service.recording_started.connect(self.tray.on_recording_started)
        recording_service.recording_stopped.connect(self.tray.on_recording_stopped)
        recording_service.recording_failed.connect(self.tray.on_recording_failed)
        recording_service.transcription_complete.connect(self.tray.on_transcription_complete)
        recording_service.stop_requested.connect(self.tray.on_stop_hotkey_pressed)
        recording_service.llm_processing_complete.connect(self.tray.on_llm_processing_complete)
        
        # Connect exit hotkey if available
        if recording_service.hotkey_handler and hasattr(recording_service.hotkey_handler, 'exit_hotkey_pressed'):
            logger.debug("Connecting exit hotkey signal")
            recording_service.hotkey_handler.exit_hotkey_pressed.connect(self._on_exit_hotkey)
        
        # Connect UI signals to services
        self.tray.settings_action.triggered.connect(self.show_settings)
    
    def _setup_hotkeys(self):
        """Set up application hotkeys."""
        logger.debug("Setting up application hotkeys")
        
        # Get the recording service
        recording_service = self.service_manager.recording_service
        
        # Register record hotkey (this is handled by the recording service)
        if recording_service.hotkey_handler:
            # Explicitly call the registration method
            if hasattr(recording_service, '_register_hotkeys'):
                logger.debug("Registering hotkeys via recording service")
                recording_service._register_hotkeys()
            else:
                logger.warning("Recording service has a hotkey_handler but no _register_hotkeys method")
        else:
            logger.warning("No hotkey handler available in recording service")
    
    def show_settings(self):
        """Show the settings window."""
        logger.debug("Showing settings window")
        
        # Create a new window if it doesn't exist or was closed
        if self.settings_window is None or not self.settings_window.isVisible():
            self.settings_window = SettingsWindow(
                settings=self.service_manager.settings,
                settings_repository=self.service_manager.recording_service.settings_repository
            )
            
            # Connect settings saved signal
            self.settings_window.settings_saved.connect(self._on_settings_saved)
        
        # Show and activate the window
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
    
    def _on_settings_saved(self):
        """Handle settings saved event."""
        logger.info("Settings saved, reloading")
        
        # Reload settings in service manager
        self.service_manager.reload_settings()
    
    def _on_exit_hotkey(self):
        """Handle exit hotkey press event."""
        logger.info("Exit hotkey pressed, shutting down application")
        self.app.quit()
    
    def _show_error(self, message):
        """Show an error message box."""
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Critical)
        error_box.setWindowTitle("Error")
        error_box.setText(message)
        error_box.exec()
    
    def run(self):
        """Run the application main loop."""
        return self.app.exec()
    
    def shutdown(self):
        """Clean up resources before shutdown."""
        logger.info("Shutting down application")
        
        # Shutdown service manager
        if hasattr(self, 'service_manager'):
            self.service_manager.shutdown()


def run_application():
    """Run the application."""
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
    
    # Set up exception hook
    def exception_hook(exc_type, exc_value, exc_traceback):
        logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    
    # Install exception hook
    sys.excepthook = exception_hook
    
    try:
        # Create and run application
        app_bootstrap = AppBootstrap()
        exit_code = app_bootstrap.run()
        sys.exit(exit_code)
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        sys.exit(1) 