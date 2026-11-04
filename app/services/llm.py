import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config import Settings
from ..lexicon import LOAN_OK
from ..llm_schemas import LlmAnnotationBatch, LlmWordAnnotation
from .annotate import AnnotatedWord, StubAnnotator, normalize
from .asr import AsrWord

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "annotate.md"
PROMPT_VERSION = "annotate-v1"
_SYSTEM_PROMPT: str | None = None


def system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        template = PROMPT_PATH.read_text(encoding="utf-8")
        _SYSTEM_PROMPT = template.replace("{{LOAN_OK}}", ", ".join(sorted(LOAN_OK)))
    return _SYSTEM_PROMPT


def build_client(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or None,
        temperature=0,
        timeout=settings.llm_timeout,
        max_tokens=settings.llm_max_tokens,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def message_text(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(part.get("text", ""))
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content)


def parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Response does not contain a JSON object")
    return json.loads(cleaned[start : end + 1])


class LlmAnnotator:
    def __init__(self, settings: Settings, client=None) -> None:
        self.client = client or build_client(settings)
        self.batch_size = max(1, settings.llm_batch_size)
        self.warnings: list[str] = []

    def annotate(self, words: list[AsrWord]) -> list[AnnotatedWord]:
        result: list[AnnotatedWord] = []
        for start in range(0, len(words), self.batch_size):
            batch = words[start : start + self.batch_size]
            annotations = self._annotate_batch(batch)
            missing = 0
            for local_index, word in enumerate(batch):
                annotation = annotations.get(local_index)
                if annotation is None:
                    missing += 1
                result.append(self._to_annotated(word, annotation))
            if missing:
                self.warnings.append(f"{PROMPT_VERSION}: no annotation for {missing} words in batch {start}")
        return result

    def _annotate_batch(self, batch: list[AsrWord]) -> dict[int, LlmWordAnnotation]:
        payload = [{"index": index, "surface": word.surface} for index, word in enumerate(batch)]
        messages = [
            SystemMessage(content=system_prompt()),
            HumanMessage(content=json.dumps({"words": payload}, ensure_ascii=False)),
        ]

        for attempt in range(2):
            response = None
            try:
                response = self.client.invoke(messages)
                raw = message_text(response)
                parsed = LlmAnnotationBatch.model_validate(parse_json(raw))
                mapping = {}
                for annotation in parsed.words:
                    if 0 <= annotation.index < len(batch) and annotation.index not in mapping:
                        mapping[annotation.index] = annotation
                if not mapping:
                    raise ValueError("Empty annotation list")
                return mapping
            except Exception as error:
                if attempt == 0:
                    if response is not None:
                        messages.append(AIMessage(content=message_text(response)))
                    messages.append(
                        HumanMessage(
                            content=(
                                f"Ответ не прошёл валидацию: {error}. "
                                "Верни только валидный JSON по схеме, для каждого index ровно один объект."
                            )
                        )
                    )
                    continue
                self.warnings.append(f"{PROMPT_VERSION}: batch failed: {error}")
                return {}

    def _to_annotated(self, word: AsrWord, annotation: LlmWordAnnotation | None) -> AnnotatedWord:
        if annotation is None:
            token = normalize(word.surface) or word.surface
            return AnnotatedWord(word.surface, token, word.start_ms, word.end_ms, "unknown", "unknown")

        token = normalize(word.surface)
        category = annotation.category
        lemma = normalize(annotation.lemma)
        suggestions = [
            item.word.strip()
            for item in annotation.suggestions
            if item.word.strip()
            and normalize(item.word) != token
            and normalize(item.word) != lemma
        ]
        meaning_kk = next((item.meaning_kk for item in annotation.suggestions if item.meaning_kk), "")
        advice = annotation.advice.strip()

        if token in LOAN_OK and category == "replace":
            category = "loan_ok"
            suggestions = []
            meaning_kk = ""
            advice = ""

        return AnnotatedWord(
            surface=word.surface,
            lemma=annotation.lemma.strip().lower() or token or word.surface,
            start_ms=word.start_ms,
            end_ms=word.end_ms,
            lang=annotation.lang,
            category=category,
            suggestions=suggestions,
            meaning_kk=meaning_kk,
            advice=advice,
        )


def get_annotator(settings: Settings):
    if settings.llm_provider == "stub":
        return StubAnnotator()
    return LlmAnnotator(settings)
