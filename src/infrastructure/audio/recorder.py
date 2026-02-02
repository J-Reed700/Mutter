from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np
import sounddevice as sd
from typing import Optional, Callable, List
from pathlib import Path
import wave
from datetime import datetime
import threading
import logging
import time
import weakref

logger = logging.getLogger(__name__)

@dataclass
class AudioRecording:
    """Represents a completed audio recording"""
    data: np.ndarray
    sample_rate: int
    timestamp: datetime
    path: Optional[Path] = None

class AudioRecorder:
    # Maximum recording duration in seconds (prevent runaway memory usage)
    MAX_RECORDING_DURATION = 600  # 10 minutes
    
    # Maximum audio data size in bytes (approximately)
    MAX_AUDIO_DATA_SIZE = 100 * 1024 * 1024  # 100 MB
    
    def __init__(self, sample_rate=16000, channels=1, device=None):
        """Initialize the audio recorder.
        
        Args:
            sample_rate: The sample rate for recording
            channels: Number of audio channels (1=mono, 2=stereo)
            device: The audio input device to use
        """
        logger.info(f"Initializing AudioRecorder: sample_rate={sample_rate}, channels={channels}, device={device}")
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device
        self.recording = False
        self._lock = threading.RLock()  # Use RLock for reentrant locking
        self._audio_data: List[np.ndarray] = []
        self._audio_data_size = 0  # Track approximate size
        self._record_thread = None
        self._stream: Optional[sd.InputStream] = None
        self._recording_start_time: Optional[float] = None
        self._device_error_count = 0
        self._max_device_errors = 5
        
        # Make sure recordings directory exists
        self.recordings_dir = Path("recordings")
        self.recordings_dir.mkdir(exist_ok=True)
        
        # Debug: List available audio devices
        self._log_available_devices()
    
    def _log_available_devices(self):
        """Log available audio devices for debugging."""
        try:
            devices = sd.query_devices()
            logger.debug(f"Available audio devices:")
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    logger.debug(f"  {i}: {dev['name']} (inputs: {dev['max_input_channels']})")
            
            # Get actual device that will be used
            if self.device is None or self.device == 'default':
                default_device = sd.default.device[0]
                if isinstance(default_device, int):
                    device_info = sd.query_devices(default_device)
                    logger.debug(f"Using default input device: {device_info['name']}")
                else:
                    logger.debug(f"Using system default input device")
            else:
                logger.debug(f"Using specified input device: {self.device}")
        except Exception as e:
            logger.error(f"Error querying audio devices: {e}")
    
    def _resolve_device_id(self, device_name):
        """Resolve device name to a device ID to handle multiple devices with same name"""
        if device_name is None or device_name == 'default':
            return None  # Use system default
            
        try:
            devices = sd.query_devices()
            # Look for all devices with this name
            matching_devices = []
            for i, dev in enumerate(devices):
                if dev['name'] == device_name and dev['max_input_channels'] > 0:
                    matching_devices.append(i)
                    
            if not matching_devices:
                logger.warning(f"No device found with name '{device_name}', using default")
                return None
            elif len(matching_devices) == 1:
                logger.debug(f"Found a single device matching '{device_name}': ID {matching_devices[0]}")
                device_id = matching_devices[0]
                self._validate_device_settings(device_id)
                return device_id
            else:
                # Multiple devices with same name - prefer WASAPI on Windows (usually better quality)
                wasapi_device = None
                for dev_id in matching_devices:
                    dev_info = devices[dev_id]
                    host_api = dev_info.get('hostapi', 0)
                    host_name = sd.query_hostapis(host_api).get('name', '').lower()
                    if "wasapi" in host_name:
                        logger.debug(f"Multiple devices matched '{device_name}', selecting WASAPI device: ID {dev_id}")
                        wasapi_device = dev_id
                        break
                
                # If found a WASAPI device, use it
                if wasapi_device is not None:
                    self._validate_device_settings(wasapi_device)
                    return wasapi_device
                
                # If no WASAPI found, just use the first one
                logger.debug(f"Multiple devices matched '{device_name}', using first one: ID {matching_devices[0]}")
                self._validate_device_settings(matching_devices[0])
                return matching_devices[0]
        except Exception as e:
            logger.error(f"Error resolving device ID: {e}")
            return None
    
    def _validate_device_settings(self, device_id):
        """Check if current sample rate is supported by the device and adjust if needed"""
        try:
            if device_id is None:
                return
                
            device_info = sd.query_devices(device_id)
            device_sample_rate = int(device_info.get('default_samplerate', 44100))
            
            # If current sample rate doesn't match device's default sample rate
            if self.sample_rate != device_sample_rate:
                logger.warning(f"Device '{device_info['name']}' prefers sample rate {device_sample_rate}Hz, " 
                              f"but configured for {self.sample_rate}Hz")
                
                # Try to query supported sample rates if available
                supported_rates = []
                try:
                    # Check if this device explicitly lists supported rates
                    if hasattr(device_info, 'supported_samplerates'):
                        supported_rates = device_info['supported_samplerates']
                    
                    # If no explicit list, try some common sample rates
                    # Attempt an educated guess based on the default sample rate
                    if not supported_rates:
                        if device_sample_rate == 48000:
                            supported_rates = [48000, 96000, 24000]
                        elif device_sample_rate == 44100:
                            supported_rates = [44100, 88200, 22050]
                        else:
                            supported_rates = [device_sample_rate]
                except Exception as e:
                    logger.debug(f"Error querying supported sample rates: {e}")
                    supported_rates = [device_sample_rate]  # Default to device's default rate
                
                # Set sample rate to device's default
                logger.info(f"Automatically adjusting sample rate to {device_sample_rate}Hz for device '{device_info['name']}'")
                self.sample_rate = device_sample_rate
                
                # Log supported rates
                logger.debug(f"Device likely supports these sample rates: {supported_rates}")
        except Exception as e:
            logger.error(f"Error validating device settings: {e}")
    
    def _check_device_available(self, device_id) -> bool:
        """Check if the specified audio device is still available."""
        try:
            if device_id is None:
                # Check if default device is available
                default_device = sd.default.device[0]
                if default_device is None:
                    return False
                sd.query_devices(default_device)
            else:
                sd.query_devices(device_id)
            return True
        except Exception as e:
            logger.warning(f"Device check failed: {e}")
            return False
    
    def update_settings(self, sample_rate=None, channels=None, device=None):
        """Update recorder settings.
        
        Args:
            sample_rate: New sample rate for recording
            channels: New number of audio channels
            device: New audio input device to use
            
        Returns:
            bool: True if settings were updated successfully
        """
        logger.debug(f"Updating audio recorder settings: sample_rate={sample_rate}, channels={channels}, device={device}")
        
        with self._lock:
            # Only update settings if not currently recording
            if self.recording:
                logger.warning("Cannot update settings while recording is in progress")
                return False
                
            # Update settings if provided
            if sample_rate is not None:
                self.sample_rate = sample_rate
                
            if channels is not None:
                self.channels = channels
                
            if device is not None:
                self.device = device
                
            return True
    
    def _cleanup_audio_data(self):
        """Clean up audio data to free memory."""
        with self._lock:
            self._audio_data.clear()
            self._audio_data_size = 0
    
    def start_recording(self):
        """Start recording audio in a separate thread."""
        with self._lock:
            if self.recording:
                logger.debug("Recording already in progress")
                return
                
            self.recording = True
            self._cleanup_audio_data()  # Clear any previous data
            self._recording_start_time = time.time()
            self._device_error_count = 0
            
            def record_audio():
                actual_device = None
                try:
                    # Resolve device name to device ID to handle multiple devices with same name
                    actual_device = self._resolve_device_id(self.device)
                    
                    logger.debug(f"Starting recording thread with device={self.device} (using actual_device={actual_device}), "
                                f"sample_rate={self.sample_rate}, channels={self.channels}")
                    
                    # Additional debug info for device that will be used
                    self._log_device_info(actual_device)
                    
                    # Start the recording stream
                    self._stream = sd.InputStream(
                        samplerate=self.sample_rate,
                        channels=self.channels,
                        device=actual_device,
                        callback=self._audio_callback
                    )
                    
                    with self._stream:
                        logger.info("Started recording")
                        
                        # Stay in this loop until recording is set to False
                        while self.recording:
                            # Check for maximum recording duration
                            if self._recording_start_time:
                                elapsed = time.time() - self._recording_start_time
                                if elapsed > self.MAX_RECORDING_DURATION:
                                    logger.warning(f"Maximum recording duration ({self.MAX_RECORDING_DURATION}s) reached, stopping")
                                    self.recording = False
                                    break
                            
                            # Check for maximum data size
                            if self._audio_data_size > self.MAX_AUDIO_DATA_SIZE:
                                logger.warning(f"Maximum audio data size reached, stopping")
                                self.recording = False
                                break
                            
                            # Check if device is still available
                            if self._device_error_count >= self._max_device_errors:
                                logger.error("Too many device errors, stopping recording")
                                self.recording = False
                                break
                            
                            time.sleep(0.1)
                            
                except sd.PortAudioError as e:
                    logger.error(f"PortAudio error during recording: {e}")
                    self._handle_device_error(e)
                except OSError as e:
                    if e.errno == 19:  # ENODEV - No such device
                        logger.error(f"Audio device disconnected: {e}")
                    else:
                        logger.error(f"OS error during recording: {e}")
                    self._handle_device_error(e)
                except Exception as e:
                    logger.error(f"Error during recording: {e}", exc_info=True)
                finally:
                    self.recording = False
                    self._stream = None
                    logger.debug("Recording thread finished")
            
            # Start recording in a separate thread
            self._record_thread = threading.Thread(
                target=record_audio, 
                daemon=True,
                name="AudioRecorder"
            )
            self._record_thread.start()
    
    def _log_device_info(self, actual_device):
        """Log information about the audio device being used."""
        try:
            if actual_device is None:
                default_device_idx = sd.default.device[0]
                if default_device_idx is not None:
                    device_info = sd.query_devices(default_device_idx)
                    logger.debug(f"Recording with default device: {device_info['name']}")
                    logger.debug(f"Device details: {device_info}")
                    
                    # Validate sample rate for default device
                    if self.sample_rate != int(device_info.get('default_samplerate', 44100)):
                        logger.warning(f"Default device prefers sample rate {device_info.get('default_samplerate')}Hz, "
                                     f"but configured for {self.sample_rate}Hz. This may cause issues.")
            else:
                device_info = sd.query_devices(actual_device)
                logger.debug(f"Recording with device: {device_info['name']}")
                logger.debug(f"Device details: {device_info}")
        except Exception as e:
            logger.error(f"Error getting device info: {e}")
    
    def _handle_device_error(self, error):
        """Handle audio device errors gracefully."""
        self._device_error_count += 1
        logger.warning(f"Device error #{self._device_error_count}: {error}")
        
        if self._device_error_count >= self._max_device_errors:
            logger.error("Maximum device errors reached, audio recording will stop")
            self.recording = False
    
    def stop_recording(self) -> Optional[Path]:
        """Stop the recording and save the audio to a file.
        
        Returns:
            Path to the saved audio file or None if failed
        """
        with self._lock:
            if not self.recording:
                logger.debug("No recording in progress")
                return None
                
            self.recording = False
            self._recording_start_time = None
            
            # Wait for recording thread to finish
            if self._record_thread:
                self._record_thread.join(timeout=3.0)
                if self._record_thread.is_alive():
                    logger.warning("Recording thread did not terminate in time")
                self._record_thread = None
            
            # Close the stream if it's still open
            if self._stream:
                try:
                    self._stream.close()
                except Exception as e:
                    logger.debug(f"Error closing stream: {e}")
                self._stream = None
            
            # Check if we have any audio data
            if not self._audio_data or len(self._audio_data) == 0:
                logger.warning("No audio data recorded")
                self._cleanup_audio_data()
                return None
            
            try:
                # Concatenate all audio chunks
                audio_data = np.concatenate(self._audio_data, axis=0)
                
                # Debug information about the recorded audio
                duration = len(audio_data) / self.sample_rate
                logger.debug(f"Recorded audio: {len(audio_data)} samples, {duration:.2f} seconds")
                
                # Check if audio has actual content (not just silence)
                audio_min = np.min(audio_data)
                audio_max = np.max(audio_data)
                audio_mean = np.mean(np.abs(audio_data))
                logger.debug(f"Audio levels - min: {audio_min:.6f}, max: {audio_max:.6f}, mean: {audio_mean:.6f}")
                
                if audio_mean < 0.001:
                    logger.warning("Audio recording appears to be very quiet or silent")
                
                # Create a filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = self.recordings_dir / f"recording_{timestamp}.wav"
                
                # Save as WAV file
                with wave.open(str(filename), 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(2)  # 16-bit audio
                    wf.setframerate(self.sample_rate)
                    # Convert float to int16
                    audio_data_int = (audio_data * 32767).astype(np.int16)
                    wf.writeframes(audio_data_int.tobytes())
                
                logger.info(f"Saved recording to {filename}")
                
                # Clean up audio data after saving
                self._cleanup_audio_data()
                
                return filename
                
            except Exception as e:
                logger.error(f"Error saving audio file: {e}", exc_info=True)
                self._cleanup_audio_data()
                return None
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback function for the InputStream."""
        try:
            if status:
                logger.warning(f"Audio callback status: {status}")
                # Track device errors
                if 'input overflow' in str(status).lower() or 'underflow' in str(status).lower():
                    self._device_error_count += 1
            
            # Don't append if we're not recording
            if not self.recording:
                return
            
            # Append the audio data
            data_copy = indata.copy()
            with self._lock:
                self._audio_data.append(data_copy)
                self._audio_data_size += data_copy.nbytes
            
            # Periodically log audio levels for debugging
            if len(self._audio_data) % 10 == 0:  # Log every ~1 second
                audio_min = np.min(data_copy)
                audio_max = np.max(data_copy)
                audio_mean = np.mean(np.abs(data_copy))
                logger.debug(f"Current audio frame - min: {audio_min:.6f}, max: {audio_max:.6f}, mean: {audio_mean:.6f}")
                
        except Exception as e:
            logger.error(f"Error in audio callback: {e}")
    
    def get_last_recording_duration(self) -> float:
        """Get the duration of the last recording in seconds.
        
        Returns:
            float: Duration in seconds or 0 if no recording available
        """
        try:
            with self._lock:
                if not self._audio_data:
                    return 0
                    
                # Calculate duration from total samples / sample rate
                total_samples = sum(chunk.shape[0] for chunk in self._audio_data)
                return total_samples / self.sample_rate
        except Exception as e:
            logger.error(f"Error calculating recording duration: {e}")
            return 0
    
    def get_last_recording_info(self) -> dict:
        """Get information about the last recording.
        
        Returns:
            dict: Recording information or empty dict if no recording available
        """
        try:
            with self._lock:
                if not self._audio_data:
                    return {}
                    
                # Calculate some basic audio statistics
                audio_data = np.concatenate(self._audio_data, axis=0)
                return {
                    "duration_seconds": len(audio_data) / self.sample_rate,
                    "sample_rate": self.sample_rate,
                    "channels": self.channels,
                    "samples": len(audio_data),
                    "min_amplitude": float(np.min(audio_data)),
                    "max_amplitude": float(np.max(audio_data)),
                    "mean_amplitude": float(np.mean(np.abs(audio_data))),
                    "is_silent": float(np.mean(np.abs(audio_data))) < 0.001
                }
        except Exception as e:
            logger.error(f"Error getting recording info: {e}")
            return {}
    
    def cleanup(self):
        """Clean up all resources held by the recorder."""
        logger.debug("Cleaning up audio recorder")
        
        # Stop any ongoing recording
        if self.recording:
            self.recording = False
            if self._record_thread:
                self._record_thread.join(timeout=2.0)
        
        # Close the stream
        if self._stream:
            try:
                self._stream.close()
            except Exception as e:
                logger.debug(f"Error closing stream during cleanup: {e}")
            self._stream = None
        
        # Clear audio data
        self._cleanup_audio_data()
        
        logger.debug("Audio recorder cleanup complete")
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.cleanup()
        except Exception:
            pass
