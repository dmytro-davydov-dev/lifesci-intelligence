"""Repo-relative location of the version-controlled test corpus (works locally and in CI)."""

from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parents[3] / "lifesci-test-data"
