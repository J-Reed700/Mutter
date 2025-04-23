import subprocess
import time
from PySide6.QtGui import QKeySequence
import logging

logger = logging.getLogger(__name__)


class MacOSSystemExtension:
    @staticmethod
    def paste_text(last_transcription: str):
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
                                     text=True, 
                                     check=True)
                return "true" in result.stdout.lower()
            except:
                return Fals
        def request_accessibility_permissions():
            """Show dialog to request accessibility permissions"""
            dialog_script = '''
                tell application "System Preferences"
                    activate
                    set current pane to pane "com.apple.preference.security"
                    reveal anchor "Privacy_Accessibility"
                end tell
                display dialog "Mutter needs Accessibility permissions to auto-paste text. Please enable it in System Settings > Privacy & Security > Accessibility." buttons {"Open Settings", "Cancel"} default button "Open Settings"
            '''
            try:
                subprocess.run(['osascript', '-e', dialog_script], check=True)
            except:
                logger.error("Failed to show accessibility permission dialog")
                
        # Check if we have accessibility permissions
        if not check_accessibility_permissions():
            logger.warning("No accessibility permissions, requesting from user")
            request_accessibility_permissions()
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
            logger.error(f"Failed to send keystrokes via AppleScript: {e}")
            # If we get a permission error, request permissions
            if "not allowed assistive access" in str(e).lower():
                request_accessibility_permissions()
        except Exception as e:
            logger.error(f"Error executing AppleScript: {e}")
                
