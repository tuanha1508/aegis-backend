# ADK Web dev UI — uses the repo-local virtualenv without requiring activation.
# Docs: https://google.github.io/adk-docs/runtime/web-interface/
# Default port 8000 conflicts with uvicorn; use 8001 for ADK.
# Windows: if reload fails, pass: --no-reload
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$appDir = Join-Path $repoRoot "app"
$localAdk = Join-Path $repoRoot ".venv\\Scripts\\adk.exe"

if (-not (Test-Path $localAdk)) {
    throw "ADK CLI not found at '$localAdk'. Run '.\.venv\Scripts\pip.exe install -r requirements.txt' first."
}

Set-Location $appDir
& $localAdk web --port 8001 @args
