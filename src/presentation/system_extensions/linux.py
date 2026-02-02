import subprocess
import time
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QClipboard
import logging

logger = logging.getLogger(__name__)

class LinuxSystemExtension:
    @staticmethod
    def paste_text(text_to_paste: str = None):
        """Paste text into the active window.

        Args:
            text_to_paste: Optional text to copy to clipboard before pasting.
                          If None, just simulates Ctrl+V with current clipboard content.
        """
        # Use xdotool to simulate Ctrl+V keystroke
        # Ensure clipboard content is updated
        # We'll force a synchronization by using xsel
        try:
            # If text is provided, copy it to clipboard first
            if text_to_paste is not None:
                # Re-copy to clipboard to ensure it's fresh
                clipboard = QApplication.clipboard()
                clipboard.setText(text_to_paste)
                # Also set the X11 primary selection
                clipboard.setText(text_to_paste, QClipboard.Selection)
                logger.debug(f"Copied text to clipboard before paste: {text_to_paste[:100]}...")

                # Use xsel to ensure the clipboard content is synchronized
                try:
                    # Copy our content to X clipboard using xsel
                    process = subprocess.Popen(['xsel', '-b', '-i'], stdin=subprocess.PIPE)
                    process.communicate(input=text_to_paste.encode())
                    logger.debug("Synchronized clipboard content with xsel")
                except (subprocess.SubprocessError, FileNotFoundError):
                    logger.warning("xsel not found, using Qt clipboard only")

            # Give a larger delay for UI and clipboard to stabilize
            time.sleep(1.0)

            # Simulate Ctrl+V using xdotool
            subprocess.run(['xdotool', 'key', 'ctrl+v'], check=True)
            logger.debug("Auto-paste keystrokes sent via xdotool")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to send keystrokes via xdotool: {e}")
        except FileNotFoundError:
            logger.error("xdotool not found. Please install it to enable auto-paste functionality.")