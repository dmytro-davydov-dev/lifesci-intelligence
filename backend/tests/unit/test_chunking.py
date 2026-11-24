import pytest

from app.domain.chunking import CHARS_PER_TOKEN, PageText, chunk_pages, estimate_tokens


def words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_short_pages_become_one_chunk_each_with_page_numbers() -> None:
    chunks = chunk_pages([PageText(1, "Page one text."), PageText(2, "Page two text.")])
    assert [(c.ordinal, c.page, c.text) for c in chunks] == [
        (0, 1, "Page one text."),
        (1, 2, "Page two text."),
    ]


def test_chunks_never_span_pages() -> None:
    pages = [PageText(1, words(300, "a")), PageText(2, words(300, "b"))]
    for chunk in chunk_pages(pages, chunk_tokens=100, overlap_tokens=20):
        prefix = "a" if chunk.page == 1 else "b"
        assert all(w.startswith(prefix) for w in chunk.text.split())


def test_chunks_respect_size_limit_and_overlap() -> None:
    chunks = chunk_pages([PageText(None, words(1000))], chunk_tokens=50, overlap_tokens=10)

    assert len(chunks) > 1
    assert all(len(c.text) <= 50 * CHARS_PER_TOKEN for c in chunks)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        shared = set(previous.text.split()) & set(current.text.split())
        assert 0 < sum(len(w) + 1 for w in shared) <= 10 * CHARS_PER_TOKEN + 1


def test_every_word_is_covered_in_order() -> None:
    text = words(777)
    chunks = chunk_pages([PageText(None, text)], chunk_tokens=40, overlap_tokens=8)
    seen: list[str] = []
    for chunk in chunks:
        for word in chunk.text.split():
            if not seen or int(word[1:]) > int(seen[-1][1:]):
                seen.append(word)
    assert seen == text.split()
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_prefers_ending_chunks_at_sentence_boundaries() -> None:
    sentence = "Deviations are logged by the shift lead. "
    chunks = chunk_pages([PageText(None, sentence * 40)], chunk_tokens=60, overlap_tokens=10)
    assert all(c.text.endswith(".") for c in chunks)


def test_over_long_word_is_split_to_chunk_size() -> None:
    chunks = chunk_pages([PageText(None, "x" * 100 + " tail")], chunk_tokens=10, overlap_tokens=2)
    assert all(len(c.text) <= 40 for c in chunks)
    assert "".join(c.text.split(" ")[0] for c in chunks[:3]) == "x" * 100


def test_blank_pages_produce_no_chunks() -> None:
    chunks = chunk_pages([PageText(1, "  \n "), PageText(2, "Content here.")])
    assert [(c.ordinal, c.page) for c in chunks] == [(0, 2)]


def test_tracks_markdown_and_numbered_section_headings_across_pages() -> None:
    pages = [
        PageText(1, "# Purpose\nThis SOP defines deviation handling."),
        PageText(2, "Continued purpose text.\n4.2 Deviation Reporting\nReport within 24 hours."),
    ]
    chunks = chunk_pages(pages, chunk_tokens=8, overlap_tokens=1)

    assert chunks[0].section == "Purpose"
    assert chunks[1].section in {"Purpose", None} or chunks[1].page == 1
    page_two = [c for c in chunks if c.page == 2]
    assert page_two[0].section == "Purpose"
    assert page_two[-1].section == "4.2 Deviation Reporting"


@pytest.mark.parametrize(
    "line",
    [
        "3 operators must sign the form.",
        "21 CFR Part 11 Compliance",
        "2024 Annual Review",
        "3 Remove the cap",
    ],
)
def test_lines_not_mistaken_for_numbered_headings(line: str) -> None:
    assert chunk_pages([PageText(None, line)])[0].section is None


@pytest.mark.parametrize(
    ("line", "section"), [("4. Scope", "4. Scope"), ("4.2.1 Triage", "4.2.1 Triage")]
)
def test_numbered_headings_detected(line: str, section: str) -> None:
    assert chunk_pages([PageText(None, f"{line}\nBody text.")])[0].section == section


def test_overlap_must_be_smaller_than_chunk() -> None:
    with pytest.raises(ValueError):
        chunk_pages([PageText(None, "x")], chunk_tokens=10, overlap_tokens=10)


def test_estimate_tokens_rounds_up() -> None:
    assert estimate_tokens("abcde") == 2
