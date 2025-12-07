"""Wayland-compatible hotkey handler using evdev.

This handler reads keyboard events directly from input devices,
which works on both X11 and Wayland. Requires the user to be in
the 'input' group to access /dev/input/event* devices.
"""

from .base import HotkeyHandler
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import Signal
import logging
from typing import Dict, Any, Optional, Set
import threading
import os

logger = logging.getLogger(__name__)

# Lazy import evdev to provide better error messages
evdev = None

def _import_evdev():
    global evdev
    if evdev is None:
        import evdev as _evdev
        evdev = _evdev
    return evdev


class WaylandHotkeyHandler(HotkeyHandler):
    """Handles global hotkeys on Linux/Wayland using evdev.
    
    This class reads keyboard events directly from input devices,
    bypassing the display server entirely. Works on both Wayland and X11.
    
    Requirements:
        - User must be in the 'input' group: sudo usermod -aG input $USER
        - Logout and login after adding to group
    """
    exit_hotkey_pressed = Signal()
    
    def __init__(self):
        super().__init__()
        self.registered_hotkeys: Dict[QKeySequence, Any] = {}
        self.registered_process_text_hotkey: Optional[QKeySequence] = None
        self.exit_hotkey: Optional[QKeySequence] = None
        self._lock = threading.Lock()
        self._is_key_held = False
        self._current_keys: Set[str] = set()
        self._should_stop = False
        self._listener_thread = None
        self._keyboards = []
        
        # Import and initialize evdev
        self._setup_keyboard_listener()
        
    def _find_keyboard_devices(self):
        """Find all keyboard input devices."""
        _import_evdev()
        keyboards = []
        
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        for device in devices:
            capabilities = device.capabilities()
            # Check if device has key events (EV_KEY = 1)
            if evdev.ecodes.EV_KEY in capabilities:
                keys = capabilities[evdev.ecodes.EV_KEY]
                # Check if it has typical keyboard keys (KEY_A = 30)
                if evdev.ecodes.KEY_A in keys:
                    logger.debug(f"Found keyboard device: {device.name} at {device.path}")
                    keyboards.append(device)
        
        return keyboards
        
    def _setup_keyboard_listener(self):
        """Set up the evdev keyboard listener."""
        try:
            self._keyboards = self._find_keyboard_devices()
            
            if not self._keyboards:
                raise RuntimeError(
                    "No keyboard devices found. Make sure you're in the 'input' group."
                )
            
            logger.info(f"Found {len(self._keyboards)} keyboard device(s)")
            
            # Start listener thread
            self._should_stop = False
            self._listener_thread = threading.Thread(
                target=self._listen_loop,
                daemon=True
            )
            self._listener_thread.start()
            logger.info("evdev keyboard listener started successfully")
            
        except PermissionError as e:
            raise RuntimeError(
                f"Permission denied accessing input devices. "
                f"Add yourself to the 'input' group:\n"
                f"  sudo usermod -aG input $USER\n"
                f"Then logout and login again."
            ) from e
        except Exception as e:
            logger.error(f"Failed to initialize evdev keyboard listener: {e}")
            raise RuntimeError(f"Failed to initialize hotkey handler: {e}") from e
    
    def _listen_loop(self):
        """Main loop for reading keyboard events."""
        _import_evdev()
        
        try:
            # Use select to monitor multiple devices
            from selectors import DefaultSelector, EVENT_READ
            selector = DefaultSelector()
            
            for keyboard in self._keyboards:
                selector.register(keyboard, EVENT_READ)
            
            while not self._should_stop:
                # Wait for events with timeout
                for key, mask in selector.select(timeout=0.1):
                    device = key.fileobj
                    try:
                        for event in device.read():
                            if event.type == evdev.ecodes.EV_KEY:
                                self._handle_key_event(event)
                    except BlockingIOError:
                        pass
                    except OSError as e:
                        # Device disconnected
                        logger.warning(f"Device error: {e}")
                        
        except Exception as e:
            logger.error(f"Error in evdev listener loop: {e}")
        finally:
            selector.close()
    
    def _handle_key_event(self, event):
        """Handle a key event from evdev."""
        _import_evdev()
        
        key_str = self._evdev_to_qt_key(event.code)
        if not key_str:
            return
            
        # event.value: 0 = release, 1 = press, 2 = repeat
        if event.value == 1:  # Key press
            self._on_press(key_str)
        elif event.value == 0:  # Key release
            self._on_release(key_str)
    
    def _on_press(self, key_str: str):
        """Handle key press events."""
        try:
            with self._lock:
                self._current_keys.add(key_str)
                logger.debug(f"Current keys: {self._current_keys}")
                
                # Check if this is the process text hotkey
                if (self.registered_process_text_hotkey and 
                    self._check_hotkey_match(self.registered_process_text_hotkey)):
                    logger.debug("Process text hotkey pressed")
                    self.process_text_hotkey_pressed.emit()
                    return
                    
                # Check if this is the exit hotkey
                if self.exit_hotkey and self._check_hotkey_match(self.exit_hotkey):
                    logger.info(f"Exit hotkey detected: {self._current_keys}")
                    self.exit_hotkey_pressed.emit()
                    return
                    
                # Regular hotkey handling
                for hotkey in self.registered_hotkeys:
                    if self._check_hotkey_match(hotkey):
                        if not self._is_key_held:
                            self._is_key_held = True
                            logger.debug(f"Hotkey pressed: {self._current_keys}")
                            self.hotkey_pressed.emit()
                        return
                        
        except Exception as e:
            logger.error(f"Error handling key press: {e}")
            
    def _on_release(self, key_str: str):
        """Handle key release events."""
        try:
            with self._lock:
                import time
                time.sleep(0.1)
                
                # Check if this was a registered hotkey BEFORE removing the key
                for hotkey in self.registered_hotkeys:
                    if self._check_hotkey_match(hotkey):
                        if self._is_key_held:
                            self._is_key_held = False
                            logger.debug(f"Hotkey released: {self._current_keys}")
                            self.hotkey_released.emit()
                            if key_str in self._current_keys:
                                self._current_keys.remove(key_str)
                            return
                
                if key_str in self._current_keys:
                    self._current_keys.remove(key_str)
                        
        except Exception as e:
            logger.error(f"Error handling key release: {e}")
            
    def _check_hotkey_match(self, hotkey: QKeySequence) -> bool:
        """Check if the current set of pressed keys matches a hotkey combination."""
        try:
            hotkey_str = hotkey.toString()
            logger.debug(f"Checking hotkey match: {hotkey_str} against {self._current_keys}")
            hotkey_parts = set(hotkey_str.split('+'))
            return hotkey_parts.issubset(self._current_keys)
        except Exception as e:
            logger.error(f"Error checking hotkey match: {e}")
            return False
    
    def _evdev_to_qt_key(self, code: int) -> Optional[str]:
        """Convert evdev key code to Qt key sequence string."""
        _import_evdev()
        
        # Modifier keys
        MODIFIERS = {
            evdev.ecodes.KEY_LEFTCTRL: "Ctrl",
            evdev.ecodes.KEY_RIGHTCTRL: "Ctrl",
            evdev.ecodes.KEY_LEFTSHIFT: "Shift",
            evdev.ecodes.KEY_RIGHTSHIFT: "Shift",
            evdev.ecodes.KEY_LEFTALT: "Alt",
            evdev.ecodes.KEY_RIGHTALT: "Alt",
            evdev.ecodes.KEY_LEFTMETA: "Meta",
            evdev.ecodes.KEY_RIGHTMETA: "Meta",
        }
        
        # Special keys
        SPECIAL_KEYS = {
            evdev.ecodes.KEY_ESC: "Esc",
            evdev.ecodes.KEY_SPACE: "Space",
            evdev.ecodes.KEY_ENTER: "Return",
            evdev.ecodes.KEY_BACKSPACE: "Backspace",
            evdev.ecodes.KEY_TAB: "Tab",
            evdev.ecodes.KEY_DELETE: "Delete",
            evdev.ecodes.KEY_HOME: "Home",
            evdev.ecodes.KEY_END: "End",
            evdev.ecodes.KEY_PAGEUP: "PgUp",
            evdev.ecodes.KEY_PAGEDOWN: "PgDown",
            evdev.ecodes.KEY_LEFT: "Left",
            evdev.ecodes.KEY_RIGHT: "Right",
            evdev.ecodes.KEY_UP: "Up",
            evdev.ecodes.KEY_DOWN: "Down",
            evdev.ecodes.KEY_INSERT: "Insert",
            evdev.ecodes.KEY_F1: "F1",
            evdev.ecodes.KEY_F2: "F2",
            evdev.ecodes.KEY_F3: "F3",
            evdev.ecodes.KEY_F4: "F4",
            evdev.ecodes.KEY_F5: "F5",
            evdev.ecodes.KEY_F6: "F6",
            evdev.ecodes.KEY_F7: "F7",
            evdev.ecodes.KEY_F8: "F8",
            evdev.ecodes.KEY_F9: "F9",
            evdev.ecodes.KEY_F10: "F10",
            evdev.ecodes.KEY_F11: "F11",
            evdev.ecodes.KEY_F12: "F12",
        }
        
        # Letter keys (KEY_A = 30 through KEY_Z)
        LETTER_KEYS = {
            evdev.ecodes.KEY_A: "A",
            evdev.ecodes.KEY_B: "B",
            evdev.ecodes.KEY_C: "C",
            evdev.ecodes.KEY_D: "D",
            evdev.ecodes.KEY_E: "E",
            evdev.ecodes.KEY_F: "F",
            evdev.ecodes.KEY_G: "G",
            evdev.ecodes.KEY_H: "H",
            evdev.ecodes.KEY_I: "I",
            evdev.ecodes.KEY_J: "J",
            evdev.ecodes.KEY_K: "K",
            evdev.ecodes.KEY_L: "L",
            evdev.ecodes.KEY_M: "M",
            evdev.ecodes.KEY_N: "N",
            evdev.ecodes.KEY_O: "O",
            evdev.ecodes.KEY_P: "P",
            evdev.ecodes.KEY_Q: "Q",
            evdev.ecodes.KEY_R: "R",
            evdev.ecodes.KEY_S: "S",
            evdev.ecodes.KEY_T: "T",
            evdev.ecodes.KEY_U: "U",
            evdev.ecodes.KEY_V: "V",
            evdev.ecodes.KEY_W: "W",
            evdev.ecodes.KEY_X: "X",
            evdev.ecodes.KEY_Y: "Y",
            evdev.ecodes.KEY_Z: "Z",
        }
        
        # Number keys
        NUMBER_KEYS = {
            evdev.ecodes.KEY_0: "0",
            evdev.ecodes.KEY_1: "1",
            evdev.ecodes.KEY_2: "2",
            evdev.ecodes.KEY_3: "3",
            evdev.ecodes.KEY_4: "4",
            evdev.ecodes.KEY_5: "5",
            evdev.ecodes.KEY_6: "6",
            evdev.ecodes.KEY_7: "7",
            evdev.ecodes.KEY_8: "8",
            evdev.ecodes.KEY_9: "9",
        }
        
        if code in MODIFIERS:
            return MODIFIERS[code]
        if code in SPECIAL_KEYS:
            return SPECIAL_KEYS[code]
        if code in LETTER_KEYS:
            return LETTER_KEYS[code]
        if code in NUMBER_KEYS:
            return NUMBER_KEYS[code]
            
        return None
            
    def register_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Register a global hotkey."""
        if not key_sequence or key_sequence.isEmpty() or key_sequence.count() != 1:
            logger.warning("Only single key combinations are supported")
            return False
            
        with self._lock:
            if key_sequence in self.registered_hotkeys:
                return True
                
            try:
                self.registered_hotkeys[key_sequence] = True
                logger.info(f"Successfully registered hotkey: {key_sequence.toString()}")
                return True
            except Exception as e:
                logger.error(f"Error registering hotkey {key_sequence}: {e}")
                return False
                
    def unregister_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Unregister a previously registered hotkey."""
        with self._lock:
            if key_sequence not in self.registered_hotkeys:
                return True
                
            try:
                del self.registered_hotkeys[key_sequence]
                return True
            except Exception as e:
                logger.error(f"Error unregistering hotkey {key_sequence}: {e}")
                return False
                
    def register_process_text_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Register a hotkey for text processing."""
        if not key_sequence or key_sequence.isEmpty() or key_sequence.count() != 1:
            logger.warning("Invalid key sequence for process text hotkey")
            return False
            
        with self._lock:
            if self.registered_process_text_hotkey:
                self.unregister_hotkey(self.registered_process_text_hotkey)
                
            if self.register_hotkey(key_sequence):
                self.registered_process_text_hotkey = key_sequence
                logger.info(f"Successfully registered process text hotkey: {key_sequence.toString()}")
                return True
                
            return False
            
    def shutdown(self) -> None:
        """Clean up resources before shutdown."""
        logger.debug("Shutting down evdev hotkey handler")
        self._should_stop = True
        
        if self._listener_thread:
            self._listener_thread.join(timeout=1.0)
            
        for keyboard in self._keyboards:
            try:
                keyboard.close()
            except Exception as e:
                logger.error(f"Error closing keyboard device: {e}")
                
    def __del__(self):
        """Cleanup on deletion."""
        self.shutdown()
        
    def is_key_held(self) -> bool:
        """Returns whether the hotkey is currently being held down."""
        with self._lock:
            return self._is_key_held

