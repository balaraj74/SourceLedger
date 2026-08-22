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

DEFAULT_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-3.6-flash", "gemini-1.5-pro"]

def _get_google_api_keys() -> List[str]:
    keys = []
    for i in range(1, 9):
        val = os.getenv(f"GOOGLE_API_KEY{i}", "").strip()
        if val and not val.startswith("your-"):
            keys.append(val)
    gem_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gem_key and gem_key not in keys:
        keys.append(gem_key)
    return keys

class GeminiGatewayClient:
    """
    Client for interacting with the Gemini API Gateway using API_URL="https://free-api-erel.onrender.com/api/generate"
    with automatic high-availability fallback to direct Google Gemini API endpoints.
    """
    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout: int = 4
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
            response = requests.get(url, headers=self.headers, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch key pool status: {e}")
            return {"error": str(e), "total_keys": 0, "keys": []}

    def generate_text(
        self,
        prompt: str,
        model: str = "gemini-2.0-flash",
        temperature: float = 0.2
    ) -> str:
        """
        Text generation requesting the API_URL model endpoint directly with Google API fallback.
        """
        models_to_try = [model] + [m for m in DEFAULT_MODELS if m != model]
        google_keys = _get_google_api_keys()

        base_payload = {
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
            endpoints = [
                (self.api_url, self.headers, True),
                (f"{self.base_url}/v1beta/models/{target_model}:generateContent", self.headers, False)
            ]
            for gkey in google_keys:
                endpoints.append((
                    f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={gkey}",
                    {"Content-Type": "application/json"},
                    False
                ))

            for url, headers, is_proxy_api in endpoints:
                payload = dict(base_payload)
                payload["model"] = target_model
                if not is_proxy_api:
                    payload = {k: v for k, v in payload.items() if k not in ("prompt", "model")}

                try:
                    response = requests.post(
                        url, json=payload, headers=headers, timeout=self.timeout
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
                    logger.warning(f"generate_text error at {url[:45]}... ({target_model}): {e}")
                    last_exception = e

        raise RuntimeError(f"Gateway text generation failed: {last_exception}")

    def generate_multimodal(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: str = "gemini-2.0-flash",
        temperature: float = 0.1,
        response_mime_type: Optional[str] = "application/json"
    ) -> str:
        """
        Multimodal (image + text) generation with API_URL and Google API fallback.
        """
        # Try direct Google GenAI SDK first with KeyRotator if GOOGLE_API_KEY is available
        direct_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY1")
        if direct_key:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=direct_key)
                contents = [
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    prompt
                ]
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type=response_mime_type,
                    system_instruction=system_instruction
                )
                res = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                if res.text:
                    return res.text
            except Exception as direct_err:
                logger.warning(f"Direct Google GenAI SDK multimodal failed: {direct_err}. Trying HTTP gateway...")

        models_to_try = [model] + [m for m in DEFAULT_MODELS if m != model]
        google_keys = _get_google_api_keys()
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

        base_payload: Dict[str, Any] = {
            "prompt": prompt,
            "contents": contents
        }

        if system_instruction:
            base_payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        gen_config: Dict[str, Any] = {"temperature": temperature}
        if response_mime_type:
            gen_config["responseMimeType"] = response_mime_type
        base_payload["generationConfig"] = gen_config

        last_exception = None

        for target_model in models_to_try:
            endpoints = [
                (self.api_url, self.headers, True),
                (f"{self.base_url}/v1beta/models/{target_model}:generateContent", self.headers, False)
            ]
            for gkey in google_keys:
                endpoints.append((
                    f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={gkey}",
                    {"Content-Type": "application/json"},
                    False
                ))

            for url, headers, is_proxy_api in endpoints:
                payload = dict(base_payload)
                payload["model"] = target_model
                if not is_proxy_api:
                    payload = {k: v for k, v in payload.items() if k not in ("prompt", "model")}

                logger.info(f"Attempting multimodal extraction at {url[:45]}... (model: {target_model})")
                try:
                    response = requests.post(
                        url, json=payload, headers=headers, timeout=self.timeout
                    )
                    
                    if response.status_code == 404:
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
                    logger.warning(f"HTTP Error for {url[:45]}... ({target_model}): {http_err}")
                    last_exception = http_err
                except Exception as e:
                    logger.warning(f"Error calling {url[:45]}... ({target_model}): {e}")
                    last_exception = e

        raise RuntimeError(f"All model endpoints failed. Last error: {last_exception}")
