from .base import HotkeyHandler
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import Qt, Signal, QMetaObject
import logging
from typing import Dict, Any, Optional, Set
import threading
from pynput import keyboard
import time

logger = logging.getLogger(__name__)

class LinuxHotkeyHandler(HotkeyHandler):
    """Handles global hotkeys on Linux using pynput.
    
    This class manages registration and unregistration of global hotkeys,
    and emits signals when hotkeys are pressed/released.
    """
    # Add a new signal for exit hotkey
    exit_hotkey_pressed = Signal()
    
    def __init__(self):
        super().__init__()
        self.registered_hotkeys: Dict[QKeySequence, Any] = {}
        self.registered_process_text_hotkey: Optional[QKeySequence] = None
        self.process_text_hotkey_id: Optional[int] = None
        self.exit_hotkey: Optional[QKeySequence] = None
        self._lock = threading.RLock()  # Use RLock for reentrant locking
        self._is_key_held = False
        self._listener = None
        self._current_keys: Set[str] = set()
        self._should_stop = False
        
        # Initialize the keyboard listener
        self._setup_keyboard_listener()
        
    def _setup_keyboard_listener(self):
        """Set up the keyboard listener."""
        try:
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release
            )
            self._listener.start()
            logger.info("Keyboard listener started successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize keyboard listener: {e}")
            raise RuntimeError(f"Failed to initialize hotkey handler: {e}")
    
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
            
    def _on_press(self, key):
        """Handle key press events."""
        try:
            # Convert pynput key to string
            key_str = self._pynput_to_qt_key(key)
            if not key_str:
                return
                
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
            
    def _on_release(self, key):
        """Handle key release events."""
        try:
            # Convert pynput key to string
            key_str = self._pynput_to_qt_key(key)
            if not key_str:
                return
                
            with self._lock:
                # Add a small delay to prevent premature stopping
                time.sleep(0.1)
                
                # Check if this was a registered hotkey BEFORE removing the key
                for hotkey in self.registered_hotkeys:
                    if self._check_hotkey_match(hotkey):
                        if self._is_key_held:
                            self._is_key_held = False
                            logger.debug(f"Hotkey released: {self._current_keys}")
                            self._emit_signal_safely(self.hotkey_released)
                            # Remove the key after emitting the signal
                            self._current_keys.discard(key_str)
                            logger.debug(f"Current keys after release: {self._current_keys}")
                            return
                
                # If no hotkey match, just remove the key
                self._current_keys.discard(key_str)
                logger.debug(f"Current keys after release: {self._current_keys}")
                        
        except Exception as e:
            logger.error(f"Error handling key release: {e}")
            
    def _check_hotkey_match(self, hotkey: QKeySequence) -> bool:
        """Check if the current set of pressed keys matches a hotkey combination."""
        try:
            hotkey_str = hotkey.toString()
            logger.debug(f"Checking hotkey match: {hotkey_str} against {self._current_keys}")
            
            # Split the hotkey string into individual keys
            hotkey_parts = set(hotkey_str.split('+'))
            
            # Check if all parts of the hotkey are currently pressed
            return hotkey_parts.issubset(self._current_keys)
            
        except Exception as e:
            logger.error(f"Error checking hotkey match: {e}")
            return False
            
    def _pynput_to_qt_key(self, key) -> Optional[str]:
        """Convert pynput key to Qt key sequence string."""
        try:
            # Handle special keys
            if isinstance(key, keyboard.Key):
                if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                    return "Ctrl"
                elif key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                    return "Shift"
                elif key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                    return "Alt"
                elif key == keyboard.Key.cmd_l or key == keyboard.Key.cmd_r:
                    return "Meta"
                elif key == keyboard.Key.esc:
                    return "Esc"
                elif key == keyboard.Key.space:
                    return "Space"
                elif key == keyboard.Key.enter:
                    return "Return"
                elif key == keyboard.Key.backspace:
                    return "Backspace"
                elif key == keyboard.Key.tab:
                    return "Tab"
                elif key == keyboard.Key.delete:
                    return "Delete"
                elif key == keyboard.Key.home:
                    return "Home"
                elif key == keyboard.Key.end:
                    return "End"
                elif key == keyboard.Key.page_up:
                    return "PgUp"
                elif key == keyboard.Key.page_down:
                    return "PgDown"
                elif key == keyboard.Key.left:
                    return "Left"
                elif key == keyboard.Key.right:
                    return "Right"
                elif key == keyboard.Key.up:
                    return "Up"
                elif key == keyboard.Key.down:
                    return "Down"
                elif key == keyboard.Key.insert:
                    return "Insert"
                elif key == keyboard.Key.f1:
                    return "F1"
                elif key == keyboard.Key.f2:
                    return "F2"
                elif key == keyboard.Key.f3:
                    return "F3"
                elif key == keyboard.Key.f4:
                    return "F4"
                elif key == keyboard.Key.f5:
                    return "F5"
                elif key == keyboard.Key.f6:
                    return "F6"
                elif key == keyboard.Key.f7:
                    return "F7"
                elif key == keyboard.Key.f8:
                    return "F8"
                elif key == keyboard.Key.f9:
                    return "F9"
                elif key == keyboard.Key.f10:
                    return "F10"
                elif key == keyboard.Key.f11:
                    return "F11"
                elif key == keyboard.Key.f12:
                    return "F12"
                else:
                    return None
                    
            # Handle regular keys
            if hasattr(key, 'char') and key.char:
                return key.char.upper()
                
            return None
            
        except Exception as e:
            logger.error(f"Error converting pynput key to Qt key sequence: {e}")
            return None
            
    def register_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Register a global hotkey.
        
        Args:
            key_sequence: The key combination to register
            
        Returns:
            True if registration was successful, False otherwise
        """
        if not key_sequence or key_sequence.isEmpty() or key_sequence.count() != 1:
            logger.warning("Only single key combinations are supported")
            return False
            
        with self._lock:
            if key_sequence in self.registered_hotkeys:
                return True
                
            try:
                # Store the hotkey
                self.registered_hotkeys[key_sequence] = True
                logger.info(f"Successfully registered hotkey: {key_sequence.toString()}")
                return True
                
            except Exception as e:
                logger.error(f"Error registering hotkey {key_sequence}: {e}")
                return False
                
    def unregister_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Unregister a previously registered hotkey.
        
        Args:
            key_sequence: The key combination to unregister
            
        Returns:
            True if unregistration was successful, False otherwise
        """
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
        """Register a hotkey for text processing
        
        Args:
            key_sequence: The key sequence to register
            
        Returns:
            bool: True if registration succeeded, False otherwise
        """
        if not key_sequence or key_sequence.isEmpty() or key_sequence.count() != 1:
            logger.warning("Invalid key sequence for process text hotkey")
            return False
            
        with self._lock:
            # Unregister previous process text hotkey if it exists
            if self.registered_process_text_hotkey:
                self.unregister_hotkey(self.registered_process_text_hotkey)
                
            # Register the new hotkey
            if self.register_hotkey(key_sequence):
                self.registered_process_text_hotkey = key_sequence
                logger.info(f"Successfully registered process text hotkey: {key_sequence.toString()}")
                return True
                
            return False
            
    def shutdown(self) -> None:
        """Clean up resources before shutdown."""
        logger.debug("Shutting down hotkey handler")
        self._should_stop = True
        
        # Stop the keyboard listener
        if self._listener:
            try:
                self._listener.stop()
                # Wait for listener thread to finish
                if hasattr(self._listener, 'join'):
                    self._listener.join(timeout=1.0)
            except Exception as e:
                logger.debug(f"Error stopping keyboard listener: {e}")
            self._listener = None
        
        # Clear state
        with self._lock:
            self.registered_hotkeys.clear()
            self._current_keys.clear()
        
        logger.debug("Hotkey handler shutdown complete")
                
    def __del__(self):
        """Cleanup registered hotkeys on deletion."""
        try:
            self.shutdown()
        except Exception:
            pass
        
    def is_key_held(self) -> bool:
        """Returns whether the hotkey is currently being held down."""
        with self._lock:
            return self._is_key_held
