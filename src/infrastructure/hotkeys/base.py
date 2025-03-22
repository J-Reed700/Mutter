from abc import ABC, ABCMeta, abstractmethod
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence
from typing import Dict, Any

# Create a custom metaclass that inherits from both ABCMeta and type(QObject)
class QObjectABCMeta(type(QObject), ABCMeta):
    pass

# Use the custom metaclass for our abstract class
class HotkeyHandler(QObject, metaclass=QObjectABCMeta):
    hotkey_pressed = Signal()
    hotkey_released = Signal()
    process_text_hotkey_pressed = Signal()  # New signal for processing text
    
    def __init__(self):
        super().__init__()
        self.registered_hotkeys: Dict[QKeySequence, Any] = {}
        self.registered_process_text_hotkey: QKeySequence = None
    
    @abstractmethod
    def register_hotkey(self, key_sequence: QKeySequence) -> bool:
        pass
    
    @abstractmethod
    def unregister_hotkey(self, key_sequence: QKeySequence) -> bool:
        pass
    
    @abstractmethod
    def register_process_text_hotkey(self, key_sequence: QKeySequence) -> bool:
        """Register a hotkey for text processing
        
        Args:
            key_sequence: The key sequence to register
            
        Returns:
            bool: True if registration succeeded, False otherwise
        """
        pass 