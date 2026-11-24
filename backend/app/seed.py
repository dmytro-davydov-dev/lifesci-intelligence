"""Seed the knowledge base with the corpus sample documents (idempotent).

    uv run python -m app.seed                      # local, repo-relative corpus
    docker compose exec api python -m app.seed     # inside Compose (CORPUS_DIR)

Only manifest-listed files in sample-documents/ are ingested; evaluation data and
adversarial fixtures are never seeded.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from app.application.documents import DocumentService
from app.corpus import CorpusError, default_corpus_dir, sample_documents
from app.domain.documents import DocumentValidationError


@dataclass(frozen=True)
class SeedOutcome:
    filename: str
    outcome: str  # created | duplicate | failed | rejected
    status: str | None
    detail: str | None = None


def seed_corpus(service: DocumentService, corpus_dir: Path) -> list[SeedOutcome]:
    outcomes = []
    for document in sample_documents(corpus_dir):
        try:
            result = service.upload(
                document.path.name, document.path.read_bytes(), document.version
            )
        except DocumentValidationError as exc:
            outcomes.append(SeedOutcome(document.path.name, "rejected", None, exc.message))
            continue
        stored = result.document
        if stored.status == "failed":
            outcome = "failed"
        else:
            outcome = "duplicate" if result.duplicate else "created"
        outcomes.append(SeedOutcome(document.path.name, outcome, stored.status, stored.error))
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=None, help="Corpus root directory.")
    args = parser.parse_args(argv)
    corpus_dir = args.corpus or default_corpus_dir()

    from app.main import create_app  # deferred: builds DB engine and providers

    try:
        outcomes = seed_corpus(create_app().state.document_service, corpus_dir)
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for item in outcomes:
        suffix = f" - {item.detail}" if item.detail else ""
        print(f"{item.outcome:<9} {item.filename} [{item.status or '-'}]{suffix}")
    bad = [o for o in outcomes if o.outcome in {"failed", "rejected"}]
    print(f"{len(outcomes) - len(bad)}/{len(outcomes)} sample documents ready from {corpus_dir}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
