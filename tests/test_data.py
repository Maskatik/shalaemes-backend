import io
import wave

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


def test_delete_all_data(tmp_path):
    client = TestClient(create_app(tmp_path))

    session_id = client.post("/api/sessions").json()["id"]
    client.post(
        f"/api/sessions/{session_id}/chunks",
        files={"file": ("0000.wav", make_wav(), "audio/wav")},
    )
    client.post(f"/api/sessions/{session_id}/finish")

    detail = client.get(f"/api/sessions/{session_id}").json()
    word = next(item for item in detail["words"] if item["category"] == "replace")
    client.post(f"/api/sessions/{session_id}/words/{word['idx']}/learn")

    before = client.get("/api/profile").json()
    assert before["sessions"] == 1
    assert before["xp"] == 20
    assert before["words"]["learned"] == 1

    deleted = client.delete("/api/data")
    assert deleted.status_code == 204

    assert client.get("/api/sessions").json() == []
    assert client.get(f"/api/sessions/{session_id}").status_code == 404

    after = client.get("/api/profile").json()
    assert after["sessions"] == 0
    assert after["xp"] == 0
    assert after["words"]["learned"] == 0
    first = next(item for item in after["achievements"] if item["key"] == "first_session")
    assert first["unlocked"] is False
