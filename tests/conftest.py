"""Shared pytest path bootstrap for agent-os imports."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Suppress PydanticAI startup banner in CI/tests
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

ROOT = Path(__file__).resolve().parents[1] / "agent-os"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
