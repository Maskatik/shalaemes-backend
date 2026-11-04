from app.services.asr_krasr import build_generate_kwargs, words_from_result


def test_words_from_word_timestamps():
    result = {
        "text": " Сәлем дедлайн",
        "chunks": [
            {"text": " Сәлем", "timestamp": (0.0, 0.5)},
            {"text": " дедлайн", "timestamp": (0.5, 1.25)},
        ],
    }
    words = words_from_result(result, offset_ms=1000, duration_sec=2.0)

    assert [word.surface for word in words] == ["Сәлем", "дедлайн"]
    assert words[0].start_ms == 1000
    assert words[0].end_ms == 1500
    assert words[1].start_ms == 1500
    assert words[1].end_ms == 2250


def test_words_from_plain_text_fallback():
    result = {"text": "бір екі үш"}
    words = words_from_result(result, offset_ms=0, duration_sec=3.0)

    assert len(words) == 3
    assert words[0].start_ms == 0
    assert words[-1].end_ms == 3000


def test_generate_kwargs_dynamic_tokens():
    assert build_generate_kwargs(3.0, "kazakh")["max_new_tokens"] == 40
    assert build_generate_kwargs(18.0, "kazakh")["max_new_tokens"] == 96
    assert build_generate_kwargs(30.0, "kazakh")["max_new_tokens"] == 128
    assert build_generate_kwargs(30.0, None).get("language") is None
