"""Round-Robin Gemini API Key Rotator — SourceLedger.

Provides multi-key rotation and automatic fallback when Gemini API keys
hit quota limits (429), expire, or become invalid.
"""

from typing import Optional
from google import genai
from ..config import settings
from ..utils.logging import get_logger

logger = get_logger("APIKeyRotator")


class APIKeyRotator:
    """Round-robin Gemini API key manager with expiration tracking.

    Cycles through all configured API keys (GOOGLE_API_KEY1..8, GOOGLE_API_KEY)
    in a round-robin sequence. If an API key expires, hits quota limits (429),
    or becomes invalid, it can be marked as expired to skip it in future calls.
    """

    def __init__(self, keys: list[str] | None = None) -> None:
        if keys:
            self._keys = [k.strip() for k in keys if k and k.strip()]
        else:
            self._keys = settings.get_google_api_keys()

        self._index = 0
        self._expired_keys: set[str] = set()

    @property
    def total_keys(self) -> int:
        """Total number of configured keys."""
        return len(self._keys)

    @property
    def active_keys_count(self) -> int:
        """Number of currently active (non-expired) keys."""
        return len([k for k in self._keys if k not in self._expired_keys])

    def get_next_key(self) -> Optional[str]:
        """Get the next active API key using Round-Robin rotation."""
        active = [k for k in self._keys if k not in self._expired_keys]
        if not active:
            logger.warning("All Gemini API keys are marked as expired/exhausted!")
            return None

        key = active[self._index % len(active)]
        self._index = (self._index + 1) % len(active)
        logger.info(
            "Round-Robin API Key selected (Key %d/%d active)",
            (self._index % len(active)) + 1,
            len(active),
        )
        return key

    def mark_expired(self, key: str) -> None:
        """Mark an API key as expired or exhausted."""
        if key:
            self._expired_keys.add(key)
            logger.warning(
                "Marked API key ending in '...%s' as EXPIRED/EXHAUSTED. Remaining active keys: %d",
                key[-6:],
                self.active_keys_count,
            )

    def reset(self) -> None:
        """Reset all expired keys back to active state."""
        self._expired_keys.clear()
        self._index = 0
        logger.info("API Key Rotator reset. All keys restored to active pool.")

    def call_with_rotation(self, func, *args, **kwargs):
        """Execute a Gemini API call with key rotation and 429 retry support."""
        attempts = 0
        max_attempts = max(1, self.total_keys)

        while attempts < max_attempts:
            key = self.get_next_key()
            if not key:
                break
            try:
                # If client kwarg or target client uses key
                return func(*args, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str or "exhausted" in err_str:
                    self.mark_expired(key)
                    attempts += 1
                    logger.warning(f"Key retry attempt {attempts}/{max_attempts} due to 429 quota: {e}")
                    continue
                else:
                    raise e
        
        # Fallback single execution
        return func(*args, **kwargs)


# Global singleton rotator instance
key_rotator = APIKeyRotator()
