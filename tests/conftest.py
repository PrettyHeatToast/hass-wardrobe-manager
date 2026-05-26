"""Shared fixtures for Wardrobe tests."""

from __future__ import annotations

import sys

import pytest

if sys.platform == "win32":
    # pytest-homeassistant-custom-component calls pytest_socket.disable_socket()
    # in its pytest_runtest_setup, which breaks pytest-asyncio's event-loop
    # fixture on Windows (the proactor loop creates a self-pipe via
    # socket.socketpair). Stub the disabler before any test runs.
    import pytest_socket

    pytest_socket.disable_socket = lambda *_a, **_kw: None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable loading of custom integrations in every test."""
    yield
