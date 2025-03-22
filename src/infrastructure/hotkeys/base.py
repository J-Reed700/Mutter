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
    
    def __init__(self):
        super().__init__()
        self.registered_hotkeys: Dict[QKeySequence, Any] = {}
    
    @abstractmethod
    def register_hotkey(self, key_sequence: QKeySequence) -> bool:
        pass
    
    @abstractmethod
    def unregister_hotkey(self, key_sequence: QKeySequence) -> bool:
        pass 