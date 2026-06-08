"""Pytest fixtures for MyPolaris tests."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant tests to load this repository's custom component."""
    yield