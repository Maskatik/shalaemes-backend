import json

from langchain_core.messages import AIMessage

from app.config import Settings
from app.services.asr import AsrWord
from app.services.llm import LlmAnnotator


def valid_response() -> str:
    return json.dumps(
        {
            "words": [
                {
                    "index": 0,
                    "lemma": "дедлайн",
                    "lang": "ru",
                    "category": "replace",
                    "suggestions": [
                        {"word": "мерзім", "meaning_kk": "белгіленген уақыт", "example": "Мерзімді ұзарттым."}
                    ],
                    "advice": "",
                },
                {
                    "index": 1,
                    "lemma": "короче",
                    "lang": "ru",
                    "category": "filler",
                    "suggestions": [],
                    "advice": "Пауза жасап, ойды жалғастырыңыз.",
                },
                {
                    "index": 2,
                    "lemma": "телефон",
                    "lang": "ru",
                    "category": "replace",
                    "suggestions": [{"word": "телефон", "meaning_kk": "", "example": ""}],
                    "advice": "",
                },
            ]
        },
        ensure_ascii=False,
    )


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def invoke(self, messages):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return AIMessage(content=response)


def make_annotator(tmp_path, responses: list[str]) -> tuple[LlmAnnotator, FakeClient]:
    settings = Settings.from_env(tmp_path)
    client = FakeClient(responses)
    return LlmAnnotator(settings, client=client), client


def test_llm_annotates_words(tmp_path):
    annotator, client = make_annotator(tmp_path, [valid_response()])
    words = [AsrWord("Дедлайнды", 0, 1000), AsrWord("короче", 1000, 2000), AsrWord("телефон", 2000, 3000)]

    result = annotator.annotate(words)

    assert client.calls == 1
    assert [word.surface for word in result] == ["Дедлайнды", "короче", "телефон"]
    assert result[0].category == "replace"
    assert result[0].lemma == "дедлайн"
    assert result[0].suggestions == ["мерзім"]
    assert result[1].category == "filler"
    assert result[1].advice
    assert result[2].category == "loan_ok"
    assert result[2].suggestions == []


def test_llm_retries_on_invalid_json(tmp_path):
    annotator, client = make_annotator(tmp_path, ["not json", valid_response()])
    words = [AsrWord("дедлайн", 0, 1000), AsrWord("короче", 1000, 2000), AsrWord("телефон", 2000, 3000)]

    result = annotator.annotate(words)

    assert client.calls == 2
    assert result[0].category == "replace"


def test_llm_marks_unknown_after_retry(tmp_path):
    annotator, client = make_annotator(tmp_path, ["not json", "still not json"])
    words = [AsrWord("дедлайн", 0, 1000), AsrWord("короче", 1000, 2000)]

    result = annotator.annotate(words)

    assert client.calls == 2
    assert all(word.category == "unknown" for word in result)
    assert annotator.warnings
