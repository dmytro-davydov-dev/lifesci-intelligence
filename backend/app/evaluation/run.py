"""Run the golden dataset against vector and hybrid retrieval and write a report.

    EVAL_DATABASE_URL=postgresql+psycopg://lifesci:lifesci@127.0.0.1:5432/lifesci_eval \\
        uv run python -m app.evaluation.run

The target database is reset (its name must end in `_eval` or `_test`). Providers come
from the usual settings: MODEL_PROVIDER=fake (default, offline) or openai (live, opt-in).
Both modes use the identical corpus, questions, providers and settings except retrieval.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess  # noqa: S404 - fixed git command for report provenance
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, create_engine, make_url, text
from sqlalchemy.orm import sessionmaker

from app.application.chat import ChatService, ChatSettings, RetrievalMode
from app.config import Settings
from app.corpus import (
    GOLDEN_DATASET,
    CorpusError,
    EvalCase,
    adversarial_document,
    default_corpus_dir,
    load_golden_dataset,
    sample_documents,
)
from app.domain.providers import ChatError, EmbeddingError
from app.domain.retrieval import RetrievedChunk
from app.evaluation.evidence import EvidenceCandidate
from app.evaluation.metrics import (
    RECALL_KS,
    CaseResult,
    citation_gold_precision,
    contains_forbidden,
    literal_fact_recall,
    recall_at_k,
    reciprocal_rank,
    summarize,
)
from app.infrastructure.db import create_db_engine
from app.infrastructure.models import Chunk, Document
from app.seed import seed_corpus

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = BACKEND_DIR.parent / "evals" / "reports"
MODES: tuple[RetrievalMode, ...] = ("vector", "hybrid")
ADVERSARIAL_FIXTURES = {"INJECTION-001": "INJECTION-001.txt"}
_SAFE_DB_NAME = re.compile(r"[A-Za-z0-9_]+_(?:eval|test)")
_LOCAL_HOSTS = {None, "", "localhost", "127.0.0.1", "::1", "db"}


class EvaluationSetupError(RuntimeError):
    pass


def check_target(url: str, allow_remote: bool = False) -> URL:
    """Refuse anything but a dedicated, local *_eval / *_test database (it gets emptied)."""
    target = make_url(url)
    if not _SAFE_DB_NAME.fullmatch(target.database or ""):
        raise EvaluationSetupError(
            "Evaluation database name must match [A-Za-z0-9_]+_eval or _test."
        )
    if not allow_remote and target.host not in _LOCAL_HOSTS:
        raise EvaluationSetupError(
            "Refusing to reset a non-local database; pass --allow-remote to override."
        )
    return target


def prepare_database(url: str, allow_remote: bool = False) -> None:
    """Create (if needed), migrate and empty a dedicated evaluation database."""
    target = check_target(url, allow_remote)
    name = target.database or ""
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE documents, conversations CASCADE"))
    finally:
        engine.dispose()


@dataclass(frozen=True)
class Corpus:
    fixture_by_runtime: dict[uuid.UUID, str]
    runtime_by_fixture: dict[str, uuid.UUID]
    sample_ids: list[uuid.UUID]


def ingest(app_state: Any, corpus_dir: Path) -> Corpus:
    """Upload the corpus and map runtime ids to fixture ids via manifest filenames."""
    outcomes = seed_corpus(app_state.document_service, corpus_dir)
    if bad := [o.filename for o in outcomes if o.status != "ready"]:
        raise EvaluationSetupError("Corpus documents not ready: " + ", ".join(bad))
    fixture_by_filename = {d.path.name: d.document_id for d in sample_documents(corpus_dir)}
    sample_filenames = set(fixture_by_filename)
    for fixture_id, filename in ADVERSARIAL_FIXTURES.items():
        path = adversarial_document(corpus_dir, filename)
        result = app_state.document_service.upload(path.name, path.read_bytes())
        if result.document.status != "ready":
            raise EvaluationSetupError(f"Adversarial fixture not ready: {filename}")
        fixture_by_filename[path.name] = fixture_id
    if len(set(fixture_by_filename.values())) != len(fixture_by_filename):
        raise EvaluationSetupError("Duplicate fixture document ids in the corpus.")

    documents = app_state.document_service.list_documents()
    unknown = [d.name for d in documents if d.name not in fixture_by_filename]
    if unknown:
        raise EvaluationSetupError("Unexpected documents in evaluation DB: " + ", ".join(unknown))
    fixture_by_runtime = {d.id: fixture_by_filename[d.name] for d in documents}
    return Corpus(
        fixture_by_runtime=fixture_by_runtime,
        runtime_by_fixture={v: k for k, v in fixture_by_runtime.items()},
        sample_ids=sorted((d.id for d in documents if d.name in sample_filenames), key=str),
    )


def _candidate(chunk: RetrievedChunk, corpus: Corpus) -> EvidenceCandidate:
    return EvidenceCandidate(corpus.fixture_by_runtime[chunk.document_id], chunk.page, chunk.text)


def _scope(case: EvalCase, corpus: Corpus) -> list[uuid.UUID]:
    """Explicit case scope, else all sample documents (adversarial fixtures stay isolated)."""
    if case.document_scope:
        return [corpus.runtime_by_fixture[d] for d in case.document_scope]
    return corpus.sample_ids


def evaluate_case(
    case: EvalCase,
    mode: str,
    corpus: Corpus,
    session_factory: sessionmaker,
    chat: ChatService,
) -> CaseResult:
    """Score the retrieval and answer of one chat call (the ranking the answer used)."""
    scope = _scope(case, corpus)
    started = time.perf_counter()
    try:
        result = chat.ask(case.question, document_ids=scope, mode="qa")
    except (ChatError, EmbeddingError) as exc:
        return _failed(case, mode, type(exc).__name__, started)
    latency_ms = (time.perf_counter() - started) * 1000
    retrieved = [_candidate(c, corpus) for c in result.retrieved]

    cited = []
    with session_factory() as session:
        for citation in result.citations:
            chunk = session.get(Chunk, citation.chunk_id)
            fixture = corpus.fixture_by_runtime.get(citation.document_id)
            if chunk is None or fixture is None:
                raise EvaluationSetupError(f"Citation outside the evaluation corpus: {case.id}")
            cited.append(EvidenceCandidate(fixture, chunk.page, chunk.text))

    return CaseResult(
        case_id=case.id,
        category=case.category,
        mode=mode,
        expected_status=case.expected_status,
        status=result.status,
        recall={k: recall_at_k(retrieved, case.gold_evidence, k) for k in RECALL_KS},
        reciprocal_rank=reciprocal_rank(retrieved, case.gold_evidence),
        fact_recall=literal_fact_recall(result.answer, case.expected_facts),
        citation_precision=citation_gold_precision(cited, case.gold_evidence),
        forbidden_leak=(
            contains_forbidden(result.answer, case.forbidden_output)
            if case.forbidden_output
            else None
        ),
        latency_ms=latency_ms,
        citations=len(cited),
    )


def _failed(case: EvalCase, mode: str, error: str, started: float) -> CaseResult:
    return CaseResult(
        case_id=case.id,
        category=case.category,
        mode=mode,
        expected_status=case.expected_status,
        status="error",
        recall={k: None for k in RECALL_KS},
        reciprocal_rank=None,
        fact_recall=None,
        citation_precision=None,
        forbidden_leak=None,
        latency_ms=(time.perf_counter() - started) * 1000,
        error=error,
    )


def run_evaluation(
    settings: Settings, corpus_dir: Path, allow_remote: bool = False
) -> dict[str, Any]:
    from app.infrastructure.providers import build_chat_provider, build_embedding_provider
    from app.main import create_app

    prepare_database(settings.database_url, allow_remote)
    embedder = build_embedding_provider(settings)
    chat_provider = build_chat_provider(settings)
    app = create_app(settings, embedder=embedder, chat_provider=chat_provider)
    corpus = ingest(app.state, corpus_dir)
    engine = create_db_engine(settings)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    cases = load_golden_dataset(corpus_dir)

    chats = {
        mode: ChatService(
            session_factory,
            embedder,
            chat_provider,
            ChatSettings.from_settings(settings, retrieval_mode=mode),
        )
        for mode in MODES
    }
    results: dict[str, list[CaseResult]] = {mode: [] for mode in MODES}
    for index, case in enumerate(cases):
        # Alternate which mode runs first so warm-up effects do not favour one mode.
        order = MODES if index % 2 == 0 else tuple(reversed(MODES))
        for mode in order:
            results[mode].append(evaluate_case(case, mode, corpus, session_factory, chats[mode]))

    with session_factory() as session:
        chunk_count = session.query(Chunk).join(Document).count()
    engine.dispose()
    return build_report(settings, corpus_dir, cases, results, chunk_count)


def _git_commit() -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        output = subprocess.run(  # noqa: S603 - fixed arguments, no user input
            [git, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=BACKEND_DIR,
        )
        dirty = subprocess.run(  # noqa: S603 - fixed arguments, no user input
            [git, "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
            cwd=BACKEND_DIR,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = output.stdout.strip()
    return f"{commit}-dirty" if commit and dirty else commit or None


def build_report(
    settings: Settings,
    corpus_dir: Path,
    cases: list[EvalCase],
    results: dict[str, list[CaseResult]],
    chunk_count: int,
) -> dict[str, Any]:
    dataset_bytes = (corpus_dir / GOLDEN_DATASET).read_bytes()
    live = settings.model_provider == "openai"
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "dataset": {
            "path": str(GOLDEN_DATASET),
            "sha256": hashlib.sha256(dataset_bytes).hexdigest(),
            "cases": len(cases),
            "indexed_chunks": chunk_count,
        },
        "configuration": {
            "model_provider": settings.model_provider,
            "embedding_model": settings.openai_embedding_model if live else "fake-hashed-bow",
            "chat_model": settings.openai_chat_model if live else "fake-extractive",
            "top_k": settings.retrieval_top_k,
            "candidate_pool": settings.retrieval_candidate_pool,
            "rrf_k": settings.rrf_k,
            "context_max_tokens": settings.context_max_tokens,
        },
        "unavailable": {
            "tokens_and_cost": "Provider adapters do not record usage yet.",
            "semantic_support": "No judge model; citation_gold_precision checks location only.",
            **({} if live else {"live_model": "Offline fake providers; not model quality."}),
        },
        "summary": {mode: summarize(rows) for mode, rows in results.items()},
        "cases": [
            {**asdict(row), "recall": {str(k): v for k, v in row.recall.items()}}
            for rows in results.values()
            for row in rows
        ],
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    metrics = list(next(iter(summary.values())).keys())
    lines = [
        f"# Evaluation report ({report['configuration']['model_provider']})",
        "",
        f"- Generated: {report['generated_at']} | commit: {report['git_commit'] or 'n/a'}",
        f"- Dataset: `{report['dataset']['path']}` sha256 `{report['dataset']['sha256'][:12]}`, "
        f"{report['dataset']['cases']} cases, {report['dataset']['indexed_chunks']} chunks",
        "- Configuration: " + ", ".join(f"{k}={v}" for k, v in report["configuration"].items()),
        "- Unavailable: " + "; ".join(f"{k}: {v}" for k, v in report["unavailable"].items()),
        "",
        "## Summary",
        "",
        "| metric | " + " | ".join(summary) + " |",
        "|---|" + "---|" * len(summary),
    ]
    lines += [
        f"| {m} | " + " | ".join(_fmt(summary[mode][m]) for mode in summary) + " |" for m in metrics
    ]
    lines += [
        "",
        "## Cases",
        "",
        "| case | category | mode | expected | status | R@1 | R@3 | R@8 | RR | facts | cites |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["cases"]:
        recall = row["recall"]
        lines.append(
            f"| {row['case_id']} | {row['category']} | {row['mode']} | {row['expected_status']} "
            f"| {row['status']}{'' if row['status'] == row['expected_status'] else ' ✗'} "
            f"| {_fmt(recall['1'])} | {_fmt(recall['3'])} | {_fmt(recall['8'])} "
            f"| {_fmt(row['reciprocal_rank'])} | {_fmt(row['fact_recall'])} "
            f"| {_fmt(row['citation_precision'])} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--allow-remote", action="store_true", help="Allow a non-local DB.")
    args = parser.parse_args(argv)

    url = os.environ.get("EVAL_DATABASE_URL")
    if not url:
        print("error: set EVAL_DATABASE_URL (database name ending in _eval)", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="lifesci-eval-") as storage:
        settings = Settings(database_url=url, storage_dir=Path(storage))
        try:
            report = run_evaluation(
                settings, args.corpus or default_corpus_dir(), args.allow_remote
            )
        except (EvaluationSetupError, CorpusError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["generated_at"][:16].replace(":", "")
    stem = f"{stamp}-{settings.model_provider}"
    (args.output_dir / f"{stem}.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.output_dir / f"{stem}.md").write_text(render_markdown(report))
    print(render_markdown(report).split("## Cases")[0])
    print(f"wrote {args.output_dir / stem}.json and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
