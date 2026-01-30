import subprocess
import time
from PySide6.QtGui import QKeySequence
import ctypes
from ctypes import wintypes
import time
import logging

logger = logging.getLogger(__name__)


class WindowsSystemExtension:
    @staticmethod
    def paste_text(text_to_paste: str = None):
        """Paste text into the active window.

        Args:
            text_to_paste: Optional text to copy to clipboard before pasting.
                          If None, just simulates Ctrl+V with current clipboard content.
        """
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

        # Simulate Ctrl+V keystroke
        # Virtual Key Codes
        VK_CONTROL = 0x11
        VK_V = 0x56

        # Input types
        INPUT_KEYBOARD = 1

        # Key event types
        KEYEVENTF_KEYDOWN = 0x0000
        KEYEVENTF_KEYUP = 0x0002

        # Define structures for input simulation
        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
            ]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)
            ]

        class INPUT_union(ctypes.Union):
            _fields_ = [
                ("mi", MOUSEINPUT),
                ("ki", KEYBDINPUT),
                ("hi", HARDWAREINPUT)
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", wintypes.DWORD),
                ("union", INPUT_union)
            ]

        # Give a small delay for clipboard to stabilize
        time.sleep(0.5)

        # Prepare keystroke events:
        # Press Ctrl, Press V, Release V, Release Ctrl
        inputs = (INPUT * 4)()

        # Press Ctrl
        inputs[0].type = INPUT_KEYBOARD
        inputs[0].union.ki.wVk = VK_CONTROL
        inputs[0].union.ki.dwFlags = KEYEVENTF_KEYDOWN

        # Press V
        inputs[1].type = INPUT_KEYBOARD
        inputs[1].union.ki.wVk = VK_V
        inputs[1].union.ki.dwFlags = KEYEVENTF_KEYDOWN

        # Release V
        inputs[2].type = INPUT_KEYBOARD
        inputs[2].union.ki.wVk = VK_V
        inputs[2].union.ki.dwFlags = KEYEVENTF_KEYUP

        # Release Ctrl
        inputs[3].type = INPUT_KEYBOARD
        inputs[3].union.ki.wVk = VK_CONTROL
        inputs[3].union.ki.dwFlags = KEYEVENTF_KEYUP

        # Send keystrokes
        nInputs = len(inputs)
        cbSize = ctypes.c_int(ctypes.sizeof(INPUT))
        ctypes.windll.user32.SendInput(nInputs, ctypes.pointer(inputs), cbSize)

        logger.debug("Auto-paste keystrokes sent")

                
