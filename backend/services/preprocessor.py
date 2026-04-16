import re
from typing import Iterable, List


class ReviewPreprocessor:
    """Small text cleaner used by the isolated continuous-learning pipeline."""

    _whitespace_re = re.compile(r"\s+")
    _non_word_re = re.compile(r"[^a-z0-9\s]")

    @classmethod
    def clean_text(cls, text: str) -> str:
        normalized = (text or "").lower().strip()
        normalized = cls._non_word_re.sub(" ", normalized)
        normalized = cls._whitespace_re.sub(" ", normalized)
        return normalized or "no_review_text"

    @classmethod
    def batch_clean(cls, texts: Iterable[str]) -> List[str]:
        return [cls.clean_text(text) for text in texts]
