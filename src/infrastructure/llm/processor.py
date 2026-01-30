from pathlib import Path
import logging
from typing import Optional, Dict, List, Any, Tuple
import requests
from requests.auth import HTTPBasicAuth
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
    
    def __init__(self, api_url: str = "http://localhost:8080/v1", username: str = "", password: str = ""):
        """Initialize the text processor
        
        Args:
            api_url: URL of the local LLM API server
            username: Username for HTTP Basic Auth (optional)
            password: Password for HTTP Basic Auth (optional)
        """
        self.api_url = api_url
        self.auth = HTTPBasicAuth(username, password) if username and password else None
        self.available = self._check_availability()
        if self.available:
            logger.info(f"LLM processor initialized with API at {api_url}" + (" (with auth)" if self.auth else ""))
        else:
            logger.warning(f"LLM API not available at {api_url}")
    
    def _check_availability(self) -> bool:
        """Check if the LLM API is available by testing connectivity"""
        try:
            # Just try to reach the base URL - don't require specific endpoints
            # Strip /v1 to get base URL for connectivity check
            base_url = self.api_url.rstrip('/')
            if base_url.endswith('/v1'):
                base_url = base_url[:-3]
            
            response = requests.get(base_url, timeout=5, auth=self.auth, allow_redirects=True)
            
            # Any response means the server is reachable
            logger.info(f"LLM API server responding at {base_url} (status {response.status_code})")
            return True
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Cannot connect to LLM API at {self.api_url}: {e}")
            return False
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout connecting to LLM API at {self.api_url}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error checking LLM API availability: {e}")
            return False
    
    def get_available_models(self) -> List[str]:
        """Get list of available LLM models"""
        if not self.available:
            return []
            
        try:
            response = requests.get(f"{self.api_url}/models", timeout=5, auth=self.auth)
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
        prompt = prompt_template
        if "{text}" in prompt_template:
            prompt = prompt_template.replace("{text}", text)
        else:
            prompt = prompt + "\n\n{text}"
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
                "max_tokens": 32768  # Very high limit - most modern models support 32k+
            }
            
            response = requests.post(
                f"{self.api_url}/chat/completions",
                json=payload,
                timeout=60,  # 60 second timeout for slower models
                auth=self.auth
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"LLM API response: {data}")
                
                # Try standard OpenAI format first
                result = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Some APIs use 'text' instead of 'message.content'
                if not result:
                    result = data.get("choices", [{}])[0].get("text", "")
                
                # Some APIs put response directly in 'response' or 'output'
                if not result:
                    result = data.get("response", "") or data.get("output", "")
                
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
                    logger.error(f"Empty result from LLM API. Response structure: {list(data.keys())}")
                    return None
            else:
                logger.error(f"LLM API error: {response.status_code}, {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing text with LLM: {e}")
            return None 