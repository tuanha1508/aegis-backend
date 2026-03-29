#!/usr/bin/env bash
# ADK Web dev UI — run from repo root after: pip install -r requirements.txt
# Docs: https://google.github.io/adk-docs/runtime/web-interface/
set -e
cd "$(dirname "$0")/../app"
exec adk web --port 8001 "$@"
