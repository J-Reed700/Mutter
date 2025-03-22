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

logger = logging.getLogger(__name__)

@dataclass
class AudioRecording:
    """Represents a completed audio recording"""
    data: np.ndarray
    sample_rate: int
    timestamp: datetime
    path: Optional[Path] = None

class AudioRecorder:
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
        self._lock = threading.Lock()
        self._audio_data = []
        self._record_thread = None
        
        # Make sure recordings directory exists
        self.recordings_dir = Path("recordings")
        self.recordings_dir.mkdir(exist_ok=True)
        
        # Debug: List available audio devices
        try:
            devices = sd.query_devices()
            logger.debug(f"Available audio devices:")
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    logger.debug(f"  {i}: {dev['name']} (inputs: {dev['max_input_channels']})")
            
            # Get actual device that will be used
            if device is None or device == 'default':
                default_device = sd.default.device[0]
                if isinstance(default_device, int):
                    device_info = sd.query_devices(default_device)
                    logger.debug(f"Using default input device: {device_info['name']}")
                else:
                    logger.debug(f"Using system default input device")
            else:
                logger.debug(f"Using specified input device: {device}")
        except Exception as e:
            logger.error(f"Error querying audio devices: {e}")
    
    def start_recording(self):
        """Start recording audio in a separate thread."""
        with self._lock:
            if self.recording:
                return
                
            self.recording = True
            self._audio_data = []
            
            def record_audio():
                try:
                    # Convert 'default' to None for sounddevice
                    actual_device = None if self.device == 'default' else self.device
                    
                    logger.debug(f"Starting recording thread with device={self.device} (using actual_device={actual_device}), "
                                f"sample_rate={self.sample_rate}, channels={self.channels}")
                    
                    # Additional debug info for device that will be used
                    try:
                        default_device_idx = sd.default.device[0]
                        if actual_device is None and default_device_idx is not None:
                            device_info = sd.query_devices(default_device_idx)
                            logger.debug(f"Recording with default device: {device_info['name']}")
                            logger.debug(f"Device details: {device_info}")
                        elif actual_device is not None:
                            device_info = sd.query_devices(actual_device)
                            logger.debug(f"Recording with device: {device_info['name']}")
                            logger.debug(f"Device details: {device_info}")
                    except Exception as e:
                        logger.error(f"Error getting device info: {e}")
                    
                    # Start the recording stream
                    with sd.InputStream(samplerate=self.sample_rate,
                                       channels=self.channels,
                                       device=actual_device,
                                       callback=self._audio_callback):
                        logger.info("Started recording")
                        
                        # Stay in this loop until recording is set to False
                        while self.recording:
                            time.sleep(0.1)
                            
                except Exception as e:
                    logger.error(f"Error during recording: {e}", exc_info=True)
                    self.recording = False
            
            # Start recording in a separate thread
            self._record_thread = threading.Thread(target=record_audio, daemon=True)
            self._record_thread.start()
    
    def stop_recording(self) -> Optional[Path]:
        """Stop the recording and save the audio to a file.
        
        Returns:
            Path to the saved audio file or None if failed
        """
        with self._lock:
            if not self.recording:
                return None
                
            self.recording = False
            
            # Wait for recording thread to finish
            if self._record_thread:
                self._record_thread.join(timeout=2.0)
                self._record_thread = None
            
            # Check if we have any audio data
            if not self._audio_data or len(self._audio_data) == 0:
                logger.warning("No audio data recorded")
                return None
            
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
            
            try:
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
                return filename
                
            except Exception as e:
                logger.error(f"Error saving audio file: {e}", exc_info=True)
                return None
    
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback function for the InputStream."""
        if status:
            logger.warning(f"Audio callback status: {status}")
        
        # Append the audio data
        self._audio_data.append(indata.copy())
        
        # Periodically log audio levels for debugging
        if len(self._audio_data) % 10 == 0:  # Log every ~1 second
            latest_audio = indata.copy()
            audio_min = np.min(latest_audio)
            audio_max = np.max(latest_audio)
            audio_mean = np.mean(np.abs(latest_audio))
            logger.debug(f"Current audio frame - min: {audio_min:.6f}, max: {audio_max:.6f}, mean: {audio_mean:.6f}") 