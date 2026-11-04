from typing import Literal

from pydantic import BaseModel, Field


class SessionOut(BaseModel):
    id: int
    status: str
    started_at: str
    ended_at: str | None = None
    duration_sec: int | None = None
    foreign_ratio: float | None = None
    top_words: list[str] = Field(default_factory=list)


class WordOut(BaseModel):
    idx: int
    surface: str
    lemma: str
    start_ms: int
    end_ms: int
    lang: str
    category: str
    user_flag: str


class SummaryItem(BaseModel):
    lemma: str
    count: int
    suggestions: list[str] = Field(default_factory=list)
    meaning_kk: str = ""
    advice: str = ""


class SummaryOut(BaseModel):
    total_words: int
    foreign_ratio: float
    replace: list[SummaryItem]
    filler: list[SummaryItem]
    warnings: list[str] = Field(default_factory=list)


class SessionDetail(SessionOut):
    words: list[WordOut]
    summary: SummaryOut | None = None
    error: str | None = None


class ChunkOut(BaseModel):
    session_id: int
    chunks: int


class FinishOut(BaseModel):
    id: int
    status: str


class WordFlagIn(BaseModel):
    user_flag: Literal["none", "asr_error"]


class LearnOut(BaseModel):
    lemma: str
    status: str
    xp: int
    level: int
    level_title: str
    already_learned: bool


class AchievementOut(BaseModel):
    key: str
    title: str
    description: str
    unlocked: bool
    current: int
    target: int


class ProfileWords(BaseModel):
    suggested: int = 0
    learned: int = 0
    used: int = 0
    consolidated: int = 0


class LexiconWordOut(BaseModel):
    lemma: str
    category: str
    meaning_kk: str = ""
    example: str = ""
    count: int = 0
    status: str = "suggested"
    suggestions: list[str] = Field(default_factory=list)


class WordListOut(BaseModel):
    replace: list[LexiconWordOut]
    filler: list[LexiconWordOut]


class ProfileOut(BaseModel):
    display_name: str
    level: int
    level_title: str
    xp: int
    current_level_xp: int
    next_level_xp: int | None = None
    progress: float
    sessions: int
    minutes: int
    foreign_ratio_avg: float | None = None
    words: ProfileWords
    achievements: list[AchievementOut]
