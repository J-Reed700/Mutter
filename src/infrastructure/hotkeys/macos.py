import threading
import logging
from pynput import keyboard
from PySide6.QtCore import Signal, QObject
from PySide6.QtGui import QKeySequence
from .base import HotkeyHandler

logger = logging.getLogger(__name__)

class MacOSHotkeyHandler(HotkeyHandler):
    # Inherit signals from HotkeyHandler and add exit signal
    exit_hotkey_pressed = Signal()
    stop_hotkey_pressed = Signal()  # Add a specific signal for stopping

    def __init__(self):
        super().__init__()
        self._pressed_keys = set()
        # We'll use a dict to map a QKeySequence to its normalized frozenset of key names
        self.registered_hotkeys = {}  # { QKeySequence: frozenset(str) }
        self.registered_process_text_hotkey = None  # QKeySequence for process text
        self.exit_hotkey = None  # QKeySequence for exit

        # For tracking active hotkey state (to avoid duplicate signal emissions)
        self._active_hotkeys = {}  # { QKeySequence: bool }
        self._is_key_held = False  # Track recording state
        
        # Debug logging
        logger.debug("Initializing MacOSHotkeyHandler")

        # Start the keyboard listener in a background thread
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self._listener.start()
        logger.debug("MacOS keyboard listener started")

        # Add a flag to temporarily disable hotkeys
        self._hotkeys_enabled = True

    def _normalize_key(self, key):
        """
        Normalize a key from pynput.keyboard.Key or KeyCode to a lowercase string.
        """
        if isinstance(key, keyboard.KeyCode):
            return key.char.lower() if key.char else ""
        else:
            # Handle special keys like cmd, shift, etc.
            if hasattr(key, 'name'):
                # Map pynput key names to our expected format
                key_map = {
                    'cmd': 'command',
                    'ctrl': 'control',
                    'alt': 'alt',
                    'shift': 'shift'
                }
                name = key.name.lower()
                return key_map.get(name, name)
            return str(key).lower()

    def _parse_qkeysequence(self, key_sequence: QKeySequence):
        """
        Convert a QKeySequence into a frozenset of normalized key strings.
        Example: "Command+Shift+R" → frozenset({'command', 'shift', 'r'})
        Example: "Meta+Shift+R" → frozenset({'command', 'shift', 'r'})
        """
        ks_str = key_sequence.toString()
        # Log the key sequence for debugging
        logger.debug(f"Parsing key sequence: {ks_str}")
        
        # Handle different formats of key sequences
        # First, ensure we only take the first key sequence if multiple are provided
        if "," in ks_str:
            ks_str = ks_str.split(",")[0].strip()
            logger.warning(f"Multiple key sequences detected, using only the first one: {ks_str}")
        
        if "+" in ks_str:
            keys = [k.strip().lower() for k in ks_str.split("+") if k.strip()]
        else:
            # Handle single key case
            keys = [ks_str.lower()]
            
        # Map Qt key names to pynput names
        key_map = {
            'meta': 'command',  # Qt uses Meta for Command on macOS
            'cmd': 'command',
            'command': 'command',
            'ctrl': 'control',
            'control': 'control',
            'alt': 'alt',
            'option': 'alt',    # macOS uses Option for Alt
            'shift': 'shift'
        }
        
        normalized_keys = []
        for k in keys:
            normalized = key_map.get(k, k)
            normalized_keys.append(normalized)
            logger.debug(f"Normalized key '{k}' to '{normalized}'")
            
        logger.debug(f"Parsed keys: {normalized_keys}")
        return frozenset(normalized_keys)

    def fix_hotkey_sequence(self, key_sequence: QKeySequence) -> QKeySequence:
        """
        Check if the key sequence needs fixing for macOS compatibility.
        This helps resolve Control vs Command confusion on macOS.
        
        Args:
            key_sequence: The QKeySequence to check and fix
            
        Returns:
            QKeySequence: Fixed key sequence if needed, or original if no fix needed
        """
        ks_str = key_sequence.toString()
        if not ks_str:
            return key_sequence
            
        logger.debug(f"Analyzing hotkey sequence: {ks_str}")
        
        # The issue is that Control and Command can get mixed up
        # This happens because pynput may interpret keys differently
        # from how Qt/PySide6 does.
        
        # Check if we need to swap Ctrl and Meta (Command)
        if "Ctrl" in ks_str and "Meta" not in ks_str:
            # This is a Control-based hotkey, but on macOS Command is more common
            logger.info(f"User has selected Control-based hotkey {ks_str} on macOS - Command is more typical")
            
        elif "Meta" in ks_str and "Ctrl" not in ks_str:
            # This is a Command-based hotkey (correct for macOS)
            logger.debug(f"Using Command-based hotkey {ks_str} - this is standard for macOS")
            
        # Debug the actual key representation
        ns = self._parse_qkeysequence(key_sequence)
        logger.debug(f"Normalized key representation: {ns}")
        
        return key_sequence
    
    def normalize_for_macos(self, key_sequence: QKeySequence) -> QKeySequence:
        """
        Create consistent representation of hotkeys on macOS.
        Specifically handles the Control vs Command confusion.
        
        Args:
            key_sequence: The QKeySequence to normalize
            
        Returns:
            QKeySequence: A normalized version for macOS
        """
        ks_str = key_sequence.toString()
        if not ks_str:
            return key_sequence
            
        # On macOS, prefer Command (Meta) over Control for most operations
        # This helps maintain consistency with macOS conventions
        if "Ctrl" in ks_str and "Meta" not in ks_str:
            # Convert Control to Command for consistency
            new_str = ks_str.replace("Ctrl", "Meta")
            logger.info(f"Converting {ks_str} to {new_str} for macOS consistency")
            return QKeySequence(new_str)
        
        return key_sequence
        
    def register_hotkey(self, key_sequence: QKeySequence) -> bool:
        if not self._validate_key_sequence(key_sequence):
            return False
            
        # Apply any fixes for macOS compatibility
        key_sequence = self.fix_hotkey_sequence(key_sequence)
        
        # Register the main hotkey only - don't automatically register both versions
        ns = self._parse_qkeysequence(key_sequence)
        self.registered_hotkeys[key_sequence] = ns
        logger.info(f"Registered hotkey: {key_sequence.toString()} with keys {ns}")
        
        # Log the state of keyboard listener and OS details
        import platform
        logger.debug(f"Platform: {platform.system()} {platform.release()}")
        logger.debug(f"Keyboard listener running: {self._listener.is_alive()}")
        
        return True

    def _on_press(self, key):
        # Skip processing if hotkeys are disabled
        if not self._hotkeys_enabled:
            logger.debug("Hotkeys disabled, ignoring key press")
            return
            
        normalized = self._normalize_key(key)
        if normalized:
            self._pressed_keys.add(normalized)            
            # Special debug for common macOS confusion keys
            if normalized in ['command', 'control']:
                logger.debug(f"Detected modifier key: {normalized}")
            
            # Check if any registered hotkey exactly matches current keys
            for ks, reg_keys in self.registered_hotkeys.items():
                # Check for exact match (not just subset)
                active_mods = {k for k in self._pressed_keys if k in ['command', 'control', 'shift', 'alt', 'option']}
                active_keys = {k for k in self._pressed_keys if k not in ['command', 'control', 'shift', 'alt', 'option']}
                reg_mods = {k for k in reg_keys if k in ['command', 'control', 'shift', 'alt', 'option']}
                reg_keys_no_mods = {k for k in reg_keys if k not in ['command', 'control', 'shift', 'alt', 'option']}
                
                # Check if the modifier keys match exactly and the regular keys match
                if reg_mods == active_mods and reg_keys_no_mods.issubset(active_keys):
                    if not self._active_hotkeys.get(ks, False):
                        # Mark as active and emit the hotkey_pressed signal.
                        self._active_hotkeys[ks] = True
                        logger.debug(f"Hotkey pressed: {ks.toString()} (exact match)")
                        
                        # Toggle recording state
                        if not self._is_key_held:
                            self._is_key_held = True
                            logger.debug("Starting recording")
                            self.hotkey_pressed.emit()
                        else:
                            # If already recording, stop it
                            self._is_key_held = False
                            logger.debug("Stopping recording")
                            self.hotkey_released.emit()
                            self.stop_hotkey_pressed.emit()  # Explicit stop signal
                        
                        # Special handling for exit hotkey.
                        if self.exit_hotkey and ks == self.exit_hotkey:
                            logger.info(f"Exit hotkey detected: {ks.toString()}")
                            self.exit_hotkey_pressed.emit()
                        
                        # Special handling for process text hotkey.
                        if self.registered_process_text_hotkey and ks == self.registered_process_text_hotkey:
                            logger.debug("Process text hotkey detected")
                            self.process_text_hotkey_pressed.emit()

    def _on_release(self, key):
        normalized = self._normalize_key(key)
        if normalized in self._pressed_keys:
            self._pressed_keys.remove(normalized)
            
        # For any hotkey that is no longer fully pressed, update its active state
        for ks, reg_keys in self.registered_hotkeys.items():
            # Use same exact match checking as in _on_press
            active_mods = {k for k in self._pressed_keys if k in ['command', 'control', 'shift', 'alt', 'option']}
            active_keys = {k for k in self._pressed_keys if k not in ['command', 'control', 'shift', 'alt', 'option']}
            reg_mods = {k for k in reg_keys if k in ['command', 'control', 'shift', 'alt', 'option']}
            reg_keys_no_mods = {k for k in reg_keys if k not in ['command', 'control', 'shift', 'alt', 'option']}
            
            # Check if the hotkey was previously active but is no longer fully pressed
            # This uses the same exact matching as in _on_press
            is_still_pressed = reg_mods == active_mods and reg_keys_no_mods.issubset(active_keys)
            if self._active_hotkeys.get(ks, False) and not is_still_pressed:
                self._active_hotkeys[ks] = False
                logger.debug(f"Hotkey released: {ks.toString()}")
                
                # We don't emit hotkey_released here to avoid duplicate stops
                # The actual stop is handled in _on_press when the hotkey is pressed again

    def unregister_hotkey(self, key_sequence: QKeySequence) -> bool:
        if key_sequence in self.registered_hotkeys:
            del self.registered_hotkeys[key_sequence]
            logger.info(f"Unregistered hotkey: {key_sequence.toString()}")
            return True
        return False

    def register_process_text_hotkey(self, key_sequence: QKeySequence) -> bool:
        if not self._validate_key_sequence(key_sequence):
            logger.warning(f"Invalid process text hotkey: {key_sequence.toString()}")
            return False
        ns = self._parse_qkeysequence(key_sequence)
        self.registered_process_text_hotkey = key_sequence
        self.registered_hotkeys[key_sequence] = ns
        logger.info(f"Registered process text hotkey: {key_sequence.toString()} with keys {ns}")
        return True

    def _validate_key_sequence(self, key_sequence: QKeySequence) -> bool:
        if not key_sequence or key_sequence.isEmpty():
            logger.warning("Empty key sequence")
            return False
        return True

    def is_key_held(self) -> bool:
        """Returns whether the hotkey is currently being held down."""
        return self._is_key_held

    def shutdown(self):
        if self._listener:
            self._listener.stop()
            logger.info("Stopped MacOS hotkey listener")

    # Add a method to enable/disable hotkeys
    def set_hotkeys_enabled(self, enabled: bool):
        """Enable or disable hotkey processing"""
        logger.info(f"{'Enabling' if enabled else 'Disabling'} hotkeys")
        self._hotkeys_enabled = enabled 
        
    def debug_hotkeys(self):
        """Log all registered hotkeys and current status for debugging"""
        logger.info(f"--- MacOS Hotkey Handler Debug Info ---")
        logger.info(f"Hotkeys enabled: {self._hotkeys_enabled}")
        logger.info(f"Currently pressed keys: {self._pressed_keys}")
        logger.info(f"Is recording active: {self._is_key_held}")
        
        logger.info(f"Registered hotkeys ({len(self.registered_hotkeys)}):")
        for ks, keys in self.registered_hotkeys.items():
            logger.info(f" - {ks.toString()} -> {keys} (active: {self._active_hotkeys.get(ks, False)})")
            
        logger.info(f"Exit hotkey: {self.exit_hotkey.toString() if self.exit_hotkey else 'None'}")
        logger.info(f"Process text hotkey: {self.registered_process_text_hotkey.toString() if self.registered_process_text_hotkey else 'None'}")
        logger.info(f"-------------------------------------") 