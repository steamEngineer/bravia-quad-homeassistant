"""Tests for scripts/forbid_private_commit.sh path denylist."""

from __future__ import annotations

import subprocess

import pytest

from tests.conftest import REPO_ROOT

FORBID_SCRIPT = REPO_ROOT / "scripts" / "forbid_private_commit.sh"


def check_path(path: str) -> bool:
    """Return True when the path is forbidden."""
    result = subprocess.run(  # noqa: S603
        [str(FORBID_SCRIPT), "--check-path", path],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode != 0


def scan_diff(diff: str) -> bool:
    """Return True when the diff contains forbidden credential-shaped JSON."""
    diff_file = REPO_ROOT / ".cache" / "forbid_scan_test.diff"
    diff_file.parent.mkdir(parents=True, exist_ok=True)
    diff_file.write_text(diff, encoding="utf-8")
    result = subprocess.run(  # noqa: S603
        [str(FORBID_SCRIPT), "--scan-diff-file", str(diff_file)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode != 0


@pytest.mark.parametrize(
    ("path", "forbidden"),
    [
        ("docs/development.md", False),
        ("docs/README.md", False),
        ("scripts/check_connection.py", False),
        ("scripts/grpc/get_session_keys.py", False),
        ("config/configuration.yaml", False),
        ("docs/handoff-probe-B3-20260703.json", True),
        ("scripts/grpc/session_keys.json", True),
        ("config/.storage/core.config_entries", True),
        (".cache/frida/foo.bin", True),
    ],
)
def test_path_denylist(path: str, forbidden: bool) -> None:
    assert check_path(path) is forbidden


PLACEHOLDER_HMAC = "1" * 64
REAL_HMAC = "d6e0edbb98b3442a1fb244dd05e69cb156c0b0ae68808844297f5c642368eb6a"


def test_grpc_json_placeholder_diff_allowed() -> None:
    diff = f'+  "hmac_key": "{PLACEHOLDER_HMAC}"\n'
    assert not scan_diff(diff)


def test_grpc_json_real_credential_diff_forbidden() -> None:
    diff = f'+  "hmac_key": "{REAL_HMAC}"\n'
    assert scan_diff(diff)
