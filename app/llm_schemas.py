from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LlmSuggestion(BaseModel):
    word: str
    meaning_kk: str = ""
    example: str = ""


class LlmWordAnnotation(BaseModel):
    index: int
    lemma: str = ""
    lang: Literal["kk", "ru", "en", "unknown"] = "unknown"
    category: Literal["replace", "filler", "loan_ok", "kk", "unknown"] = "unknown"
    suggestions: list[LlmSuggestion] = Field(default_factory=list)
    advice: str = ""

    @field_validator("lang", "category", mode="before")
    @classmethod
    def lower_value(cls, value):
        return value.lower() if isinstance(value, str) else value


class LlmAnnotationBatch(BaseModel):
    words: list[LlmWordAnnotation] = Field(default_factory=list)
