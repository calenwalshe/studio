"""conftest.py — project-level pytest configuration for studio-tui."""
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: marks tests that call external processes (e.g. claude -p) and take ~30-60s",
    )
