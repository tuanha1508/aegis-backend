"""ADK Web entrypoint for a visual Aegis multi-agent graph.

This exports one composed pipeline as `root_agent` so `adk web` renders the
specialist agents and their nesting in the UI.

Set `ADK_WEB_PIPELINE` to one of:
- `pre_storm`
- `active_storm` (default, richest graph)
- `post_storm`
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ADK loads this file as part of the standalone 'agents' package, not 'app.agents'.
# Add the repo root so 'from app.*' imports resolve throughout the codebase.
_repo_root = str(Path(__file__).resolve().parent.parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from app.agents.orchestrator import (  # noqa: E402
    _build_active_storm_pipeline,
    _build_post_storm_pipeline,
    _build_pre_storm_pipeline,
)


def _build_root_agent():
    pipeline = os.getenv("ADK_WEB_PIPELINE", "active_storm").strip().lower()

    if pipeline == "pre_storm":
        return _build_pre_storm_pipeline()
    if pipeline == "post_storm":
        return _build_post_storm_pipeline()
    return _build_active_storm_pipeline()


root_agent = _build_root_agent()
