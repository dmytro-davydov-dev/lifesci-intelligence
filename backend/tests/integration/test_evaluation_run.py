import pytest

from app.config import Settings
from app.evaluation.run import (
    EvaluationSetupError,
    check_target,
    render_markdown,
    run_evaluation,
)
from tests.support.corpus import CORPUS_DIR

pytestmark = pytest.mark.integration


def offline(database_url: str, tmp_path) -> Settings:
    # Explicit fake provider: never inherit MODEL_PROVIDER=openai from the shell.
    return Settings(database_url=database_url, model_provider="fake", storage_dir=tmp_path)


def test_offline_run_compares_modes_on_identical_cases(database_url: str, tmp_path) -> None:
    report = run_evaluation(offline(database_url, tmp_path), CORPUS_DIR)

    assert set(report["summary"]) == {"vector", "hybrid"}
    for summary in report["summary"].values():
        assert summary["cases"] == report["dataset"]["cases"]
        assert summary["errors"] == 0
        assert summary["injection_leaks"] == 0
        assert 0 < summary["recall@8"] <= 1
    by_mode = {
        m: [c["case_id"] for c in report["cases"] if c["mode"] == m] for m in report["summary"]
    }
    assert by_mode["vector"] == by_mode["hybrid"]
    assert "live_model" in report["unavailable"]
    assert "| recall@8 |" in render_markdown(report)


def test_metrics_are_reproducible_across_fresh_ingestions(database_url: str, tmp_path) -> None:
    def metrics() -> dict:
        report = run_evaluation(offline(database_url, tmp_path), CORPUS_DIR)
        return {
            mode: {k: v for k, v in summary.items() if not k.startswith("latency")}
            for mode, summary in report["summary"].items()
        }

    assert metrics() == metrics()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@127.0.0.1:5432/lifesci",
        "postgresql+psycopg://u:p@127.0.0.1:5432/x_evalz",
        'postgresql+psycopg://u:p@127.0.0.1:5432/bad"name_eval',
        "postgresql+psycopg://u:p@prod.example.com:5432/lifesci_eval",
    ],
)
def test_refuses_unsafe_evaluation_targets(url: str) -> None:
    with pytest.raises(EvaluationSetupError):
        check_target(url)


def test_accepts_local_eval_database_and_explicit_remote() -> None:
    assert (
        check_target("postgresql+psycopg://u:p@127.0.0.1/lifesci_eval").database == "lifesci_eval"
    )
    remote = "postgresql+psycopg://u:p@db.example.com/lifesci_eval"
    assert check_target(remote, allow_remote=True).host == "db.example.com"
