"""Wayland-compatible hotkey handler using evdev.

This handler reads keyboard events directly from input devices,
which works on both X11 and Wayland. Requires the user to be in
the 'input' group to access /dev/input/event* devices.
"""

from .base import HotkeyHandler
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import Signal, Qt, QMetaObject, Q_ARG
import logging
from typing import Dict, Any, Optional, Set, List
import threading
import os
import time
import weakref

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
        self._lock = threading.RLock()  # Use RLock for reentrant locking
        self._is_key_held = False
        self._current_keys: Set[str] = set()
        self._should_stop = False
        self._listener_thread = None
        self._keyboards: List = []
        self._device_paths: Set[str] = set()  # Track device paths
        self._reconnect_interval = 5.0  # Seconds between device reconnection attempts
        self._last_reconnect_attempt = 0
        
        # Import and initialize evdev
        self._setup_keyboard_listener()
        
    def _find_keyboard_devices(self) -> List:
        """Find all keyboard input devices."""
        _import_evdev()
        keyboards = []
        
        try:
            device_paths = evdev.list_devices()
            for path in device_paths:
                try:
                    device = evdev.InputDevice(path)
                    capabilities = device.capabilities()
                    # Check if device has key events (EV_KEY = 1)
                    if evdev.ecodes.EV_KEY in capabilities:
                        keys = capabilities[evdev.ecodes.EV_KEY]
                        # Check if it has typical keyboard keys (KEY_A = 30)
                        if evdev.ecodes.KEY_A in keys:
                            logger.debug(f"Found keyboard device: {device.name} at {device.path}")
                            keyboards.append(device)
                except (OSError, PermissionError) as e:
                    logger.debug(f"Could not access device {path}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error listing input devices: {e}")
        
        return keyboards
        
    def _setup_keyboard_listener(self):
        """Set up the evdev keyboard listener."""
        try:
            self._keyboards = self._find_keyboard_devices()
            self._device_paths = {kb.path for kb in self._keyboards}
            
            if not self._keyboards:
                raise RuntimeError(
                    "No keyboard devices found. Make sure you're in the 'input' group."
                )
            
            logger.info(f"Found {len(self._keyboards)} keyboard device(s)")
            
            # Start listener thread
            self._should_stop = False
            self._listener_thread = threading.Thread(
                target=self._listen_loop,
                daemon=True,
                name="EvdevHotkeyListener"
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
    
    def _refresh_devices(self):
        """Refresh the list of keyboard devices, handling disconnects and reconnects."""
        _import_evdev()
        
        current_time = time.time()
        if current_time - self._last_reconnect_attempt < self._reconnect_interval:
            return False
        
        self._last_reconnect_attempt = current_time
        
        try:
            # Find new keyboards
            new_keyboards = self._find_keyboard_devices()
            new_paths = {kb.path for kb in new_keyboards}
            
            # Close devices that are no longer present
            with self._lock:
                for kb in self._keyboards[:]:
                    if kb.path not in new_paths:
                        try:
                            logger.info(f"Closing disconnected device: {kb.name}")
                            kb.close()
                        except Exception as e:
                            logger.debug(f"Error closing device: {e}")
                        self._keyboards.remove(kb)
                
                # Add new devices
                for kb in new_keyboards:
                    if kb.path not in self._device_paths:
                        logger.info(f"New keyboard device found: {kb.name} at {kb.path}")
                        self._keyboards.append(kb)
                
                self._device_paths = {kb.path for kb in self._keyboards}
                
            return len(self._keyboards) > 0
            
        except Exception as e:
            logger.error(f"Error refreshing devices: {e}")
            return False
    
    def _listen_loop(self):
        """Main loop for reading keyboard events."""
        _import_evdev()
        
        from selectors import DefaultSelector, EVENT_READ
        selector = None
        
        try:
            while not self._should_stop:
                # Create or recreate selector with current devices
                if selector is None:
                    selector = DefaultSelector()
                    with self._lock:
                        for keyboard in self._keyboards:
                            try:
                                selector.register(keyboard, EVENT_READ)
                            except (ValueError, OSError) as e:
                                logger.debug(f"Could not register device {keyboard.path}: {e}")
                
                if not self._keyboards:
                    # No devices available, wait and try to reconnect
                    logger.warning("No keyboard devices available, waiting for reconnection...")
                    time.sleep(self._reconnect_interval)
                    if self._refresh_devices():
                        # Recreate selector with new devices
                        if selector:
                            try:
                                selector.close()
                            except Exception:
                                pass
                        selector = None
                    continue
                
                try:
                    # Wait for events with timeout
                    events = selector.select(timeout=0.5)
                    
                    devices_to_remove = []
                    
                    for key, mask in events:
                        device = key.fileobj
                        try:
                            for event in device.read():
                                if event.type == evdev.ecodes.EV_KEY:
                                    self._handle_key_event(event)
                        except BlockingIOError:
                            pass
                        except OSError as e:
                            # Device disconnected or error
                            if e.errno == 19:  # ENODEV - No such device
                                logger.warning(f"Device disconnected: {device.path}")
                                devices_to_remove.append(device)
                            else:
                                logger.warning(f"Device error on {device.path}: {e}")
                                devices_to_remove.append(device)
                    
                    # Remove disconnected devices and refresh
                    if devices_to_remove:
                        for device in devices_to_remove:
                            try:
                                selector.unregister(device)
                            except (KeyError, ValueError):
                                pass
                            try:
                                device.close()
                            except Exception:
                                pass
                            with self._lock:
                                if device in self._keyboards:
                                    self._keyboards.remove(device)
                                self._device_paths.discard(device.path)
                        
                        # Try to refresh devices
                        self._refresh_devices()
                        
                        # Recreate selector
                        try:
                            selector.close()
                        except Exception:
                            pass
                        selector = None
                        
                except (OSError, ValueError) as e:
                    logger.warning(f"Selector error: {e}")
                    # Recreate selector
                    if selector:
                        try:
                            selector.close()
                        except Exception:
                            pass
                        selector = None
                    time.sleep(0.5)
                    self._refresh_devices()
                        
        except Exception as e:
            logger.error(f"Error in evdev listener loop: {e}")
        finally:
            if selector:
                try:
                    selector.close()
                except Exception:
                    pass
            logger.debug("Evdev listener loop exited")
    
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
    
    def _emit_signal_safely(self, signal):
        """Emit a signal safely from a background thread using queued connection."""
        try:
            # Use QMetaObject.invokeMethod for thread-safe signal emission
            # This ensures the signal is processed in the main thread
            QMetaObject.invokeMethod(
                self,
                lambda: signal.emit(),
                Qt.ConnectionType.QueuedConnection
            )
        except Exception as e:
            logger.error(f"Error emitting signal: {e}")
            # Fallback to direct emission (may cause issues but better than nothing)
            try:
                signal.emit()
            except Exception as e2:
                logger.error(f"Fallback signal emission also failed: {e2}")
    
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
                    self._emit_signal_safely(self.process_text_hotkey_pressed)
                    return
                    
                # Check if this is the exit hotkey
                if self.exit_hotkey and self._check_hotkey_match(self.exit_hotkey):
                    logger.info(f"Exit hotkey detected: {self._current_keys}")
                    self._emit_signal_safely(self.exit_hotkey_pressed)
                    return
                    
                # Regular hotkey handling
                for hotkey in self.registered_hotkeys:
                    if self._check_hotkey_match(hotkey):
                        if not self._is_key_held:
                            self._is_key_held = True
                            logger.debug(f"Hotkey pressed: {self._current_keys}")
                            self._emit_signal_safely(self.hotkey_pressed)
                        return
                        
        except Exception as e:
            logger.error(f"Error handling key press: {e}")
            
    def _on_release(self, key_str: str):
        """Handle key release events."""
        try:
            with self._lock:
                # Small delay to prevent premature stopping
                time.sleep(0.1)
                
                # Check if this was a registered hotkey BEFORE removing the key
                for hotkey in self.registered_hotkeys:
                    if self._check_hotkey_match(hotkey):
                        if self._is_key_held:
                            self._is_key_held = False
                            logger.debug(f"Hotkey released: {self._current_keys}")
                            self._emit_signal_safely(self.hotkey_released)
                            if key_str in self._current_keys:
                                self._current_keys.discard(key_str)
                            return
                
                self._current_keys.discard(key_str)
                        
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
            self._listener_thread.join(timeout=2.0)
            if self._listener_thread.is_alive():
                logger.warning("Listener thread did not terminate in time")
            self._listener_thread = None
        
        with self._lock:
            for keyboard in self._keyboards:
                try:
                    keyboard.close()
                except Exception as e:
                    logger.debug(f"Error closing keyboard device: {e}")
            self._keyboards.clear()
            self._device_paths.clear()
        
        logger.debug("Evdev hotkey handler shutdown complete")
                
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.shutdown()
        except Exception:
            pass
        
    def is_key_held(self) -> bool:
        """Returns whether the hotkey is currently being held down."""
        with self._lock:
            return self._is_key_held
