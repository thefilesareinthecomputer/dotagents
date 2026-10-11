"""Shared test setup.

The spawn-time seat-root check (chat.assert_seat_root) refuses a seat cwd
outside `config.seat_roots`. Suite fixtures seat agents in synthetic paths
like /tmp/peer, which a real installation would rightly reject, so the
roots are widened here to include the temp directories tests actually use.

This widens the ALLOWED SET for tests only. It never disables the check -
the control itself is exercised directly in
tests/test_permission_matrix.py::test_seat_root_is_re_asserted_at_spawn,
which pins both the permit and the refusal.
"""

import json
import tempfile
from pathlib import Path

import pytest

# Aliased: pytest's own `pytest_configure(config)` hook takes a parameter
# named `config`, so the module keeps a distinct name here.
from second_brain import chat, config as brain_config

_real_seat_roots = brain_config.seat_roots


@pytest.fixture(autouse=True)
def isolate_station_state(tmp_path, monkeypatch):
    """The suite never reads the developer's own station. The global claude
    settings the hook preflight scans and the brain home the config loads
    both point at empty temp files; a test that needs specific content sets
    its own, and tests that patch these helpers themselves still win."""
    settings = tmp_path / "station" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"allow": [], "deny": []}, "hooks": {}}))
    monkeypatch.setattr(chat, "_global_settings_path", lambda: settings)
    monkeypatch.setenv("SECOND_BRAIN_HOME", str(tmp_path / "brain-home"))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_seat_roots: run against the unwidened config.seat_roots - "
        "for tests that are ABOUT root derivation and confinement")


@pytest.fixture(autouse=True)
def permit_temp_seat_roots(request, monkeypatch):
    if request.node.get_closest_marker("real_seat_roots"):
        return
    extra = [Path("/tmp").resolve(), Path(tempfile.gettempdir()).resolve()]
    monkeypatch.setattr(brain_config, "seat_roots",
                        lambda: _real_seat_roots() + extra)
