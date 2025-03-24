import logging
from typing import Dict, Callable, Optional
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

class DownloadManager(QObject):
    """
    Global manager for tracking and handling model downloads.
    
    This class allows multiple components to register progress callbacks
    and provides a central place to track all downloads.
    """
    
    # Signal when download progress is updated
    download_progress_updated = Signal(str, str, float)  # model_name, message, progress
    
    def __init__(self):
        super().__init__()
        self._downloads: Dict[str, Dict] = {}
        
    def register_progress_callback(self, window):
        """Register a window to receive progress updates
        
        Args:
            window: Window with update_download_progress method to receive updates
        """
        self.download_progress_updated.connect(window.update_download_progress)
        
    def unregister_progress_callback(self, window):
        """Unregister a window from receiving progress updates
        
        Args:
            window: Window to unregister
        """
        try:
            self.download_progress_updated.disconnect(window.update_download_progress)
        except (TypeError, RuntimeError):
            # Already disconnected
            pass
            
    def get_progress_callback(self) -> Callable[[str, float], None]:
        """Get progress callback for a model download
        
        Returns:
            Callable that can be passed to EmbeddedTextProcessor for progress tracking
        """
        def progress_callback(message: str, progress: float):
            # Extract model name from message if possible
            model_name = "Unknown Model"
            
            # Try to extract model name from common message patterns
            if "model:" in message.lower():
                parts = message.split("model:", 1)
                if len(parts) > 1:
                    model_parts = parts[1].strip().split()
                    if model_parts:
                        model_name = model_parts[0].strip()
            elif "downloading" in message.lower() and ":" in message:
                parts = message.split(":", 1)
                if len(parts) > 1:
                    model_parts = parts[1].strip().split()
                    if model_parts:
                        model_name = model_parts[0].strip()
            elif "model files:" in message.lower():
                # It's a generic download progress message, try to extract model name from any previous download
                if self._downloads and len(self._downloads) > 0:
                    # Use the most recently updated download as the most likely current one
                    model_name = next(iter(self._downloads.keys()))
            
            # Clean up the model name if it has extra characters
            if "/" in model_name:
                model_name = model_name.split("/")[-1]
            
            # Track this download
            self._update_download(model_name, message, progress)
            
            # Emit signal for any registered windows
            logger.debug(f"Emitting download progress update for {model_name}: {progress:.1f}% - {message}")
            self.download_progress_updated.emit(model_name, message, progress)
        
        return progress_callback
    
    def get_progress_callback_for_model(self, model_name: str) -> Callable[[str, float], None]:
        """Get progress callback for a specific model download
        
        Args:
            model_name: Name of the model being downloaded
            
        Returns:
            Callable that can be passed to EmbeddedTextProcessor for progress tracking
        """
        def progress_callback(message: str, progress: float):
            # Track this download
            self._update_download(model_name, message, progress)
            
            # Emit signal for any registered windows
            self.download_progress_updated.emit(model_name, message, progress)
        
        return progress_callback
    
    def _update_download(self, model_name: str, message: str, progress: float):
        """Update the internal tracking of a download
        
        Args:
            model_name: Name of the model being downloaded
            message: Status message
            progress: Progress percentage (0-100) or negative for error
        """
        # Update our internal tracking
        if model_name not in self._downloads:
            self._downloads[model_name] = {"message": message, "progress": progress}
        else:
            self._downloads[model_name]["message"] = message
            self._downloads[model_name]["progress"] = progress
            
        # Log progress
        if progress < 0:
            logger.error(f"Download error for {model_name}: {message}")
        elif progress >= 100:
            logger.info(f"Download complete for {model_name}")
        else:
            logger.debug(f"Download progress for {model_name}: {progress:.1f}% - {message}")
    
    def get_downloads(self) -> Dict[str, Dict]:
        """Get all current downloads
        
        Returns:
            Dictionary of model_name -> download information
        """
        return self._downloads.copy() 