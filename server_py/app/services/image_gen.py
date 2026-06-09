"""
Server-side scene image generation via Google Gemini image models.

Text generation stays on Miriel; Gemini is used here *only* to render scene
images. Generation is intentionally lazy and failure-tolerant: the
``google-genai`` SDK is imported only when a render is actually attempted, so
the server still boots (and the persistent cache keeps serving) even when the
SDK or an API key is unavailable. Callers treat ``None`` as "no image this
time" and gameplay continues unaffected.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Optional

_logger = logging.getLogger(__name__)

# gemini-2.5-flash-image ("Nano Banana") is the current GA image model.
# Override with GEMINI_IMAGE_MODEL (e.g. gemini-3.1-flash-image-preview).
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"
DEFAULT_ASPECT_RATIO = "16:9"


def _api_key() -> Optional[str]:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def image_gen_enabled() -> bool:
    """True when an API key is configured (the SDK is checked lazily at render)."""
    return bool(_api_key())


def get_image_model() -> str:
    return os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)


def generate_scene_image(prompt: str) -> Optional[str]:
    """
    Render ``prompt`` and return a ``data:image/...;base64,...`` URI, or ``None``
    if generation is unavailable or fails. Never raises.
    """
    api_key = _api_key()
    if not api_key:
        _logger.warning("[image_gen] GEMINI_API_KEY not set; skipping generation")
        return None

    model = get_image_model()
    aspect_ratio = os.getenv("GEMINI_IMAGE_ASPECT_RATIO", DEFAULT_ASPECT_RATIO)

    try:
        # Lazy import: a missing/broken SDK must never block server startup.
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        config_kwargs = {"response_modalities": ["IMAGE"]}
        # image_config (aspect ratio) is newer; tolerate SDKs without it.
        try:
            config_kwargs["image_config"] = types.ImageConfig(aspect_ratio=aspect_ratio)
        except Exception:  # noqa: BLE001
            pass

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        data_uri = _extract_image_data_uri(response)
        if data_uri is None:
            _logger.warning("[image_gen] no image part in response (model=%s)", model)
        return data_uri
    except Exception as exc:  # noqa: BLE001 - rendering must never crash gameplay
        _logger.warning("[image_gen] generation failed (model=%s): %s", model, exc)
        return None


def _extract_image_data_uri(response) -> Optional[str]:
    """Pull the first inline image part out of a genai response into a data URI."""
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is None:
                continue
            data = getattr(inline, "data", None)
            if not data:
                continue
            mime = getattr(inline, "mime_type", None) or "image/png"
            # The SDK may return raw bytes or an already-base64 string.
            b64 = base64.b64encode(data).decode("ascii") if isinstance(data, bytes) else str(data)
            return f"data:{mime};base64,{b64}"
    return None


def enrich_scene_prompt(base_prompt: str) -> str:
    """
    Use Miriel to add world-aware visual atmosphere to a scene prompt.

    No silent fallback: if Miriel is unconfigured or errors, this raises and the
    image request fails hard. If Miriel is reachable but returns nothing, the
    base prompt is used (Miriel working, just no extra atmosphere this time).
    """
    from .miriel_client import get_miriel_client, MirielUnavailable

    client = get_miriel_client()
    if not client.enabled:
        raise MirielUnavailable("Miriel is not configured (set MIRIEL_API_KEY).")

    query = (
        "In 2-3 sentences, describe the visual atmosphere and any notable "
        "current details of this fantasy RPG scene for an illustration. "
        "Fold in relevant recent world events or conditions. Describe only "
        "what is visibly present — no text, no UI, no labels.\n\n"
        f"Scene:\n{base_prompt}"
    )
    # NOT wrapped in try/except: a Miriel outage propagates and fails the render.
    resp = client.query(query=query, project="questai", force_exhaustive=False)
    answer = ((resp or {}).get("results", {}) or {}).get("answer", "")
    answer = (answer or "").strip()
    if answer:
        return f"{base_prompt}\n\nAtmosphere & current details: {answer}"
    return base_prompt
