from pathlib import Path
import logging
from typing import Optional, Dict, List, Any, Tuple
import requests
from requests.auth import HTTPBasicAuth
from requests import Session
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
        normalized_url = (api_url or "").rstrip("/")
        if normalized_url.endswith("/v1"):
            self.api_url = normalized_url
        else:
            self.api_url = f"{normalized_url}/v1" if normalized_url else "http://localhost:11434/v1"
        self.auth = HTTPBasicAuth(username, password) if username and password else None

        # Use a persistent session to preserve cookies across redirects (SSO/reverse proxy)
        self.session: Session = requests.Session()
        if self.auth:
            self.session.auth = self.auth
        # Set default headers that work well with reverse proxies
        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mutter/1.0 (+requests)"
        })

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
            base_url = self.api_url[:-3] if self.api_url.endswith('/v1') else self.api_url
            
            response = self.session.get(base_url, timeout=10, allow_redirects=True)
            
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
            response = self.session.get(f"{self.api_url}/models", timeout=10, allow_redirects=True)
            if response.status_code == 200:
                models = response.json().get("data", [])
                return [model.get("id") for model in models]
            else:
                logger.warning(f"Models endpoint returned {response.status_code}")
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
        if "{text}" in prompt_template:
            prompt = prompt_template.replace("{text}", text)
        else:
            prompt = f"{prompt_template}\n\n{text}"
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
                "stream": True,
            }

            # (connect_timeout, read_timeout) — read timeout is per-chunk, so streaming keeps
            # the connection alive across long reasoning traces without tripping a timeout.
            # `with` ensures the response + underlying socket are released on every exit path.
            with self.session.post(
                f"{self.api_url}/chat/completions",
                json=payload,
                timeout=(10, 60),
                stream=True,
            ) as response:
                if response.status_code != 200:
                    logger.error(f"LLM API error: {response.status_code}, {response.text}")
                    return None

                result_parts: List[str] = []
                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    line = raw_line[6:] if raw_line.startswith("data: ") else raw_line
                    if line == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug(f"Skipping non-JSON stream line: {line!r}")
                        continue

                    choices = chunk.get("choices") or [{}]
                    delta = choices[0].get("delta") or {}
                    # Only collect real output content — ignore `reasoning`/`thinking` fields.
                    piece = delta.get("content") or ""
                    if piece:
                        result_parts.append(piece)

                result = "".join(result_parts).strip()

            if result:
                return LLMProcessingResult(
                    original_text=original_text,
                    processed_text=result,
                    processing_type=processing_type,
                    model_name=model
                )
            else:
                logger.error("Empty result from LLM API stream")
                return None

        except Exception as e:
            logger.error(f"Error processing text with LLM: {e}")
            return None 