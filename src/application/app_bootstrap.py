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
from ..presentation.windows.download_manager import DownloadManagerWindow
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
        self.app.setApplicationName("Mutter")
        
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
            "Mutter",
            "Loading...",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
        
        # Initialize settings window container
        self.settings_window = None
        self.download_manager_window = None
        
        try:
            # Initialize service manager
            logger.info("Initializing service manager")
            self.service_manager = ServiceManager()
            logger.info("Service manager initialized successfully")
            
            # Store service manager reference in QApplication for global access
            self.app.service_manager = self.service_manager
            
            # Connect signals between components
            self._connect_signals()
            
            # Initialize hotkeys
            self._setup_hotkeys()
            
            # Connect system tray to service manager
            self.tray.set_service_manager(self.service_manager)
            
            # Show ready notification
            self.tray.show_notification(
                "Mutter",
                "Ready",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
            
        except Exception as e:
            logger.critical(f"Failed to initialize application: {e}", exc_info=True)
            self._show_error(f"Failed to initialize application: {str(e)}\n\nPlease check your internet connection and try again.")
            sys.exit(1)
    
    def _connect_signals(self):
        """Connect signals between components."""
        logger.debug("Connecting signals between components")
        
        recording_service = self.service_manager.recording_service
        
        # Recording state signals
        recording_service.recording_started.connect(self.tray.on_recording_started)
        recording_service.recording_stopped.connect(self.tray.on_recording_stopped)
        recording_service.recording_failed.connect(self.tray.on_recording_failed)
        recording_service.transcription_complete.connect(self.tray.on_transcription_complete)
        recording_service.llm_processing_complete.connect(self.tray.on_llm_processing_complete)
        
        # Exit hotkey signal if available
        if hasattr(recording_service.hotkey_handler, 'exit_hotkey_pressed'):
            recording_service.hotkey_handler.exit_hotkey_pressed.connect(self._on_exit_hotkey)
        
        # Connect stop hotkey if available
        if hasattr(recording_service.hotkey_handler, 'stop_hotkey_pressed'):
            recording_service.hotkey_handler.stop_hotkey_pressed.connect(self.tray.on_stop_hotkey_pressed)
    
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
    
    def show_downloads(self):
        """Show the downloads window."""
        logger.debug("Downloads functionality is disabled")
        
        # Show a notification that downloads are disabled
        self.tray.show_notification(
            "Downloads Disabled",
            "LLM features have been disabled in this version.",
            QSystemTrayIcon.MessageIcon.Information,
            3000
        )
        
        # Uncomment the following code block to enable download manager when needed
        '''
        # Create a new window if it doesn't exist or was closed
        if self.download_manager_window is None or not self.download_manager_window.isVisible():
            self.download_manager_window = DownloadManagerWindow()
            
            # Connect to the download manager
            if self.service_manager and self.service_manager.download_manager:
                logger.info("Connecting download manager window to download manager")
                self.service_manager.download_manager.register_progress_callback(self.download_manager_window)
                
                # Populate with any existing downloads
                downloads = self.service_manager.download_manager.get_downloads()
                if downloads:
                    logger.info(f"Found {len(downloads)} existing downloads to display")
                    for model_name, download_info in downloads.items():
                        self.download_manager_window.update_download_progress(
                            model_name,
                            download_info.get("message", "Download in progress"),
                            download_info.get("progress", 0.0)
                        )
        
        # Show and activate the window
        self.download_manager_window.show()
        self.download_manager_window.raise_()
        self.download_manager_window.activateWindow()
        '''
    
    def _on_settings_saved(self):
        """Handle settings saved event."""
        logger.info("Settings saved, reloading")
        
        # Reload settings in service manager
        self.service_manager.reload_settings()
        
        # Update tray with new settings
        self.tray.update_settings(self.service_manager.settings)
    
    def _on_exit_hotkey(self):
        """Handle exit hotkey press event."""
        logger.info("Exit hotkey pressed, shutting down application")
        
        # Log current state of hotkeys for debugging
        if hasattr(self.service_manager.recording_service, 'hotkey_handler'):
            handler = self.service_manager.recording_service.hotkey_handler
            if hasattr(handler, 'exit_hotkey') and handler.exit_hotkey:
                logger.info(f"Current exit_hotkey in handler: {handler.exit_hotkey.toString()}")
            else:
                logger.warning("No exit_hotkey set in handler")
            
            # Log all registered hotkeys
            if hasattr(handler, 'registered_hotkeys'):
                hotkeys = handler.registered_hotkeys
                logger.info(f"Registered hotkeys: {', '.join([k.toString() for k in hotkeys.keys()])}")
            
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