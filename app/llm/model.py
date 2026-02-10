"""
LLM client abstraction for code review.

Supports Anthropic (Claude) and OpenAI models with retry logic,
structured output parsing, and error handling.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import Settings
from app.llm.schemas import CodeReview

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass


class LLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.LLM_MODEL
    
    @abstractmethod
    async def generate_review(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> CodeReview:
        """
        Generate a structured code review.
        
        Args:
            system_prompt: System/instructions prompt
            user_prompt: User prompt with PR details
            temperature: Sampling temperature (0.0 for deterministic)
        
        Returns:
            Parsed CodeReview object
        
        Raises:
            LLMError: If generation or parsing fails
        """
        pass
    
    @abstractmethod
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Generate raw JSON response.
        
        Args:
            system_prompt: System/instructions prompt
            user_prompt: User prompt
            temperature: Sampling temperature
        
        Returns:
            Parsed JSON dictionary
        
        Raises:
            LLMError: If generation or parsing fails
        """
        pass
    
    def _parse_review(self, response_text: str) -> CodeReview:
        """
        Parse LLM response into CodeReview schema.
        
        Args:
            response_text: Raw LLM response text
        
        Returns:
            Validated CodeReview object
        
        Raises:
            LLMError: If parsing or validation fails
        """
        try:
            # Try to extract JSON from response
            json_str = self._extract_json(response_text)
            data = json.loads(json_str)
            
            # Validate against schema
            review = CodeReview(**data)
            logger.info(f"Parsed review with {len(review.comments)} comments")
            return review
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise LLMError(f"Invalid JSON response: {e}")
        except Exception as e:
            logger.error(f"Failed to validate review schema: {e}")
            raise LLMError(f"Schema validation failed: {e}")
    
    def _extract_json(self, text: str) -> str:
        """
        Extract JSON from LLM response, handling markdown code blocks.
        
        Args:
            text: Raw response text
        
        Returns:
            Clean JSON string
        """
        # Remove markdown code blocks if present
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            text = text[start:end].strip()
        
        return text.strip()


class AnthropicClient(LLMClient):
    """Anthropic (Claude) client implementation."""
    
    def __init__(self, settings: Settings):
        super().__init__(settings)
        try:
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        except ImportError:
            raise LLMError("anthropic package not installed. Run: pip install anthropic")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(LLMError),
    )
    async def generate_review(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> CodeReview:
        """Generate structured code review using Claude."""
        try:
            response = await self.client.messages.create(
                model=self.model_name,
                max_tokens=4096,
                temperature=temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            # Extract text from response
            response_text = response.content[0].text
            logger.debug(f"Claude response: {response_text[:200]}...")
            
            # Parse and validate
            return self._parse_review(response_text)
            
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            raise LLMError(f"Claude generation failed: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(LLMError),
    )
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Generate raw JSON response using Claude."""
        try:
            response = await self.client.messages.create(
                model=self.model_name,
                max_tokens=4096,
                temperature=temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            response_text = response.content[0].text
            json_str = self._extract_json(response_text)
            return json.loads(json_str)
            
        except Exception as e:
            logger.error(f"Claude JSON generation error: {e}")
            raise LLMError(f"Claude JSON generation failed: {e}")


class OpenAIClient(LLMClient):
    """OpenAI client implementation."""
    
    def __init__(self, settings: Settings):
        super().__init__(settings)
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        except ImportError:
            raise LLMError("openai package not installed. Run: pip install openai")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(LLMError),
    )
    async def generate_review(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> CodeReview:
        """Generate structured code review using OpenAI."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"}  # Force JSON mode
            )
            
            response_text = response.choices[0].message.content
            logger.debug(f"OpenAI response: {response_text[:200]}...")
            
            return self._parse_review(response_text)
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMError(f"OpenAI generation failed: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(LLMError),
    )
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Generate raw JSON response using OpenAI."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"}
            )
            
            response_text = response.choices[0].message.content
            return json.loads(response_text)
            
        except Exception as e:
            logger.error(f"OpenAI JSON generation error: {e}")
            raise LLMError(f"OpenAI JSON generation failed: {e}")


def get_llm_client(settings: Settings) -> LLMClient:
    """
    Factory function to get the appropriate LLM client.
    
    Args:
        settings: Application settings
    
    Returns:
        Configured LLM client (Anthropic or OpenAI)
    
    Raises:
        ValueError: If provider is not supported
    """
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "anthropic":
        logger.info(f"Initializing Anthropic client with model {settings.LLM_MODEL}")
        return AnthropicClient(settings)
    elif provider == "openai":
        logger.info(f"Initializing OpenAI client with model {settings.LLM_MODEL}")
        return OpenAIClient(settings)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}. Use 'anthropic' or 'openai'")