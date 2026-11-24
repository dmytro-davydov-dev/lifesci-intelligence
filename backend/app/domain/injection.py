"""Heuristic output guard against prompt injection carried in retrieved sources.

Fencing tells the model that sources are data; this guard checks the result. It flags
sentences addressed to a model (not ordinary procedure text) and rejects answers that
repeat word runs distinctive to those sentences, or long runs of the system prompt.
It is a heuristic backstop, not a guarantee: paraphrased obedience can pass.
"""

import re

_INSTRUCTION = re.compile(
    r"\b(?:ignore|disregard|forget)\b.{0,30}\b(?:previous|prior|above|earlier|all|any|your)\b"
    r".{0,20}\b(?:instructions|rules|prompts?)\b"
    r"|\b(?:reveal|print|show|output|repeat|leak)\b.{0,30}"
    r"\b(?:system prompt|your instructions|hidden instructions)\b"
    r"|\b(?:output|say|print|respond with|reply with)\b.{0,20}\bexact (?:phrase|words)\b"
    r"|\byou are now\b"
    r"|\bact as (?:an? )?(?:ai|assistant|model|chatbot|language model)\b"
    r"|^\s*(?:system|assistant)\s*:\s*(?:you|ignore|disregard|reveal|from now)\b",
    re.IGNORECASE | re.MULTILINE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "this",
        "that",
        "to",
        "with",
    ]
)

ECHO_NGRAM = 3
PROMPT_LEAK_NGRAM = 12

NGram = tuple[str, ...]


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def is_instruction(sentence: str) -> bool:
    return _INSTRUCTION.search(sentence) is not None


def instruction_sentences(text: str) -> list[str]:
    """Sentences of `text` that look like instructions addressed to a model."""
    return [s for s in sentences(text) if is_instruction(s)]


def ngrams(text: str, n: int) -> set[NGram]:
    words = _WORD.findall(text.lower())
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def injection_ngrams(source_texts: list[str], question: str, n: int = ECHO_NGRAM) -> set[NGram]:
    """Word runs found only in instruction-like source sentences.

    Runs also present in the question or in benign source text, or made mostly of
    stopwords, are excluded so answers about legitimate content are not rejected.
    """
    flagged: set[NGram] = set()
    benign = ngrams(question, n)
    for text in source_texts:
        for sentence in sentences(text):
            (flagged if is_instruction(sentence) else benign).update(ngrams(sentence, n))
    return {
        gram
        for gram in flagged - benign
        if sum(word in _STOPWORDS for word in gram) <= (n - 1) // 2
    }


def echoes(answer: str, grams: set[NGram], n: int) -> bool:
    """True when `answer` contains any of the `n`-word runs in `grams`."""
    return bool(grams) and not ngrams(answer, n).isdisjoint(grams)
