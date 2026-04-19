"""
Cloud Fallback — routes complex queries to Gemini when on-device
confidence is below the threshold.

NOTE: NOT on the web-server path. src/main.py is deliberately unplugged
from the cloud to preserve the "100% on-device, zero API calls" demo
narrative. Kept here for the standalone CLI (src/agent.py) or for when
hybrid routing is turned back on.

The Cactus engine handles cloud handoff automatically when `cactus auth`
has been configured. This module provides an explicit Gemini fallback
for cases where you want more control over cloud routing logic.

Usage:
    from src.cloud_fallback import CloudFallback
    fallback = CloudFallback()
    response = fallback.query("Write a 500-word essay on quantum computing")
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

from src.config import cfg

# google-genai is optional — only needed for explicit cloud fallback
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.info("google-genai not installed. Cloud fallback disabled. Run: pip install google-genai")


class CloudFallback:
    """
    Fallback to Gemini cloud models for tasks that exceed on-device capability.

    Cactus already supports automatic cloud handoff (when `cloud_handoff=true`
    in the completion response). This class is for explicit/manual fallback
    when you want to route specific query types to the cloud.
    """

    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model_name = model
        self._client = None

        if GENAI_AVAILABLE and cfg.GEMINI_API_KEY:
            self._client = genai.Client(api_key=cfg.GEMINI_API_KEY)
            logger.info(f"☁️ Cloud fallback ready (model={model})")
        else:
            logger.warning("☁️ Cloud fallback not available (missing API key or google-genai)")

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def query(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        max_tokens: int = 1024,
    ) -> Optional[str]:
        """
        Send a prompt to Gemini and return the response text.

        Returns None if the cloud fallback is not available.
        """
        if not self.is_available:
            logger.error("Cloud fallback not available.")
            return None

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "system_instruction": system_prompt,
                    "max_output_tokens": max_tokens,
                },
            )
            return response.text
        except Exception as e:
            logger.error(f"Cloud fallback error: {e}")
            return None

    def should_fallback(self, cactus_result: dict) -> bool:
        """
        Determine whether a Cactus completion result should trigger cloud fallback.

        Checks:
          1. Explicit cloud_handoff flag from Cactus
          2. Low confidence score below threshold
          3. Error in on-device result
        """
        # Cactus already performed handoff
        if cactus_result.get("cloud_handoff", False):
            return False  # Cactus already handled it

        # On-device error
        if not cactus_result.get("success", True):
            return True

        # Low confidence
        confidence = cactus_result.get("confidence", 1.0)
        if confidence < cfg.CLOUD_HANDOFF_THRESHOLD:
            logger.info(
                f"Low confidence ({confidence:.2f} < {cfg.CLOUD_HANDOFF_THRESHOLD}), "
                f"triggering cloud fallback."
            )
            return True

        return False
