import pytest

from app.config import Settings
from app.evaluation.run import (
    EvaluationSetupError,
    prepare_database,
    render_markdown,
    run_evaluation,
)
from tests.support.corpus import CORPUS_DIR

pytestmark = pytest.mark.integration


def test_offline_run_compares_modes_on_identical_cases(database_url: str) -> None:
    report = run_evaluation(Settings(database_url=database_url), CORPUS_DIR)

    assert set(report["summary"]) == {"vector", "hybrid"}
    for summary in report["summary"].values():
        assert summary["cases"] == report["dataset"]["cases"]
        assert summary["errors"] == 0
        assert summary["injection_leaks"] == 0
        assert 0 < summary["recall@8"] <= 1
    ids = {
        mode: [c["case_id"] for c in report["cases"] if c["mode"] == mode]
        for mode in ("vector", "hybrid")
    }
    assert ids["vector"] == ids["hybrid"]
    assert "live_model" in report["unavailable"]
    assert "| recall@8 |" in render_markdown(report)


def test_refuses_to_reset_a_non_evaluation_database() -> None:
    with pytest.raises(EvaluationSetupError):
        prepare_database("postgresql+psycopg://u:p@127.0.0.1:5432/lifesci")
