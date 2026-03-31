"""ASGI entrypoint for local development and deployed operation.

Configures structured logging before the FastAPI app is created so that
every log line emitted during startup is captured in the correct format.

Environment variables (all optional):
    REPOSCAN_DEPLOY_PROFILE   — deployment config name under configs/deployments/
                                Defaults to ``local-dev``.
    REPOSCAN_LOG_JSON         — ``"1"`` or ``"true"`` to force JSON log output.
                                Defaults to auto-detect (JSON when stdout is not a TTY).
"""

from __future__ import annotations

import os

from reposcan_contracts.config.loader import load_deployment_config
from reposcan_contracts.logging import configure_logging

# ── Resolve deployment profile ────────────────────────────────────────────────
_profile = os.environ.get("REPOSCAN_DEPLOY_PROFILE", "local-dev")
_config_path = f"configs/deployments/{_profile}.yaml"
try:
    _deployment = load_deployment_config(_config_path)
    _log_level = _deployment.infrastructure.log_level.value
except Exception:
    _log_level = "info"

# ── Configure logging before any service modules import ───────────────────────
_json_env = os.environ.get("REPOSCAN_LOG_JSON", "").lower()
_json_output: bool | None = True if _json_env in ("1", "true") else (False if _json_env in ("0", "false") else None)
configure_logging(level=_log_level, service_name="api", json_output=_json_output)

# ── Create the application ────────────────────────────────────────────────────
from .app import create_app  # noqa: E402 — must come after logging is configured

app = create_app()
