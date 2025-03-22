"""
Simple script to test system tray notifications without loading the Whisper model.
"""

import sys
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QKeySequence
import logging

from src.presentation.system_tray import SystemTrayIcon

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotificationTester:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.tray = SystemTrayIcon()
        self.tray.show()
        
    def run_test(self):
        """Run a series of notification tests"""
        # Initial notification
        self.tray.showMessage(
            "Test Started",
            "Testing notifications...",
            SystemTrayIcon.MessageIcon.Information,
            1000
        )
        time.sleep(1.5)
        
        # Test recording started
        self.tray.on_recording_started()
        logger.info("Tested recording started notification")
        time.sleep(1.5)
        
        # Test recording stopped
        dummy_path = Path("test_recording.wav")
        self.tray.on_recording_stopped(dummy_path)
        logger.info("Tested recording stopped (should not show notification)")
        time.sleep(1.5)
        
        # Test transcription complete
        test_text = "This is a test transcription that should be automatically copied to your clipboard."
        self.tray.on_transcription_complete(test_text)
        logger.info("Tested transcription complete with clipboard copy")
        time.sleep(3)
        
        # Final notification
        self.tray.showMessage(
            "Test Complete",
            "All tests completed successfully.\nCheck your clipboard for the transcription.",
            SystemTrayIcon.MessageIcon.Information,
            2000
        )
        
        # Give time for the last notification to be shown
        time.sleep(3)
        return 0
        
    def run(self):
        """Run the notification test app"""
        # Run tests on a timer to avoid blocking the event loop
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, self.run_test)
        # Run the app for a few seconds, then quit
        QTimer.singleShot(10000, self.app.quit)
        return self.app.exec()

def main():
    tester = NotificationTester()
    return tester.run()

if __name__ == "__main__":
    sys.exit(main()) 