from pathlib import Path
import logging
from typing import Optional, Dict, List, Any
import requests
import json
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class LLMProcessingResult:
    """Result from LLM processing"""
    original_text: str
    processed_text: str
    processing_type: str
    model_name: str
    
class TextProcessor:
    """Handles processing text through local LLM models"""
    
    def __init__(self, api_url: str = "http://localhost:8080/v1"):
        """Initialize the text processor
        
        Args:
            api_url: URL of the local LLM API server
        """
        self.api_url = api_url
        self.available = self._check_availability()
        if self.available:
            logger.info(f"LLM processor initialized with API at {api_url}")
        else:
            logger.warning(f"LLM API not available at {api_url}")
    
    def _check_availability(self) -> bool:
        """Check if the LLM API is available"""
        try:
            response = requests.get(f"{self.api_url}/models", timeout=2)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error checking LLM API availability: {e}")
            return False
    
    def get_available_models(self) -> List[str]:
        """Get list of available LLM models"""
        if not self.available:
            return []
            
        try:
            response = requests.get(f"{self.api_url}/models", timeout=5)
            if response.status_code == 200:
                models = response.json().get("data", [])
                return [model.get("id") for model in models]
            return []
        except Exception as e:
            logger.error(f"Error getting available models: {e}")
            return []
    
    def summarize(self, text: str, model: str = "llama3") -> Optional[LLMProcessingResult]:
        """Summarize the given text
        
        Args:
            text: Text to summarize
            model: Model to use for summarization
            
        Returns:
            LLMProcessingResult or None if processing failed
        """
        prompt = f"Please summarize the following text concisely: {text}"
        return self._process_text(text, prompt, "summarize", model)
    
    def process_with_prompt(self, text: str, prompt_template: str, model: str = "llama3") -> Optional[LLMProcessingResult]:
        """Process text with a custom prompt template
        
        Args:
            text: Text to process
            prompt_template: Custom prompt template (use {text} as placeholder)
            model: Model to use
            
        Returns:
            LLMProcessingResult or None if processing failed
        """
        prompt = prompt_template.replace("{text}", text)
        return self._process_text(text, prompt, "custom", model)
    
    def _process_text(self, original_text: str, prompt: str, processing_type: str, model: str) -> Optional[LLMProcessingResult]:
        """Process text using the LLM API
        
        Args:
            original_text: Original input text
            prompt: Full prompt to send to the LLM
            processing_type: Type of processing being performed
            model: Model to use
            
        Returns:
            LLMProcessingResult or None if processing failed
        """
        if not self.available:
            logger.error("LLM API not available")
            return None
            
        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 512
            }
            
            response = requests.post(
                f"{self.api_url}/chat/completions",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                result = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Clean up result
                result = result.strip()
                
                if result:
                    return LLMProcessingResult(
                        original_text=original_text,
                        processed_text=result,
                        processing_type=processing_type,
                        model_name=model
                    )
                else:
                    logger.error("Empty result from LLM API")
                    return None
            else:
                logger.error(f"LLM API error: {response.status_code}, {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing text with LLM: {e}")
            return None 