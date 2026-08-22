"""Gemini API Gateway Client — High-availability client wrapper.

Supports interacting with a Gemini API Round-Robin Gateway/Proxy server
or fallback directly to Google GenAI SDK. Handles authentication via
Bearer token, x-api-key, or x-goog-api-key as per the Gateway Integration Spec.
"""

import logging
import os
from typing import Any, Dict, Optional
import httpx

from ..config import settings

logger = logging.getLogger("sourceledger.GeminiGatewayClient")


class GeminiGatewayClient:
    """Client for calling Gemini API through the Round-Robin Gateway or Direct SDK."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        default_model: str = "gemini-3.6-flash",
        timeout: float = 60.0,
    ) -> None:
        raw_url = (
            base_url
            or os.getenv("API_URL")
            or getattr(settings, "api_url", "")
            or getattr(settings, "gemini_proxy_url", "")
            or getattr(settings, "proxy_url", "")
            or "https://free-api-erel.onrender.com/api/generate"
        )
        self.base_url = raw_url.replace("/api/generate", "").rstrip("/")
        self.auth_token = (
            auth_token
            or os.getenv("API_KEY")
            or getattr(settings, "api_key", "")
            or getattr(settings, "gemini_proxy_token", "")
            or getattr(settings, "proxy_auth_token", "")
            or "sk_proxy_qu7f0nNyFooVFjM3iNb_lmwZr_NP-BuL"
        )
        self.default_model = default_model
        self.timeout = timeout

    @property
    def is_proxy_enabled(self) -> bool:
        """Return True if a Gateway proxy base URL is configured."""
        return bool(self.base_url)

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
            headers["x-api-key"] = self.auth_token
            headers["x-goog-api-key"] = self.auth_token
        return headers

    async def generate_simple(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_output_tokens: Optional[int] = None,
    ) -> str:
        """Call the simplified generate endpoint POST /api/generate."""
        if not self.is_proxy_enabled:
            raise ValueError("GeminiGatewayClient base_url is not configured")

        url = f"{self.base_url}/api/generate"
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "model": model or self.default_model,
            "temperature": temperature,
        }
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(url, json=payload, headers=self._get_headers())
            res.raise_for_status()
            data = res.json()
            
            # Extract generated text from candidates payload
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"]
            return ""

    async def generate_native(
        self,
        payload: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call native proxy pass-through endpoint POST /v1beta/models/{model}:generateContent."""
        if not self.is_proxy_enabled:
            raise ValueError("GeminiGatewayClient base_url is not configured")

        target_model = model or self.default_model
        url = f"{self.base_url}/v1beta/models/{target_model}:generateContent"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(url, json=payload, headers=self._get_headers())
            res.raise_for_status()
            return res.json()

    async def check_health(self) -> Dict[str, Any]:
        """Check root health endpoint GET /."""
        if not self.is_proxy_enabled:
            return {"status": "offline", "reason": "No base_url configured"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"{self.base_url}/", headers=self._get_headers())
            res.raise_for_status()
            return res.json()

    async def get_keys_status(self) -> Dict[str, Any]:
        """Check key pool status endpoint GET /api/keys/status."""
        if not self.is_proxy_enabled:
            return {"total_keys": 0, "keys": []}

        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"{self.base_url}/api/keys/status", headers=self._get_headers())
            res.raise_for_status()
            return res.json()
