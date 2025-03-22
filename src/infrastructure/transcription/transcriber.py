from typing import Optional
from pathlib import Path
from faster_whisper import WhisperModel
import logging
from dataclasses import dataclass
import time
import requests
import os

logger = logging.getLogger(__name__)

@dataclass
class TranscriptionResult:
    text: str
    language: str
    segments: list
    duration: float

class Transcriber:
    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8", max_retries: int = 3):
        """Initialize the transcriber with the specified model.
        
        Args:
            model_size: Size of the model ('tiny', 'base', 'small', 'medium', 'large')
            device: Device to use ('cpu' or 'cuda')
            compute_type: Compute type for optimization ('int8', 'float16', 'float32')
            max_retries: Number of times to retry downloading the model
        """
        logger.info(f"Initializing Whisper model '{model_size}' on {device} with {compute_type}")
        
        # Set environment variable to use the Hugging Face cache
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        
        # Try to load the specified model with retries
        for attempt in range(max_retries):
            try:
                self.model = WhisperModel(model_size, device=device, compute_type=compute_type, download_root=self._get_model_path())
                logger.info(f"Successfully loaded model: {model_size}")
                return
            except requests.exceptions.ChunkedEncodingError as e:
                logger.warning(f"Network error on attempt {attempt+1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"Failed to download model '{model_size}' after {max_retries} attempts. Trying 'tiny' model.")
            except Exception as e:
                logger.error(f"Error loading model: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    logger.warning(f"Failed to load model '{model_size}'. Falling back to 'tiny' model.")
        
        # Fallback to tiny model if all retries failed
        try:
            logger.info("Attempting to load fallback 'tiny' model")
            self.model = WhisperModel("tiny", device=device, compute_type=compute_type, download_root=self._get_model_path())
            logger.info("Successfully loaded fallback 'tiny' model")
        except Exception as e:
            logger.critical(f"Fatal error: Could not load even the tiny model: {e}")
            raise RuntimeError(f"Failed to initialize transcription model: {e}")
    
    def _get_model_path(self) -> str:
        """Get the path for model storage"""
        # Store models in a local directory to avoid repetitive downloads
        model_dir = Path.home() / ".voicerecorder" / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        return str(model_dir)
    
    def transcribe(self, audio_path: Path, language: Optional[str] = None) -> Optional[TranscriptionResult]:
        """Transcribe an audio file.
        
        Args:
            audio_path: Path to the audio file
            language: Optional language code (e.g., 'en', 'es')
            
        Returns:
            TranscriptionResult or None if transcription failed
        """
        try:
            logger.info(f"Transcribing audio file: {audio_path}")
            
            # Debug: Check if file exists and its size
            if not audio_path.exists():
                logger.error(f"Audio file does not exist: {audio_path}")
                return None
                
            file_size = audio_path.stat().st_size
            logger.debug(f"Audio file size: {file_size} bytes ({file_size/1024:.2f} KB)")
            
            if file_size == 0:
                logger.error("Audio file is empty (0 bytes)")
                return None
                
            # Run the transcription
            logger.debug(f"Starting Whisper transcription with language={language or 'auto-detect'}")
            segments, info = self.model.transcribe(
                str(audio_path),
                language=language,
                beam_size=5,
                vad_filter=True,  # Enable Voice Activity Detection
                vad_parameters={"min_silence_duration_ms": 500}  # Adjust VAD parameters
            )
            
            # Collect all segments
            text_segments = []
            full_text = []
            
            # Count segments while processing
            segment_count = 0
            
            for segment in segments:
                segment_count += 1
                text_segments.append({
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text.strip()
                })
                full_text.append(segment.text.strip())
                logger.debug(f"Segment {segment_count}: '{segment.text.strip()}' ({segment.end - segment.start:.2f}s)")
            
            # Check if we got any segments
            if segment_count == 0:
                logger.warning("No segments detected in the audio - possible silence or unrecognized speech")
                
            # Log raw segment data for debugging
            logger.debug(f"Raw segments (count={len(full_text)}): {full_text}")
            
            # Additional debug info about detected language and confidence
            logger.debug(f"Detected language: {info.language}, language probability: {info.language_probability:.4f}")
            logger.debug(f"Transcription duration: {info.duration:.2f}s")
            
            # Join text with spaces
            joined_text = ' '.join(full_text)
            
            # Check if text is too short and likely incorrect
            if len(joined_text) < 5 and len(full_text) > 0:
                logger.warning(f"Unusually short transcription: '{joined_text}'. Possibly an error. Raw segments: {full_text}")
                # Try an alternative joining method in case spaces are being trimmed
                joined_text = ' '.join([s for s in full_text if s])
                
            result = TranscriptionResult(
                text=joined_text,
                language=info.language,
                segments=text_segments,
                duration=info.duration
            )
            
            logger.info(f"Transcription complete: {len(result.text)} chars, {len(result.segments)} segments")
            return result
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            return None 