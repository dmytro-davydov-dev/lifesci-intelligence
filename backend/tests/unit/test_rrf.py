import uuid

from app.domain.retrieval import RetrievedChunk, reciprocal_rank_fusion
from app.infrastructure.retrieval import or_tsquery


def chunk(name: str) -> RetrievedChunk:
    return RetrievedChunk(
        uuid.uuid5(uuid.NAMESPACE_DNS, name), uuid.uuid4(), "d", 1, None, name, 0.0
    )


A, B, C, D = (chunk(n) for n in "abcd")


def texts(chunks: list[RetrievedChunk]) -> list[str]:
    return [c.text for c in chunks]


def test_items_in_both_lists_outrank_single_list_items() -> None:
    fused = reciprocal_rank_fusion([[A, B, C], [C, D]], top_k=4, k=60)
    assert texts(fused)[0] == "c"
    assert fused[0].score == 1 / 63 + 1 / 61


def test_scores_follow_formula_and_list_is_truncated() -> None:
    fused = reciprocal_rank_fusion([[A, B, C]], top_k=2, k=10)
    assert texts(fused) == ["a", "b"]
    assert [c.score for c in fused] == [1 / 11, 1 / 12]


def test_ties_break_by_best_rank_then_id_deterministically() -> None:
    # A is rank 1 in one list, D rank 1 in the other: equal score and best rank.
    first = reciprocal_rank_fusion([[A, B], [D, C]], top_k=4)
    second = reciprocal_rank_fusion([[D, C], [A, B]], top_k=4)
    assert texts(first) == texts(second)
    assert set(texts(first[:2])) == {"a", "d"}


def test_empty_rankings_give_empty_result() -> None:
    assert reciprocal_rank_fusion([[], []]) == []
    assert texts(reciprocal_rank_fusion([[], [B]])) == ["b"]


def test_or_tsquery_keeps_only_alphanumeric_terms() -> None:
    assert or_tsquery("Form QA-12: who's approver?") == "form | qa | 12 | who | s | approver"
    assert or_tsquery("'); DROP TABLE chunks; -- & | ! <->") == "drop | table | chunks"
    assert or_tsquery("?!") == ""


def test_or_tsquery_dedupes_and_caps_terms() -> None:
    assert or_tsquery("QA qa Qa") == "qa"
    assert len(or_tsquery(" ".join(f"t{i}" for i in range(100))).split(" | ")) == 32
