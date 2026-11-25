"""Run the golden dataset against vector and hybrid retrieval and write a report.

    EVAL_DATABASE_URL=postgresql+psycopg://lifesci:lifesci@127.0.0.1:5432/lifesci_eval \\
        uv run python -m app.evaluation.run

The target database is reset (its name must end in `_eval` or `_test`). Providers come
from the usual settings: MODEL_PROVIDER=fake (default, offline), openai or gemini (live, opt-in).
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

from app.application.chat import ChatResult, ChatService, ChatSettings, RetrievalMode
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
from app.domain.intent import route_intent
from app.domain.providers import ChatError, EmbeddingError
from app.domain.retrieval import RetrievedChunk
from app.evaluation.evidence import EvidenceCandidate
from app.evaluation.metrics import (
    RECALL_KS,
    CaseResult,
    ComparisonCaseResult,
    citation_gold_precision,
    contains_forbidden,
    gold_document_coverage,
    literal_fact_recall,
    recall_at_k,
    reciprocal_rank,
    summarize,
    summarize_comparison,
)
from app.infrastructure.db import create_db_engine
from app.infrastructure.models import Chunk, Document
from app.seed import seed_corpus

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = BACKEND_DIR.parent / "evals" / "reports"
COMPARISON_LABELS = BACKEND_DIR.parent / "evals" / "comparison-labels.json"
COMPARISON_CATEGORIES = frozenset({"comparison", "version"})
ASSESSMENT_LABELS = frozenset({"supported", "potential_gap", "insufficient_evidence"})
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


def load_comparison_labels(path: Path, cases: list[EvalCase]) -> dict[str, str | None]:
    """Expected assessment per comparison/version case; every such case must be listed."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))["cases"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise EvaluationSetupError(f"Cannot read comparison labels: {path.name}") from exc
    expected_ids = {c.id for c in cases if c.category in COMPARISON_CATEGORIES}
    if not isinstance(raw, dict) or set(raw) != expected_ids:
        raise EvaluationSetupError("Comparison labels must list exactly the comparison cases.")
    labels: dict[str, str | None] = {}
    for case_id, entry in raw.items():
        assessment = entry.get("expected_assessment") if isinstance(entry, dict) else "invalid"
        if assessment is not None and assessment not in ASSESSMENT_LABELS:
            raise EvaluationSetupError(f"Invalid expected_assessment for {case_id}.")
        labels[case_id] = assessment
    return labels


def _cited(result: ChatResult, corpus: Corpus, session_factory, case_id: str) -> list:
    cited = []
    with session_factory() as session:
        for citation in result.citations:
            chunk = session.get(Chunk, citation.chunk_id)
            fixture = corpus.fixture_by_runtime.get(citation.document_id)
            if chunk is None or fixture is None:
                raise EvaluationSetupError(f"Citation outside the evaluation corpus: {case_id}")
            cited.append(EvidenceCandidate(fixture, chunk.page, chunk.text))
    return cited


def evaluate_comparison(
    case: EvalCase,
    corpus: Corpus,
    session_factory: sessionmaker,
    chat: ChatService,
    expected_assessment: str | None,
) -> ComparisonCaseResult:
    """Run one comparison case through the agent (mode=compare) and score its evidence."""
    started = time.perf_counter()
    try:
        result = chat.ask(case.question, document_ids=_scope(case, corpus), mode="compare")
    except (ChatError, EmbeddingError) as exc:
        return ComparisonCaseResult(
            case_id=case.id,
            category=case.category,
            expected_status=case.expected_status,
            status="error",
            intent="compare",
            evidence_recall=None,
            gold_document_coverage=None,
            citation_precision=None,
            assessments=[],
            expected_assessment=expected_assessment,
            agent_steps=0,
            latency_ms=(time.perf_counter() - started) * 1000,
            error=type(exc).__name__,
        )
    latency_ms = (time.perf_counter() - started) * 1000
    gathered = [_candidate(c, corpus) for c in result.retrieved]
    cited = _cited(result, corpus, session_factory, case.id)
    return ComparisonCaseResult(
        case_id=case.id,
        category=case.category,
        expected_status=case.expected_status,
        status=result.status,
        intent=result.intent,
        evidence_recall=recall_at_k(gathered, case.gold_evidence, len(gathered)),
        gold_document_coverage=gold_document_coverage(
            [c.document_id for c in cited], case.gold_evidence
        ),
        citation_precision=citation_gold_precision(cited, case.gold_evidence),
        assessments=[f.assessment for f in result.findings],
        expected_assessment=expected_assessment,
        agent_steps=result.agent_steps,
        latency_ms=latency_ms,
    )


def routing_report(cases: list[EvalCase], corpus: Corpus) -> dict[str, Any]:
    """The production auto-routing rule against each case's category."""
    misrouted = [
        case.id
        for case in cases
        if route_intent(case.question, "auto", len(_scope(case, corpus)))
        != ("compare" if case.category in COMPARISON_CATEGORIES else "qa")
    ]
    return {"accuracy": 1 - len(misrouted) / len(cases), "misrouted": misrouted}


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

    cited = _cited(result, corpus, session_factory, case.id)
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

    labels = load_comparison_labels(COMPARISON_LABELS, cases)
    comparisons = [
        evaluate_comparison(case, corpus, session_factory, chats["hybrid"], labels[case.id])
        for case in cases
        if case.category in COMPARISON_CATEGORIES
    ]

    with session_factory() as session:
        chunk_count = session.query(Chunk).join(Document).count()
    engine.dispose()
    return build_report(
        settings,
        corpus_dir,
        cases,
        results,
        chunk_count,
        comparisons=comparisons,
        routing=routing_report(cases, corpus),
    )


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
    comparisons: list[ComparisonCaseResult] | None = None,
    routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dataset_bytes = (corpus_dir / GOLDEN_DATASET).read_bytes()
    provider = settings.model_provider
    models = {
        "fake": ("fake-hashed-bow", "fake-extractive"),
        "openai": (settings.openai_embedding_model, settings.openai_chat_model),
        "gemini": (settings.gemini_embedding_model, settings.gemini_model),
    }[provider]
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
            "embedding_model": models[0],
            "chat_model": models[1],
            "top_k": settings.retrieval_top_k,
            "candidate_pool": settings.retrieval_candidate_pool,
            "rrf_k": settings.rrf_k,
            "context_max_tokens": settings.context_max_tokens,
            "agent_max_steps": settings.agent_max_steps,
            "agent_max_searches": settings.agent_max_searches,
            "agent_results_per_search": settings.agent_results_per_search,
        },
        "unavailable": {
            "tokens_and_cost": "Provider adapters do not record usage yet.",
            "semantic_support": "No judge model; citation_gold_precision checks location only.",
            **(
                {"live_model": "Offline fake providers; not model quality."}
                if provider == "fake"
                else {}
            ),
        },
        "summary": {mode: summarize(rows) for mode, rows in results.items()},
        "cases": [
            {**asdict(row), "recall": {str(k): v for k, v in row.recall.items()}}
            for rows in results.values()
            for row in rows
        ],
        "routing": routing,
        "comparison": None
        if comparisons is None
        else {
            "mode": "compare",
            "retrieval_mode": "hybrid",
            "labels": COMPARISON_LABELS.name,
            "summary": summarize_comparison(comparisons),
            "cases": [asdict(row) for row in comparisons],
        },
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
    return "\n".join(lines + _comparison_markdown(report)) + "\n"


def _comparison_markdown(report: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if routing := report.get("routing"):
        misrouted = ", ".join(routing["misrouted"]) or "none"
        lines += [
            "",
            "## Routing",
            "",
            f"- Auto-routing accuracy {_fmt(routing['accuracy'])}; misrouted: {misrouted}",
        ]
    comparison = report.get("comparison")
    if not comparison:
        return lines
    lines += [
        "",
        f"## Comparison agent (mode=compare, {comparison['retrieval_mode']} retrieval)",
        "",
        f"Expected assessments: `evals/{comparison['labels']}`.",
        "",
        "| metric | value |",
        "|---|---|",
        *(f"| {k} | {_fmt(v)} |" for k, v in comparison["summary"].items()),
        "",
        "| case | expected | status | steps | evidence recall | gold docs cited | cites "
        "| assessments | expected assessment |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in comparison["cases"]:
        lines.append(
            f"| {row['case_id']} | {row['expected_status']} | {row['status']} "
            f"| {row['agent_steps']} | {_fmt(row['evidence_recall'])} "
            f"| {_fmt(row['gold_document_coverage'])} | {_fmt(row['citation_precision'])} "
            f"| {', '.join(row['assessments']) or 'none'} | {row['expected_assessment'] or 'n/a'} |"
        )
    return lines


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
