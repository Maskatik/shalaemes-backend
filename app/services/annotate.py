import re
from dataclasses import dataclass, field

from ..lexicon import EN_LEMMAS, FILLERS, KZ_FILLERS, LOAN_OK, REPLACE
from .asr import AsrWord

TOKEN_PATTERN = re.compile(r"[^0-9a-zа-яәғқңөұүһі]+")
REPLACE_LEMMAS = sorted(REPLACE, key=len, reverse=True)
LOAN_LEMMAS = sorted(LOAN_OK, key=len, reverse=True)


@dataclass
class AnnotatedWord:
    surface: str
    lemma: str
    start_ms: int
    end_ms: int
    lang: str
    category: str
    suggestions: list[str] = field(default_factory=list)
    meaning_kk: str = ""
    advice: str = ""


def normalize(surface: str) -> str:
    return TOKEN_PATTERN.sub("", surface.lower())


def match_lemma(token: str, lemmas: list[str], minimum: int) -> str | None:
    for lemma in lemmas:
        if token == lemma:
            return lemma
        if len(lemma) >= minimum and token.startswith(lemma):
            return lemma
    return None


def annotate_word(word: AsrWord) -> AnnotatedWord:
    token = normalize(word.surface)
    if not token:
        return AnnotatedWord(word.surface, word.surface, word.start_ms, word.end_ms, "unknown", "unknown")

    if token in FILLERS:
        lang = "kk" if token in KZ_FILLERS else "ru"
        return AnnotatedWord(word.surface, token, word.start_ms, word.end_ms, lang, "filler")

    loan = match_lemma(token, LOAN_LEMMAS, 4)
    if loan is not None:
        return AnnotatedWord(word.surface, loan, word.start_ms, word.end_ms, "loan", "loan_ok")

    replace = match_lemma(token, REPLACE_LEMMAS, 3)
    if replace is not None:
        values = REPLACE[replace]
        lang = "en" if replace in EN_LEMMAS else "ru"
        return AnnotatedWord(
            word.surface,
            replace,
            word.start_ms,
            word.end_ms,
            lang,
            "replace",
            suggestions=list(values["suggestions"]),
            meaning_kk=values["meaning_kk"],
        )

    return AnnotatedWord(word.surface, token, word.start_ms, word.end_ms, "kk", "kk")


def annotate_words(words: list[AsrWord]) -> list[AnnotatedWord]:
    return [annotate_word(word) for word in words]


class StubAnnotator:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def annotate(self, words: list[AsrWord]) -> list[AnnotatedWord]:
        return annotate_words(words)

