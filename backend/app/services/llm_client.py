import time
import re
import logging
from typing import Type, TypeVar, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types
from google.genai.errors import APIError
from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class GeminiClient:
    """Thread-safe Gemini client wrapper with rate-limiting and retry logic."""

    def __init__(self):
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment or .env file.")
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model
        self.last_call_timestamp = 0.0

    def _rate_limit(self):
        """Ensure calls are spaced out to respect free tier limits."""
        now = time.time()
        elapsed = now - self.last_call_timestamp
        if elapsed < settings.rate_limit_delay_seconds:
            time.sleep(settings.rate_limit_delay_seconds - elapsed)
        self.last_call_timestamp = time.time()

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        max_retries: int = 3,
        temperature: float = 0.1
    ) -> T:
        """Call Gemini with structured output matching a Pydantic schema."""
        config_kwargs = {
            "response_mime_type": "application/json",
            "response_schema": response_schema,
            "temperature": temperature,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_kwargs)

        last_err = None
        for attempt in range(max_retries):
            try:
                self._rate_limit()
                res = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                if not res.text:
                    raise ValueError("Empty response text from Gemini API")
                
                # Parse and validate with Pydantic
                return response_schema.model_validate_json(res.text)

            except Exception as e:
                last_err = e
                err_str = str(e)
                logger.warning(f"Gemini call attempt {attempt+1}/{max_retries} failed: {e}")
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    match = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str, re.IGNORECASE) or re.search(r"'retryDelay':\s*'(\d+)s'", err_str)
                    if match:
                        backoff = float(match.group(1)) + 3.0
                    else:
                        backoff = 35.0
                    logger.info(f"Rate limit encountered. Adaptive backoff for {backoff:.1f}s...")
                else:
                    backoff = (attempt + 1) * 3.0
                time.sleep(backoff)

        raise RuntimeError(f"Gemini call failed after {max_retries} attempts: {last_err}")

