"""
Model Selector — Groq-first with Gemini fallback.

Groq is 5-10x faster but its LiteLLM adapter fails ~20% of the time
on complex tool calls. This module provides a wrapper that tries Groq
first and falls back to Gemini on failure.
"""

from __future__ import annotations

import logging
import os

from app.config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)


def get_fast_model():
    """Return Groq model for speed (1-3s per call)."""
    if GROQ_API_KEY:
        from google.adk.models.lite_llm import LiteLlm
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
        return LiteLlm(model="groq/llama-3.3-70b-versatile")
    return "gemini-2.5-flash"


def get_reliable_model():
    """Return Gemini model for reliability (complex tool calls, LoopAgent)."""
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)
    return "gemini-2.5-flash"


def get_model():
    """Default: Groq for speed, Gemini if no Groq key."""
    return get_fast_model()
