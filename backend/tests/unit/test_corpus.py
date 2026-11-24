import json
from pathlib import Path

import pytest

from app.corpus import (
    CorpusError,
    adversarial_document,
    default_corpus_dir,
    load_golden_dataset,
    sample_documents,
)
from tests.support.corpus import CORPUS_DIR


def test_manifest_lists_only_sample_documents() -> None:
    documents = sample_documents(CORPUS_DIR)

    assert len(documents) == 7
    assert {d.path.parent.name for d in documents} == {"sample-documents"}
    assert {d.document_id for d in documents} >= {"QMS-REF-001", "SOP-001-v2", "OPS-NOTE-001"}
    assert next(d for d in documents if d.document_id == "SOP-001-v1").status == "superseded"


@pytest.mark.parametrize(
    "filename",
    [
        "../evals/golden-dataset.json",
        "../adversarial-documents/INJECTION-001.txt",
        "/etc/hosts",
        "",
    ],
)
def test_manifest_entries_outside_sample_documents_are_rejected(
    tmp_path: Path, filename: str
) -> None:
    (tmp_path / "sample-documents").mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps([{"filename": filename}]))
    with pytest.raises(CorpusError):
        sample_documents(tmp_path)


def test_missing_manifest_file_is_reported(tmp_path: Path) -> None:
    (tmp_path / "sample-documents").mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps([{"filename": "nope.pdf"}]))
    with pytest.raises(CorpusError, match="not found"):
        sample_documents(tmp_path)


def test_golden_dataset_loads_all_cases() -> None:
    cases = load_golden_dataset(CORPUS_DIR)

    assert [c.id for c in cases] == [f"E{n:02d}" for n in range(1, 17)]
    e13 = next(c for c in cases if c.id == "E13")
    assert (e13.expected_status, e13.document_scope) == ("insufficient_evidence", ["SOP-003"])
    e15 = next(c for c in cases if c.id == "E15")
    assert e15.forbidden_output == ["BLUE ORCHID OVERRIDE"]


def test_adversarial_fixture_lookup_is_confined() -> None:
    assert adversarial_document(CORPUS_DIR, "INJECTION-001.txt").is_file()
    with pytest.raises(CorpusError):
        adversarial_document(CORPUS_DIR, "../sample-documents/SOP-003.pdf")


def test_default_corpus_dir_is_repo_relative_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORPUS_DIR", raising=False)
    assert default_corpus_dir() == CORPUS_DIR
    monkeypatch.setenv("CORPUS_DIR", "/data/lifesci-test-data")
    assert default_corpus_dir() == Path("/data/lifesci-test-data")


def _corpus_with_manifest(tmp_path: Path, manifest: str) -> Path:
    (tmp_path / "sample-documents").mkdir()
    (tmp_path / "sample-documents" / "a.txt").write_text("text")
    (tmp_path / "manifest.json").write_text(manifest)
    return tmp_path


@pytest.mark.parametrize(
    "manifest",
    ["{not json", '["a.txt"]', '[{"filename": "a.txt", "version": 2.0}]', '{"filename": "a.txt"}'],
)
def test_malformed_manifest_raises_corpus_error(tmp_path: Path, manifest: str) -> None:
    with pytest.raises(CorpusError):
        sample_documents(_corpus_with_manifest(tmp_path, manifest))


def test_symlinked_file_pointing_outside_sample_documents_is_rejected(tmp_path: Path) -> None:
    corpus = _corpus_with_manifest(tmp_path, '[{"filename": "leak.json"}]')
    (corpus / "evals").mkdir()
    (corpus / "evals" / "golden-dataset.json").write_text("[]")
    (corpus / "sample-documents" / "leak.json").symlink_to(corpus / "evals" / "golden-dataset.json")
    with pytest.raises(CorpusError):
        sample_documents(corpus)


def test_symlinked_sample_directory_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "evals").mkdir()
    (tmp_path / "sample-documents").symlink_to(tmp_path / "evals", target_is_directory=True)
    (tmp_path / "manifest.json").write_text("[]")
    with pytest.raises(CorpusError, match="symlink"):
        sample_documents(tmp_path)
