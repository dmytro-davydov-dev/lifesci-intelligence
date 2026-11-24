"""Access to the version-controlled test corpus (lifesci-test-data/).

Only `sample-documents/` entries listed in `manifest.json` are knowledge-base content.
`evals/` (questions, expected answers) and `adversarial-documents/` must never be seeded.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CORPUS_DIR_NAME = "lifesci-test-data"
SAMPLE_DIR = "sample-documents"
ADVERSARIAL_DIR = "adversarial-documents"
GOLDEN_DATASET = Path("evals") / "golden-dataset.json"


class CorpusError(ValueError):
    pass


@dataclass(frozen=True)
class CorpusDocument:
    document_id: str
    path: Path
    version: str | None
    status: str | None


@dataclass(frozen=True)
class EvidenceRef:
    document_id: str
    page: int | None
    section: str | None


@dataclass(frozen=True)
class EvalCase:
    id: str
    category: str
    question: str
    expected_status: str
    expected_facts: list[str]
    gold_evidence: list[EvidenceRef]
    document_scope: list[str] | None
    forbidden_output: list[str]


def default_corpus_dir() -> Path:
    """CORPUS_DIR env (Docker) or the repo-relative lifesci-test-data/ (local, CI)."""
    configured = os.environ.get("CORPUS_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / CORPUS_DIR_NAME


def sample_documents(corpus_dir: Path) -> list[CorpusDocument]:
    """Manifest entries, each required to be a file directly inside sample-documents/."""
    sample_root = (corpus_dir / SAMPLE_DIR).resolve()
    entries = _read_json(corpus_dir / "manifest.json")
    if not isinstance(entries, list):
        raise CorpusError("manifest.json must be a list of documents.")
    documents = []
    for entry in entries:
        filename = str(entry.get("filename", ""))
        path = (sample_root / filename).resolve()
        if path.parent != sample_root or not filename:
            raise CorpusError(f"Manifest entry outside {SAMPLE_DIR}/: {filename!r}")
        if not path.is_file():
            raise CorpusError(f"Manifest file not found: {SAMPLE_DIR}/{filename}")
        documents.append(
            CorpusDocument(
                document_id=str(entry.get("document_id") or path.stem),
                path=path,
                version=entry.get("version"),
                status=entry.get("status"),
            )
        )
    return documents


def adversarial_document(corpus_dir: Path, filename: str) -> Path:
    """Path to an adversarial fixture; for dedicated security tests only."""
    root = (corpus_dir / ADVERSARIAL_DIR).resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        raise CorpusError(f"Adversarial fixture not found: {filename!r}")
    return path


def load_golden_dataset(corpus_dir: Path) -> list[EvalCase]:
    raw = _read_json(corpus_dir / GOLDEN_DATASET)
    cases = raw["cases"] if isinstance(raw, dict) else raw
    return [
        EvalCase(
            id=case["id"],
            category=case["category"],
            question=case["question"],
            expected_status=case["expected_status"],
            expected_facts=list(case.get("expected_facts") or []),
            gold_evidence=[
                EvidenceRef(ref["document_id"], ref.get("page"), ref.get("section"))
                for ref in case.get("gold_evidence") or []
            ],
            document_scope=case.get("document_scope"),
            forbidden_output=list(case.get("forbidden_output") or []),
        )
        for case in cases
    ]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CorpusError(f"Missing corpus file: {path}") from exc
