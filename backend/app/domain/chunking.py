"""Page-aware chunking. Chunks never span pages so citations keep exact page numbers."""

import re
from dataclasses import dataclass

# Token counts are approximated as characters / 4 (no tokenizer dependency).
CHARS_PER_TOKEN = 4
DEFAULT_CHUNK_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 80
MAX_SECTION_LENGTH = 255

_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(?P<title>\S.*)$")
# "4. Title" or "4.2 Title": a period after a 1-2 digit number avoids "21 CFR Part 11" etc.
_NUMBERED_HEADING = re.compile(
    r"^(?P<title>\d{1,2}(?:\.\d{1,2})*\.(?:\d{1,2})?\s+[A-Z][^.!?]{1,100})$"
)
_SENTENCE_END = (".", "!", "?", ":", ";")


@dataclass(frozen=True)
class PageText:
    page: int | None  # 1-based for PDFs, None for plain text
    text: str


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    page: int | None
    section: str | None
    text: str


def estimate_tokens(text: str) -> int:
    return -(-len(text) // CHARS_PER_TOKEN)


def chunk_pages(
    pages: list[PageText],
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[ChunkDraft]:
    if overlap_tokens >= chunk_tokens:
        raise ValueError("overlap must be smaller than chunk size")
    max_chars = chunk_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    drafts: list[ChunkDraft] = []
    section: str | None = None
    for page in pages:
        words, sections = _words_with_sections(page.text, section, max_chars)
        if sections:
            section = sections[-1]
        for start, end in _windows(words, max_chars, overlap_chars):
            drafts.append(
                ChunkDraft(
                    ordinal=len(drafts),
                    page=page.page,
                    section=sections[start],
                    text=" ".join(words[start:end]),
                )
            )
    return drafts


def _words_with_sections(
    text: str, current: str | None, max_chars: int
) -> tuple[list[str], list[str | None]]:
    """Split into words (over-long ones into max_chars pieces) with their active section."""
    words: list[str] = []
    sections: list[str | None] = []
    for line in text.splitlines():
        stripped = line.strip()
        heading = _heading_of(stripped)
        if heading:
            current = heading
        for word in stripped.split():
            for offset in range(0, len(word), max_chars):
                words.append(word[offset : offset + max_chars])
                sections.append(current)
    return words, sections


def _heading_of(line: str) -> str | None:
    match = _MARKDOWN_HEADING.match(line) or _NUMBERED_HEADING.match(line)
    if not match:
        return None
    return match.group("title").strip()[:MAX_SECTION_LENGTH]


def _windows(words: list[str], max_chars: int, overlap_chars: int) -> list[tuple[int, int]]:
    """Greedy word windows, preferring sentence ends, with ~overlap_chars carried over."""
    windows: list[tuple[int, int]] = []
    start, count = 0, len(words)
    while start < count:
        end, length = start, 0
        while end < count and length + len(words[end]) + (end > start) <= max_chars:
            length += len(words[end]) + (end > start)
            end += 1
        if end < count:
            midpoint = start + (end - start) // 2
            for k in range(end - 1, midpoint, -1):
                if words[k].endswith(_SENTENCE_END):
                    end = k + 1
                    break
        windows.append((start, end))
        if end >= count:
            break
        next_start, overlap = end, 0
        while next_start - 1 > start and overlap + len(words[next_start - 1]) + 1 <= overlap_chars:
            next_start -= 1
            overlap += len(words[next_start]) + 1
        start = next_start
    return windows
