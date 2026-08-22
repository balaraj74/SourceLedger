import base64
import logging
import json
import os
from typing import Dict, Any, Optional, List
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("ocr_agent.gateway_client")

def _resolve_base_url(url: Optional[str]) -> str:
    raw_url = (url or os.getenv("API_URL") or "https://free-api-erel.onrender.com/api/generate").rstrip("/")
    if raw_url.endswith("/api/generate"):
        return raw_url[:-13]
    return raw_url

def _resolve_api_url(url: Optional[str]) -> str:
    raw_url = (url or os.getenv("API_URL") or "https://free-api-erel.onrender.com/api/generate").rstrip("/")
    if not raw_url.endswith("/api/generate"):
        return f"{raw_url}/api/generate"
    return raw_url

def _resolve_auth_token(token: Optional[str]) -> str:
    return token or os.getenv("API_KEY") or "sk_proxy_qu7f0nNyFooVFjM3iNb_lmwZr_NP-BuL"

DEFAULT_MODELS = ["gemini-3.6-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

class GeminiGatewayClient:
    """
    Client for interacting with the Gemini API Gateway using API_URL="https://free-api-erel.onrender.com/api/generate".
    Loads API_URL and API_KEY from environment variables (.env).
    """
    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout: int = 60
    ):
        self.api_url = _resolve_api_url(base_url)
        self.base_url = _resolve_base_url(base_url)
        self.auth_token = _resolve_auth_token(auth_token)
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
            "x-api-key": self.auth_token,
            "x-goog-api-key": self.auth_token,
        }

    def get_keys_status(self) -> Dict[str, Any]:
        """
        Queries the health and availability of the gateway key pool.
        """
        url = f"{self.base_url}/api/keys/status"
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch key pool status: {e}")
            return {"error": str(e), "total_keys": 0, "keys": []}

    def generate_text(
        self,
        prompt: str,
        model: str = "gemini-3.6-flash",
        temperature: float = 0.2
    ) -> str:
        """
        Text generation requesting the API_URL model endpoint directly.
        """
        models_to_try = [model] + [m for m in DEFAULT_MODELS if m != model]
        payload = {
            "prompt": prompt,
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature
            }
        }
        
        last_exception = None
        for target_model in models_to_try:
            payload["model"] = target_model
            # 1. Try API_URL direct endpoint first
            urls_to_try = [self.api_url, f"{self.base_url}/v1beta/models/{target_model}:generateContent"]
            for url in urls_to_try:
                try:
                    response = requests.post(
                        url, json=payload, headers=self.headers, timeout=self.timeout
                    )
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                    if "text" in data:
                        return data["text"]
                except Exception as e:
                    logger.warning(f"generate_text error at {url} with {target_model}: {e}")
                    last_exception = e

        raise RuntimeError(f"Gateway text generation failed: {last_exception}")

    def generate_multimodal(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: str = "gemini-3.6-flash",
        temperature: float = 0.1,
        response_mime_type: Optional[str] = "application/json"
    ) -> str:
        """
        Multimodal (image + text) generation requesting API_URL="https://free-api-erel.onrender.com/api/generate".
        """
        models_to_try = [model] + [m for m in DEFAULT_MODELS if m != model]
        base64_data = base64.b64encode(image_bytes).decode("utf-8")

        user_part_image = {
            "inline_data": {
                "mime_type": mime_type,
                "data": base64_data
            }
        }
        user_part_text = {"text": prompt}

        contents = [
            {
                "role": "user",
                "parts": [user_part_image, user_part_text]
            }
        ]

        payload: Dict[str, Any] = {
            "prompt": prompt,
            "contents": contents
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        gen_config: Dict[str, Any] = {"temperature": temperature}
        if response_mime_type:
            gen_config["responseMimeType"] = response_mime_type
        payload["generationConfig"] = gen_config

        last_exception = None

        for target_model in models_to_try:
            payload["model"] = target_model
            urls_to_try = [self.api_url, f"{self.base_url}/v1beta/models/{target_model}:generateContent"]

            for url in urls_to_try:
                logger.info(f"Attempting multimodal extraction at {url} (model: {target_model})")
                try:
                    response = requests.post(
                        url, json=payload, headers=self.headers, timeout=self.timeout
                    )
                    
                    if response.status_code == 404:
                        logger.warning(f"URL {url} returned 404. Retrying with next endpoint...")
                        continue
                        
                    response.raise_for_status()
                    res_data = response.json()

                    candidates = res_data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text_out = parts[0].get("text", "")
                            if text_out:
                                return text_out

                    if "text" in res_data:
                        return res_data["text"]

                except requests.HTTPError as http_err:
                    logger.warning(f"HTTP Error for {url} ({target_model}): {http_err}. Response: {response.text}")
                    last_exception = http_err
                except Exception as e:
                    logger.warning(f"Error calling {url} ({target_model}): {e}")
                    last_exception = e

        raise RuntimeError(f"All model endpoints failed. Last error: {last_exception}")
