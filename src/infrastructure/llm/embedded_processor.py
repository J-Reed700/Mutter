import logging
from typing import Optional, List, Callable
from dataclasses import dataclass
import threading
import os
from pathlib import Path

# Import the LLMProcessingResult class from processor.py
from .processor import LLMProcessingResult

logger = logging.getLogger(__name__)

# Flag to track if PyTorch dependencies are available
TORCH_AVAILABLE = False
TRANSFORMERS_AVAILABLE = False

# Define variables at the module level to avoid UnboundLocalError
AutoTokenizer = None
AutoModelForSeq2SeqLM = None
AutoModelForCausalLM = None
pipeline = None
BitsAndBytesConfig = None
HfHubHTTPError = None

# Try to import PyTorch and transformers, but don't fail if they're not available
try:
    import torch
    TORCH_AVAILABLE = True
    try:
        from transformers import pipeline, AutoModelForSeq2SeqLM, AutoTokenizer, AutoModelForCausalLM
        # Also import HfHubHTTPError for error handling
        from transformers.utils.hub import HfHubHTTPError
        # Also import BitsAndBytesConfig for 8-bit quantization
        try:
            from transformers import BitsAndBytesConfig
        except ImportError:
            logger.warning("BitsAndBytesConfig not available. 8-bit quantization will be disabled.")
        TRANSFORMERS_AVAILABLE = True
    except ImportError:
        logger.warning("Transformers library not available. Embedded LLM functionality will be disabled.")
except ImportError:
    logger.warning("PyTorch not available. Embedded LLM functionality will be disabled.")

class EmbeddedTextProcessor:
    """Process text using lightweight models embedded directly in the application"""
    
    def __init__(self, model_name: str = "sshleifer/distilbart-xsum-12-3", progress_callback: Callable[[str, float], None] = None):
        """Initialize the embedded text processor with the specified model name
        
        Args:
            model_name: Name of the model to load
            progress_callback: Optional callback to report download progress (message, progress_percentage)
        """
        # Fix model name formats that don't include the repository
        model_name_mapping = {
            "distilbart-cnn-12-6": "facebook/distilbart-cnn-12-6",
            "bart-large-cnn": "facebook/bart-large-cnn",
            "distilbart-xsum-12-3": "sshleifer/distilbart-xsum-12-3"
        }
        
        if model_name in model_name_mapping:
            logger.info(f"Updating model name from {model_name} to {model_name_mapping[model_name]}")
            model_name = model_name_mapping[model_name]
            
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self.available = False
        self.max_length = 150
        self.min_length = 40
        self._loading_lock = threading.Lock()
        self._is_loading = False
        self._progress_callback = progress_callback
        
        # Set up a custom cache directory in the user's home folder
        # This ensures models are cached between runs and not re-downloaded each time
        model_cache_dir = self._get_model_cache_path()
        os.environ["HF_HOME"] = model_cache_dir
        os.environ["TRANSFORMERS_CACHE"] = os.path.join(model_cache_dir, "transformers")
        
        logger.info(f"Using model cache directory for LLM: {model_cache_dir}")
        
        # Check if dependencies are available
        if not TORCH_AVAILABLE or not TRANSFORMERS_AVAILABLE:
            logger.warning("Required dependencies for embedded LLM are not available.")
            self.available = False
            return
        
        # Try to load the model in a background thread to not block the UI
        self._load_model_background()
    
    def _get_model_cache_path(self) -> str:
        """Get the path for model storage"""
        # Store models in a local directory to avoid repetitive downloads
        model_dir = Path.home() / ".voicerecorder" / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        return str(model_dir)
    
    def _load_model_background(self):
        """Load the model in a background thread"""
        if self._is_loading or not TORCH_AVAILABLE or not TRANSFORMERS_AVAILABLE:
            return
            
        with self._loading_lock:
            self._is_loading = True
            
        # Call the progress callback with initial message
        if self._progress_callback:
            self._progress_callback(f"Preparing to download model: {self.model_name}", 0.0)
            
        thread = threading.Thread(target=self._load_model)
        thread.daemon = True
        thread.start()
    
    def _load_model(self):
        """Load the model from Hugging Face"""
        if not TORCH_AVAILABLE or not TRANSFORMERS_AVAILABLE:
            logger.warning("Cannot load embedded model: dependencies not available")
            self.available = False
            with self._loading_lock:
                self._is_loading = False
            return
            
        try:
            # Ensure global variables are available
            global AutoTokenizer, AutoModelForSeq2SeqLM, AutoModelForCausalLM, BitsAndBytesConfig
            
            # Check if model is already cached
            model_cache_dir = self._get_model_cache_path()
            model_id = self.model_name.split("/")[-1] if "/" in self.model_name else self.model_name
            model_dir = os.path.join(model_cache_dir, "transformers", "models--" + self.model_name.replace("/", "--"))
            
            if os.path.exists(model_dir):
                logger.info(f"Found existing LLM model at {model_dir}")
                if self._progress_callback:
                    self._progress_callback(f"Found cached model: {self.model_name}", 10.0)
            else:
                logger.info(f"LLM model not found locally, will download to {model_cache_dir}")
                if self._progress_callback:
                    self._progress_callback(f"Downloading model: {self.model_name}", 5.0)
            
            logger.info(f"Loading embedded LLM model: {self.model_name}")
            if self._progress_callback:
                self._progress_callback(f"Loading model: {self.model_name}", 15.0)
            
            # Try to use CUDA first if we requested a model that requires it
            use_cuda = torch.cuda.is_available()
            device = torch.device("cuda" if use_cuda else "cpu")
            
            if not use_cuda:
                logger.info("CUDA not available, using CPU for embedded model")
            
            # Setup a progress handler for transformers to report download progress
            if self._progress_callback:
                # We need to patch the transformers download manager to report progress
                from transformers.utils.hub import custom_hf_download_progress_bar
                from tqdm import tqdm
                
                # Clear any existing callbacks
                if hasattr(custom_hf_download_progress_bar, '_callbacks'):
                    custom_hf_download_progress_bar._callbacks = []
                    
                # Original tqdm update method
                original_update = tqdm.update
                download_size = 0

                def progress_updater(current_size, total_size):
                    """Update progress based on download size"""
                    nonlocal download_size
                    download_size = total_size
                    
                    if total_size > 0:
                        # Scale to 15-80% range (reserve beginning and end for other operations)
                        progress_percent = 15.0 + (current_size / total_size) * 65.0
                        model_name = self.model_name
                        self._progress_callback(
                            f"Downloading model files: {current_size/1024/1024:.1f}/{total_size/1024/1024:.1f} MB",
                            progress_percent
                        )
                        # Ensure regular logging for debugging
                        logger.debug(f"Download progress: {current_size/1024/1024:.1f}/{total_size/1024/1024:.1f} MB ({progress_percent:.1f}%)")

                # Set a custom callback for the progress bar
                custom_hf_download_progress_bar.set_callback(progress_updater)
                
                logger.debug(f"Registered download progress callback for model: {self.model_name}")
            
            # For summarization
            try:
                if "bart" in self.model_name.lower() or "t5" in self.model_name.lower():
                    # These models can be CPU-only if needed
                    if self._progress_callback:
                        self._progress_callback(f"Downloading tokenizer for {self.model_name}", 20.0)
                    self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                    
                    if self._progress_callback:
                        self._progress_callback(f"Downloading model weights for {self.model_name}", 30.0)
                    self.model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
                    
                    if self._progress_callback:
                        self._progress_callback(f"Loading model to {device}", 80.0)
                    self.model.to(device)
                    
                # For general text generation
                else:
                    # LLMs often need GPU
                    try:
                        if self._progress_callback:
                            self._progress_callback(f"Downloading tokenizer for {self.model_name}", 20.0)
                        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                        
                        if self._progress_callback:
                            self._progress_callback(f"Downloading model weights for {self.model_name}", 30.0)
                        self.model = AutoModelForCausalLM.from_pretrained(self.model_name)
                        
                        if self._progress_callback:
                            self._progress_callback(f"Loading model to {device}", 80.0)
                        self.model.to(device)
                    except Exception as e:
                        if "CUDA" in str(e) or "cudnn" in str(e) or "GPU" in str(e):
                            logger.warning(f"Failed to load model with GPU acceleration: {e}")
                            logger.info("Trying to load model in CPU-only mode with reduced precision")
                            
                            if self._progress_callback:
                                self._progress_callback(f"Falling back to CPU with reduced precision", 40.0)
                            
                            # If BitsAndBytesConfig isn't already imported, try to import it now
                            if BitsAndBytesConfig is None:
                                try:
                                    from transformers import BitsAndBytesConfig
                                except ImportError:
                                    logger.error("BitsAndBytesConfig not available, cannot load model in reduced precision mode")
                                    raise
                            
                            # Create quantization config if BitsAndBytesConfig is available
                            if BitsAndBytesConfig is not None:
                                quantization_config = BitsAndBytesConfig(
                                    load_in_8bit=True,
                                    llm_int8_enable_fp32_cpu_offload=True
                                )
                                
                                if self._progress_callback:
                                    self._progress_callback(f"Downloading tokenizer for {self.model_name}", 45.0)
                                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                                
                                if self._progress_callback:
                                    self._progress_callback(f"Downloading quantized model for {self.model_name}", 50.0)
                                self.model = AutoModelForCausalLM.from_pretrained(
                                    self.model_name,
                                    device_map="auto",
                                    quantization_config=quantization_config
                                )
                            else:
                                raise
                        else:
                            raise
                        
                self.available = True
                if self._progress_callback:
                    self._progress_callback(f"Model {self.model_name} loaded successfully", 100.0)
                logger.info(f"Successfully loaded embedded LLM model: {self.model_name}")
                
            except HfHubHTTPError as http_error:
                # Handle common HTTP errors like timeouts
                if "timed out" in str(http_error).lower() or "timeout" in str(http_error).lower():
                    error_msg = f"Download timed out. Please check your internet connection and try again."
                    logger.error(f"HTTP timeout error: {http_error}")
                    if self._progress_callback:
                        self._progress_callback(error_msg, -1.0)
                elif "rate limit" in str(http_error).lower():
                    error_msg = f"Rate limited by Hugging Face. Please try again later."
                    logger.error(f"Rate limit error: {http_error}")
                    if self._progress_callback:
                        self._progress_callback(error_msg, -1.0)
                else:
                    error_msg = f"Error downloading model: {http_error}"
                    logger.error(f"HTTP error downloading model: {http_error}")
                    if self._progress_callback:
                        self._progress_callback(error_msg, -1.0)
                self.available = False
                
            except Exception as e:
                logger.error(f"Failed to load embedded LLM model: {e}")
                if self._progress_callback:
                    self._progress_callback(f"Error loading model: {str(e)}", -1.0)
                self.available = False
                
        except Exception as e:
            logger.error(f"Failed to load embedded LLM model: {e}")
            if self._progress_callback:
                self._progress_callback(f"Error loading model: {str(e)}", -1.0)  # Use negative to indicate error
            self.available = False
        finally:
            with self._loading_lock:
                self._is_loading = False
    
    def get_available_models(self) -> List[str]:
        """Get list of available built-in models"""
        if not TORCH_AVAILABLE or not TRANSFORMERS_AVAILABLE:
            logger.warning("Cannot list embedded models: dependencies not available")
            return []
            
        return [
            "sshleifer/distilbart-cnn-12-6",           # Small summarization model
            "facebook/bart-large-cnn",       # Better quality but larger
            "sshleifer/distilbart-xsum-12-3", # Very small model
            "philschmid/distilbart-cnn-12-6-samsum" # Good for conversation summarization
        ]
    
    def summarize(self, text: str) -> Optional[LLMProcessingResult]:
        """Summarize the given text
        
        Args:
            text: Text to summarize
            
        Returns:
            LLMProcessingResult or None if processing failed
        """
        if not TORCH_AVAILABLE or not TRANSFORMERS_AVAILABLE:
            logger.warning("Cannot use embedded LLM: dependencies not available")
            return None
            
        if not self.available:
            if not self._is_loading:
                # Try to load the model if it's not already loading
                self._load_model_background()
            logger.error("Embedded LLM not available yet")
            return None
            
        try:
            # If text is very short, just return it as is
            if len(text.split()) < 20:
                return LLMProcessingResult(
                    original_text=text,
                    processed_text=text,
                    processing_type="summarize",
                    model_name=self.model_name
                )
                
            # Truncate very long text to avoid memory issues
            max_tokens = 1024
            words = text.split()
            if len(words) > max_tokens:
                logger.warning(f"Text too long ({len(words)} words), truncating to {max_tokens} words")
                text = " ".join(words[:max_tokens])
            
            # Set max_length based on input length (aim for ~30% compression)
            max_length = min(self.max_length, max(self.min_length, int(len(text.split()) * 0.3)))
            
            # Check if model and tokenizer are loaded
            if self.model is None or self.tokenizer is None:
                logger.warning("Model not loaded yet, trying to load now")
                self._load_model()
                if self.model is None or self.tokenizer is None:
                    logger.error("Failed to load model")
                    return None
            
            # Process the text directly using model
            global pipeline
            summary = None
            
            # Try to use the pipeline first if it's available
            if pipeline is not None:
                try:
                    summarizer = pipeline("summarization", model=self.model, tokenizer=self.tokenizer)
                    result = summarizer(text, max_length=max_length, min_length=self.min_length, do_sample=False)
                    if result and len(result) > 0:
                        summary = result[0]["summary_text"]
                except Exception as pipeline_error:
                    logger.warning(f"Pipeline summarization failed: {pipeline_error}. Falling back to direct model usage.")
            
            # If pipeline failed or is not available, use direct model interaction
            if summary is None:
                # Process directly using model
                inputs = self.tokenizer(text, return_tensors="pt", max_length=1024, truncation=True)
                
                # Move inputs to model device
                device = next(self.model.parameters()).device
                inputs = {k: v.to(device) for k, v in inputs.items()}
                
                # Generate summary
                with torch.no_grad():
                    summary_ids = self.model.generate(
                        inputs["input_ids"],
                        max_length=max_length,
                        min_length=self.min_length,
                        do_sample=False
                    )
                
                summary = self.tokenizer.decode(summary_ids[0], skip_special_tokens=True)
            
            # Create result
            if summary:
                return LLMProcessingResult(
                    original_text=text,
                    processed_text=summary,
                    processing_type="summarize",
                    model_name=self.model_name
                )
            else:
                logger.error("No result from model")
                return None
        except Exception as e:
            logger.error(f"Error processing text with embedded LLM: {e}")
            return None
    
    def process_with_prompt(self, text: str, prompt_template: str) -> Optional[LLMProcessingResult]:
        """Process text with a custom prompt template
        
        Args:
            text: Text to process
            prompt_template: Custom prompt template (use {text} as placeholder)
            
        Returns:
            LLMProcessingResult or None if processing failed
        """
        if not TORCH_AVAILABLE or not TRANSFORMERS_AVAILABLE:
            logger.warning("Cannot use embedded LLM: dependencies not available")
            return None
            
        # For the embedded model we just redirect to summarize
        # as it can't handle custom prompts as effectively
        logger.info("Custom prompts not fully supported in embedded mode, using summarization")
        return self.summarize(text)

    def process_text(self, text: str, max_length: int = 150, min_length: int = 40) -> str:
        """Process text using the embedded model."""
        if not TORCH_AVAILABLE or not TRANSFORMERS_AVAILABLE:
            logger.warning("Cannot use embedded LLM: dependencies not available")
            return text
            
        try:
            # Load model if not loaded
            if self.model is None or self.tokenizer is None:
                self._load_model()
                
            # Use model type to determine processing approach
            if "bart" in self.model_name.lower() or "t5" in self.model_name.lower():
                # For summarization models (BART, T5)
                inputs = self.tokenizer(text, return_tensors="pt", max_length=1024, truncation=True)
                
                # Move inputs to the same device as the model
                device = next(self.model.parameters()).device
                inputs = {k: v.to(device) for k, v in inputs.items()}
                
                with torch.no_grad():
                    summary_ids = self.model.generate(
                        inputs["input_ids"],
                        max_length=max_length,
                        min_length=min_length,
                        early_stopping=True
                    )
                
                summary = self.tokenizer.decode(summary_ids[0], skip_special_tokens=True)
                return summary
            else:
                # For generative models (GPT, etc.)
                prompt = f"Summarize the following text:\n\n{text}\n\nSummary:"
                inputs = self.tokenizer(prompt, return_tensors="pt")
                
                # Move inputs to the same device as the model
                device = next(self.model.parameters()).device
                inputs = {k: v.to(device) for k, v in inputs.items()}
                
                import torch
                with torch.no_grad():
                    output = self.model.generate(
                        inputs["input_ids"],
                        max_length=max_length + len(inputs["input_ids"][0]),
                        temperature=0.7,
                        do_sample=True,
                        top_p=0.9
                    )
                
                generated_text = self.tokenizer.decode(output[0], skip_special_tokens=True)
                summary = generated_text[len(prompt):]
                return summary.strip()
                
        except Exception as e:
            logger.error(f"Error processing text with embedded model: {e}")
            return f"Error processing text: {e}" 