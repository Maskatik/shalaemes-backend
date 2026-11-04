import io
import wave
from urllib.parse import quote

from fastapi.testclient import TestClient

from app.main import create_app


def make_wav(seconds: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buffer.getvalue()


def test_words_and_learn(tmp_path):
    client = TestClient(create_app(tmp_path))

    session_id = client.post("/api/sessions").json()["id"]
    client.post(
        f"/api/sessions/{session_id}/chunks",
        files={"file": ("0000.wav", make_wav(), "audio/wav")},
    )
    client.post(f"/api/sessions/{session_id}/finish")

    words = client.get("/api/words").json()
    assert words["replace"]
    assert words["filler"]
    assert words["replace"][0]["suggestions"]

    lemma = words["replace"][0]["lemma"]
    learned = client.post(f"/api/words/{quote(lemma)}/learn")
    assert learned.status_code == 200
    assert learned.json()["status"] == "learned"
    assert learned.json()["xp"] == 20

    profile = client.get("/api/profile").json()
    assert profile["xp"] == 20
    assert profile["words"]["learned"] == 1

    today = client.get("/api/words", params={"period": "today"}).json()
    assert today["replace"] or today["filler"]
