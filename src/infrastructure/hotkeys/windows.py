from .base import HotkeyHandler
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import Qt, Signal
import win32con
import win32api
import win32gui
import threading
import ctypes
from typing import Dict, Tuple, Optional
import logging
from threading import Lock

logger = logging.getLogger(__name__)

# Define missing constants that might not be in older versions of win32con
MOD_NOREPEAT = 0x4000  # Define MOD_NOREPEAT manually since it's not in all win32con versions

# Define ctypes versions of Windows API functions as fallback
try:
    # Try to use the functions from win32gui
    register_hotkey_func = win32gui.RegisterHotKey
    unregister_hotkey_func = win32gui.UnregisterHotKey
    logger.debug("Using RegisterHotKey from win32gui")
except AttributeError:
    # Fallback to direct Windows API via ctypes
    logger.debug("RegisterHotKey not found in win32gui, falling back to ctypes")
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    
    # Define the function prototypes
    user32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    user32.RegisterHotKey.restype = ctypes.c_bool
    
    user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.UnregisterHotKey.restype = ctypes.c_bool
    
    # Create wrapper functions
    def register_hotkey_func(hwnd, id, modifiers, vk):
        return user32.RegisterHotKey(hwnd, id, modifiers, vk)
    
    def unregister_hotkey_func(hwnd, id):
        return user32.UnregisterHotKey(hwnd, id)

class WindowsHotkeyHandler(HotkeyHandler):
    """Handles global hotkeys on Windows using Win32 API.
    
    This class manages registration and unregistration of global hotkeys,
    and emits signals when hotkeys are pressed/released.
    """
    # Add a new signal for exit hotkey
    exit_hotkey_pressed = Signal()
    
    def __init__(self):
        super().__init__()
        self.registered_hotkeys: Dict[QKeySequence, int] = {}
        self._lock = Lock()
        self.next_id = 1
        self._hwnd: Optional[int] = None
        self._message_thread: Optional[threading.Thread] = None
        self._is_key_held = False  # Track key state
        self.registered_process_text_hotkey: Optional[QKeySequence] = None
        self.process_text_hotkey_id: Optional[int] = None
        self._setup_message_window()

    def _setup_message_window(self) -> None:
        """Creates a hidden window to receive hotkey messages.
        
        Raises:
            RuntimeError: If window creation fails
        """
        def window_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> bool:
            if msg == win32con.WM_HOTKEY:
                # wparam contains the hotkey ID
                hotkey_id = wparam
                
                # For WM_HOTKEY, Windows doesn't provide separate down/up events
                # We use a toggle pattern: first press starts recording, second press stops
                logger.debug(f"Hotkey message received: ID={hotkey_id}, lparam={hex(lparam)}")
                
                # Check if this is the process text hotkey
                if self.process_text_hotkey_id is not None and hotkey_id == self.process_text_hotkey_id:
                    logger.debug("Process text hotkey pressed")
                    self.process_text_hotkey_pressed.emit()
                    return True
                
                # Try to find which hotkey this corresponds to
                key_sequence = None
                for k, v in self.registered_hotkeys.items():
                    if v == hotkey_id:
                        key_sequence = k
                        break
                
                if key_sequence:
                    logger.debug(f"Matched to hotkey: {key_sequence.toString()}")
                    
                    # Special handling for Ctrl+Shift+Q (exit hotkey)
                    if key_sequence.toString() == "Ctrl+Shift+Q":
                        logger.info("Exit hotkey detected, emitting exit_hotkey_pressed")
                        self.exit_hotkey_pressed.emit()
                        return True
                    
                    # Regular toggle behavior for recording hotkeys
                    with self._lock:
                        if not self._is_key_held:
                            # First press (start recording)
                            self._is_key_held = True
                            logger.debug("Toggling state to RECORDING (emitting hotkey_pressed)")
                            self.hotkey_pressed.emit()
                        else:
                            # Second press (stop recording)
                            self._is_key_held = False
                            logger.debug("Toggling state to STOPPED (emitting hotkey_released)")
                            logger.debug("This should trigger SystemTrayIcon.on_stop_hotkey_pressed via signal connection")
                            self.hotkey_released.emit()
                            logger.debug("hotkey_released signal emitted")
                else:
                    logger.warning(f"Received hotkey ID {hotkey_id} doesn't match any registered hotkey")
                
            return True
            
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = window_proc
        wc.lpszClassName = "VoiceRecorderHotkey"
        
        try:
            win32gui.RegisterClass(wc)
            self._hwnd = win32gui.CreateWindow(
                wc.lpszClassName,
                "Memo Hotkey Window",
                0, 0, 0, 0, 0, 0, 0, None, None
            )
            
            self._message_thread = threading.Thread(
                target=self._message_loop,
                daemon=True,
                name="HotkeyMessageLoop"
            )
            self._message_thread.start()
            
        except Exception as e:
            logger.error(f"Failed to setup hotkey window: {e}")
            raise RuntimeError(f"Failed to initialize hotkey handler: {e}")

    def _message_loop(self) -> None:
        """Runs the Windows message loop in a separate thread."""
        try:
            logger.debug("Starting hotkey message loop")
            # Use PeekMessage instead of GetMessage to avoid blocking
            while True:
                msg = win32gui.GetMessage(None, 0, 0)
                if msg is None or msg == 0:
                    logger.debug("Message loop exiting")
                    break
                    
                logger.debug(f"Processing message: {msg}")
                win32gui.TranslateMessage(msg)
                win32gui.DispatchMessage(msg)
        except Exception as e:
            logger.error(f"Message loop error: {e}", exc_info=True)
            
    def _convert_key_sequence(self, key_sequence: QKeySequence) -> Tuple[int, int]:
        """Converts Qt key sequence to Win32 modifiers and virtual key code.
        
        Args:
            key_sequence: The Qt key sequence to convert
            
        Returns:
            Tuple of (modifiers, virtual_key_code)
        """
        # Convert key sequence to string
        key_str = key_sequence.toString()
        logger.debug(f"Converting key sequence: {key_str}")
        
        # Parse modifiers and key from string
        modifiers = 0
        if "Ctrl" in key_str:
            modifiers |= win32con.MOD_CONTROL
        if "Shift" in key_str:
            modifiers |= win32con.MOD_SHIFT
        if "Alt" in key_str:
            modifiers |= win32con.MOD_ALT
            
        # Extract the key (last character in the key string)
        key_char = key_str.split("+")[-1]
        if len(key_char) == 1:  # Single character key
            vk = win32api.VkKeyScan(key_char) & 0xFF
        else:
            # Handle special keys
            if key_char == "F1":
                vk = win32con.VK_F1
            elif key_char == "F2":
                vk = win32con.VK_F2
            elif key_char == "F3":
                vk = win32con.VK_F3
            elif key_char == "F4":
                vk = win32con.VK_F4
            elif key_char == "F5":
                vk = win32con.VK_F5
            elif key_char == "F6":
                vk = win32con.VK_F6
            elif key_char == "F7":
                vk = win32con.VK_F7
            elif key_char == "F8":
                vk = win32con.VK_F8
            elif key_char == "F9":
                vk = win32con.VK_F9
            elif key_char == "F10":
                vk = win32con.VK_F10
            elif key_char == "F11":
                vk = win32con.VK_F11
            elif key_char == "F12":
                vk = win32con.VK_F12
            elif key_char == "Space":
                vk = win32con.VK_SPACE
            elif key_char == "Ins":
                vk = win32con.VK_INSERT
            elif key_char == "Del":
                vk = win32con.VK_DELETE
            elif key_char == "Home":
                vk = win32con.VK_HOME
            elif key_char == "End":
                vk = win32con.VK_END
            elif key_char == "PgUp":
                vk = win32con.VK_PRIOR
            elif key_char == "PgDown":
                vk = win32con.VK_NEXT
            elif key_char == "Esc":
                vk = win32con.VK_ESCAPE
            else:
                # For single letter keys
                vk = ord(key_char[0].upper())
                
        logger.debug(f"Converted to modifiers: {modifiers}, vk: {vk}")
        return modifiers, vk

    def _validate_key_sequence(self, key_sequence: QKeySequence) -> bool:
        """Validates if the key sequence is supported.
        
        Args:
            key_sequence: The key sequence to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not key_sequence or key_sequence.isEmpty() or key_sequence.count() != 1:
            logger.warning("Only single key combinations are supported")
            return False
            
        try:
            self._convert_key_sequence(key_sequence)
            return True
        except Exception as e:
            logger.warning(f"Invalid key sequence {key_sequence}: {e}")
            return False

    def register_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Registers a global hotkey.
        
        Args:
            key_sequence: The key combination to register
            
        Returns:
            True if registration was successful, False otherwise
        """
        if not self._validate_key_sequence(key_sequence):
            return False
            
        with self._lock:  # Use lock for thread safety
            if key_sequence in self.registered_hotkeys:
                return True
            
            try:
                modifiers, vk = self._convert_key_sequence(key_sequence)
                # Add MOD_NOREPEAT to prevent key repetition
                modifiers |= MOD_NOREPEAT
                hotkey_id = self.next_id
                
                logger.info(f"Registering hotkey: {key_sequence.toString()}, modifiers={modifiers}, vk={vk}, id={hotkey_id}")
                if register_hotkey_func(self._hwnd, hotkey_id, modifiers, vk):
                    self.registered_hotkeys[key_sequence] = hotkey_id
                    self.next_id += 1
                    logger.info(f"Successfully registered hotkey: {key_sequence.toString()}")
                    return True
                    
                error_code = ctypes.get_last_error() if 'ctypes' in globals() else 0
                logger.warning(f"Failed to register hotkey {key_sequence}, error code: {error_code}")
                return False
                
            except Exception as e:
                logger.error(f"Error registering hotkey {key_sequence}: {e}", exc_info=True)
                return False

    def unregister_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Unregisters a previously registered hotkey.
        
        Args:
            key_sequence: The key combination to unregister
            
        Returns:
            True if unregistration was successful, False otherwise
        """
        with self._lock:  # Use lock for thread safety
            if key_sequence not in self.registered_hotkeys:
                return True
            
            try:
                hotkey_id = self.registered_hotkeys[key_sequence]
                if unregister_hotkey_func(self._hwnd, hotkey_id):
                    del self.registered_hotkeys[key_sequence]
                    return True
                    
                logger.warning(f"Failed to unregister hotkey {key_sequence}")
                return False
                
            except Exception as e:
                logger.error(f"Error unregistering hotkey {key_sequence}: {e}")
                return False

    def register_process_text_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Register a hotkey for text processing
        
        Args:
            key_sequence: The key sequence to register
            
        Returns:
            bool: True if registration succeeded, False otherwise
        """
        if not self._validate_key_sequence(key_sequence):
            logger.warning(f"Invalid key sequence for process text hotkey: {key_sequence}")
            return False
            
        # Unregister previous process text hotkey if it exists
        if self.registered_process_text_hotkey and self.process_text_hotkey_id:
            try:
                if unregister_hotkey_func(self._hwnd, self.process_text_hotkey_id):
                    logger.debug(f"Unregistered previous process text hotkey: {self.registered_process_text_hotkey.toString()}")
                else:
                    logger.warning(f"Failed to unregister previous process text hotkey: {self.registered_process_text_hotkey.toString()}")
            except Exception as e:
                logger.error(f"Error unregistering process text hotkey: {e}")
        
        # Generate a new ID for this hotkey
        hotkey_id = self.next_id
        self.next_id += 1
        
        # Convert Qt key sequence to Win32 modifiers and key code
        modifiers, vk = self._convert_key_sequence(key_sequence)
        
        # Add the MOD_NOREPEAT flag for instant triggering
        modifiers |= MOD_NOREPEAT
        
        # Try to register the hotkey
        try:
            if register_hotkey_func(self._hwnd, hotkey_id, modifiers, vk):
                logger.info(f"Registered process text hotkey: {key_sequence.toString()} with ID {hotkey_id}")
                self.registered_process_text_hotkey = key_sequence
                self.process_text_hotkey_id = hotkey_id
                return True
            else:
                logger.error(f"Failed to register process text hotkey: {key_sequence.toString()}")
                return False
        except Exception as e:
            logger.error(f"Error registering process text hotkey: {e}")
            return False

    def shutdown(self) -> None:
        """Clean up resources before shutdown."""
        logger.debug("Shutting down hotkey handler")
        
        # Unregister all hotkeys
        for key_seq, hotkey_id in list(self.registered_hotkeys.items()):
            try:
                if unregister_hotkey_func(self._hwnd, hotkey_id):
                    logger.debug(f"Unregistered hotkey: {key_seq.toString()}")
                else:
                    logger.warning(f"Failed to unregister hotkey: {key_seq.toString()}")
            except Exception as e:
                logger.error(f"Error unregistering hotkey: {e}")
        
        # Unregister process text hotkey if it exists
        if self.registered_process_text_hotkey and self.process_text_hotkey_id:
            try:
                if unregister_hotkey_func(self._hwnd, self.process_text_hotkey_id):
                    logger.debug(f"Unregistered process text hotkey: {self.registered_process_text_hotkey.toString()}")
                else:
                    logger.warning(f"Failed to unregister process text hotkey: {self.registered_process_text_hotkey.toString()}")
            except Exception as e:
                logger.error(f"Error unregistering process text hotkey: {e}")
        
        # Close the window and terminate the message thread
        if self._hwnd:
            try:
                win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
                logger.debug("Posted WM_CLOSE to message window")
            except Exception as e:
                logger.error(f"Error posting WM_CLOSE: {e}")

    def __del__(self):
        """Cleanup registered hotkeys on deletion."""
        for key_sequence in list(self.registered_hotkeys.keys()):
            self.unregister_hotkey(key_sequence)

    def is_key_held(self) -> bool:
        """Returns whether the hotkey is currently being held down."""
        with self._lock:
            return self._is_key_held 