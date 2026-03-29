"""
Safe Runner — Runs an ADK agent with automatic Groq→Gemini fallback.

First attempt uses Groq (fast, 1-3s). If it fails due to tool-call
format errors, automatically retries with Gemini (reliable, 5-15s).

Total worst case: ~18s (3s Groq fail + 15s Gemini retry)
Best case: ~3s (Groq succeeds)
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Callable

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

APP_NAME = "aegis"


async def run_agent_with_fallback(
    build_agent_fn: Callable[[Any], Agent],
    prompt: str,
    session_prefix: str = "agent",
) -> tuple[str, bool]:
    """Run an agent with Groq-first, Gemini-fallback.

    Args:
        build_agent_fn: Function that takes a model and returns an Agent.
        prompt: The user prompt to send.
        session_prefix: Prefix for session ID.

    Returns:
        Tuple of (response_text, used_fallback).
    """
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    models_to_try = []
    if GROQ_API_KEY:
        models_to_try.append(("groq", LiteLlm(model="groq/llama-3.3-70b-versatile")))
    models_to_try.append(("gemini", "gemini-2.5-flash"))

    for model_name, model in models_to_try:
        try:
            agent = build_agent_fn(model)
            session_service = InMemorySessionService()
            runner = Runner(
                agent=agent,
                app_name=APP_NAME,
                session_service=session_service,
            )

            session_id = f"{session_prefix}_{uuid.uuid4().hex[:8]}"
            session = await session_service.create_session(
                app_name=APP_NAME,
                user_id="aegis_system",
                session_id=session_id,
            )

            user_message = types.Content(
                role="user",
                parts=[types.Part(text=prompt)],
            )

            final_text = ""
            async for event in runner.run_async(
                user_id="aegis_system",
                session_id=session.id,
                new_message=user_message,
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    final_text = event.content.parts[0].text

            used_fallback = model_name != "groq"
            if used_fallback:
                logger.info("Agent %s succeeded with Gemini fallback", session_prefix)
            return final_text, used_fallback

        except Exception as e:
            if model_name == "groq" and len(models_to_try) > 1:
                logger.warning(
                    "Groq failed for %s, retrying with Gemini: %s",
                    session_prefix, str(e)[:80],
                )
                continue
            raise

    return "", True
