"""Smoke test: package imports and version is exposed."""

import polypact


def test_version_exposed() -> None:
    assert polypact.__version__ == "0.1.0"
