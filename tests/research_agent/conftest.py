"""Research Agent pytest fixtures."""

from __future__ import annotations

import pytest

from agent_runtime.service import get_specialist_gateway, reset_agent_runtime
from master import capabilities
from master.broker_service import reset_broker
from master.engineering_service import reset_engineering_os
from master.project_service import reset_project_os

from helpers import make_test_model


@pytest.fixture
def work(tmp_path):
    root = tmp_path / "PyraWork"
    root.mkdir()
    (root / "global").mkdir()
    (root / "projects").mkdir()
    return root


@pytest.fixture
def runtime_env(work):
    capabilities.reset_registry()
    reset_project_os(work)
    reset_broker(work)
    reset_engineering_os()
    reset_agent_runtime()
    gw = get_specialist_gateway()
    gw.set_override_model(make_test_model())
    capabilities.bootstrap_builtin_capabilities()
    yield gw
    gw.clear_override_model()
    capabilities.reset_registry()
