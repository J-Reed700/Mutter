from typing import Optional
from pathlib import Path
from faster_whisper import WhisperModel
import logging
from dataclasses import dataclass
import time
import requests
import os
import torch

logger = logging.getLogger(__name__)

@dataclass
class TranscriptionResult:
    text: str
    language: str
    segments: list
    duration: float

class Transcriber:
    """Handles transcription of audio files using Whisper"""
    
    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        """Initialize the transcriber
        
        Args:
            model_size: Size of the model to use ("tiny", "base", "small", "medium", "large")
            device: Device to use for computation ("cpu" or "cuda")
            compute_type: Compute type for inference ("int8", "fp16", "fp32")
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None
        
        # Set up a custom cache directory in the user's home folder
        # This helps with model reuse between application runs
        model_cache_dir = self._get_model_path()
        os.environ["HF_HOME"] = model_cache_dir
        os.environ["TRANSFORMERS_CACHE"] = os.path.join(model_cache_dir, "transformers")
        
        logger.info(f"Using model cache directory: {model_cache_dir}")
        
        try:
            logger.info(f"Initializing Whisper model '{model_size}' on {device} with {compute_type}")
            
            # If device is set to cuda but CUDA is not available, fall back to CPU
            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA requested but not available, falling back to CPU")
                self.device = "cpu"
                device = "cpu"
            
            # Check if the model is already downloaded
            model_loaded = False
            model_dir = os.path.join(model_cache_dir, "models--openai--whisper-" + model_size)
            if os.path.exists(model_dir):
                logger.info(f"Found existing model at {model_dir}")
            else:
                logger.info(f"Model not found locally, will download to {model_cache_dir}")
            
            # Initialize the model with the cache directory
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type, download_root=model_cache_dir)
            logger.info(f"Successfully loaded model: {model_size}")
        except Exception as e:
            logger.error(f"Failed to initialize Whisper model: {e}")
            # If initialization failed with CUDA, try to fall back to CPU
            if device == "cuda":
                logger.info("Attempting to initialize model on CPU instead")
                try:
                    self.device = "cpu"
                    self.model = WhisperModel(model_size, device="cpu", compute_type=compute_type, download_root=model_cache_dir)
                    logger.info(f"Successfully loaded model: {model_size} on CPU")
                except Exception as fallback_e:
                    logger.error(f"Failed to initialize Whisper model on CPU: {fallback_e}")
                    raise
            else:
                raise
    
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
            
            # Convert full language names to language codes
            language_map = {
                "english": "en",
                "spanish": "es",
                "french": "fr",
                "german": "de",
                "chinese": "zh",
                "japanese": "ja",
                "korean": "ko",
                "russian": "ru",
                "italian": "it",
                "portuguese": "pt",
                "dutch": "nl",
                "arabic": "ar",
                "hindi": "hi",
                "auto": None
            }
            
            # Normalize language to lowercase or None
            norm_language = language.lower() if language else None
            
            # Convert full language name to code if needed
            if norm_language in language_map:
                language = language_map[norm_language]
                
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