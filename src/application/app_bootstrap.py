"""
AppBootstrap handles application initialization and lifecycle.
"""

import logging
import sys
from pathlib import Path
import platform
import os

from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from PySide6.QtGui import QIcon

from .service_manager import ServiceManager
from ..presentation.system_tray import SystemTrayIcon
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
        self.service_manager = None
        
        # Set up Linux-specific configuration before creating QApplication
        if platform.system() == 'Linux':
            try:
                # Force use of XCB platform
                os.environ['QT_QPA_PLATFORM'] = 'xcb'
                # Disable D-Bus usage for system tray
                os.environ['QT_NO_DBUS'] = '1'
                # Set up icon theme paths
                QIcon.setThemeName('Adwaita')
                QIcon.setThemeSearchPaths([
                    '/usr/share/icons',
                    '/usr/share/icons/hicolor',
                    '/usr/share/icons/Adwaita',
                    '/usr/share/icons/gnome'
                ])
                # Set platform plugin path for Fedora
                os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = '/usr/lib64/qt5/plugins/platforms'
                logger.debug("Linux-specific configuration applied")
            except Exception as e:
                logger.warning(f"Failed to set up Linux configuration: {e}")

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
        try:
            # Try to show the tray icon
            self.tray.show()
            # Try to show notification if tray icon is visible
            self.tray.show_notification(
                "Mutter",
                "Loading...",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        except Exception as e:
            logger.warning(f"Error showing system tray icon: {e}")
            if platform.system() == 'Linux':
                # Try to reinitialize with XCB platform
                try:
                    os.environ['QT_QPA_PLATFORM'] = 'xcb'
                    self.tray = SystemTrayIcon()
                    self.tray.show()
                    logger.debug("System tray icon shown successfully with XCB platform")
                except Exception as e2:
                    logger.warning(f"Failed to show system tray icon with XCB platform: {e2}")
            logger.info("Application will continue with limited UI functionality")
            # Continue without the tray icon - hotkeys will still work
        
        
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
            try:
                self.tray.show_notification(
                    "Mutter",
                    "Ready",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
            except Exception as e:
                logger.warning(f"Error showing ready notification: {e}")
                # Continue without the notification
            
        except Exception as e:
            logger.critical(f"Failed to initialize application: {e}", exc_info=True)
            self._show_error(f"Application started with errors: {str(e)}\n\nSome features may not work. Please check logs.")
            # Do not exit, try to keep running in a degraded state
            # sys.exit(1)
    
    def _connect_signals(self):
        """Connect signals between components."""
        logger.debug("Connecting signals between components")
        
        if not self.service_manager:
            logger.error("Service manager is None, cannot connect signals")
            return
            
        recording_service = self.service_manager.recording_service
        if not recording_service:
            logger.error("Recording service is None, cannot connect signals")
            return
        
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
        
        # Clean up tray icon and its toast
        if hasattr(self, 'tray') and self.tray:
            if hasattr(self.tray, 'toast') and self.tray.toast:
                self.tray.toast.cleanup()
        
        # Shutdown service manager
        if hasattr(self, 'service_manager'):
            self.service_manager.shutdown()


def run_application():
    """Run the application."""
    # Ensure logging streams can handle arbitrary Unicode text on Windows.
    # Transcription/LLM output may include characters outside cp1252.
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                # Keep startup resilient even if a stream cannot be reconfigured.
                pass

    # Set up logging
    log_dir = Path.home() / ".voicerecorder" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "voicerecorder.log", encoding="utf-8"),
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