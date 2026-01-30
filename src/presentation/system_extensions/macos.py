import subprocess
import time
from PySide6.QtGui import QKeySequence
import logging

logger = logging.getLogger(__name__)


class MacOSSystemExtension:
    @staticmethod
    def paste_text(text_to_paste: str = None):
        """Paste text into the active window.

        Args:
            text_to_paste: Optional text to copy to clipboard before pasting.
                          If None, just simulates Cmd+V with current clipboard content.
        """
        def check_accessibility_permissions():
            """Check if the app has accessibility permissions"""
            check_script = '''
                tell application "System Events"
                    try
                        # Attempt to get name of first process (harmless operation)
                        name of first process
                        return true
                    on error
                        return false
                    end try
                end tell
            '''
            try:
                result = subprocess.run(['osascript', '-e', check_script],
                                     capture_output=True,
                                     text=True)
                return "true" in result.stdout.lower()
            except subprocess.CalledProcessError:
                return False

        def request_accessibility_permissions():
            """Show dialog to request accessibility permissions"""
            # First, try to open System Settings directly to Accessibility
            settings_script = '''
                tell application "System Settings"
                    activate
                    delay 0.5
                    set current pane to pane id "com.apple.preference.security"
                    delay 0.5
                    reveal anchor "Privacy_Accessibility"
                end tell
            '''
            
            # Then show a more detailed dialog
            dialog_script = '''
                display dialog "Mutter needs Accessibility permission to auto-paste text." & return & return & ¬
                    "To enable:" & return & ¬
                    "1. Click the lock icon 🔒 in System Settings" & return & ¬
                    "2. Find and enable Mutter in the list" & return & ¬
                    "3. Try auto-paste again" ¬
                    with title "Enable Auto-Paste" ¬
                    with icon caution ¬
                    buttons {"Open Settings", "Cancel"} ¬
                    default button "Open Settings"
            '''
            
            try:
                # First open System Settings
                subprocess.run(['osascript', '-e', settings_script], check=True)
                # Then show the dialog
                subprocess.run(['osascript', '-e', dialog_script], check=True)
                logger.info("Showed accessibility permission request dialog")
                return True
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to show accessibility permission dialog: {e}")
                return False

        # First check if we have accessibility permissions
        if not check_accessibility_permissions():
            logger.warning("No accessibility permissions, requesting from user")
            if request_accessibility_permissions():
                # Return early since user needs to grant permissions first
                return
            else:
                logger.error("Failed to request accessibility permissions")
                return

        # If text is provided, copy it to clipboard first
        if text_to_paste is not None:
            try:
                from PySide6.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(text_to_paste)
                logger.debug(f"Copied text to clipboard before paste: {text_to_paste[:100]}...")
            except Exception as e:
                logger.error(f"Failed to copy text to clipboard: {e}")
                return

        # Give a small delay for UI to stabilize
        time.sleep(0.5)

        # Use AppleScript to simulate Command+V keystroke
        paste_script = '''
            tell application "System Events"
                keystroke "v" using command down
            end tell
        '''

        try:
            # Execute the AppleScript
            subprocess.run(['osascript', '-e', paste_script], check=True)
            logger.debug("Auto-paste keystrokes sent via AppleScript")
        except subprocess.CalledProcessError as e:
            error_msg = str(e).lower()
            logger.error(f"Failed to send keystrokes via AppleScript: {e}")
            # If we get a permission error, request permissions
            if "not allowed assistive access" in error_msg or "not allowed to send keystrokes" in error_msg:
                request_accessibility_permissions()
        except Exception as e:
            logger.error(f"Error executing AppleScript: {e}")
                
