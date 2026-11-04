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


def test_health(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["asr"] == "stub"


def test_session_flow(tmp_path):
    client = TestClient(create_app(tmp_path))

    created = client.post("/api/sessions")
    assert created.status_code == 201
    session_id = created.json()["id"]
    assert created.json()["status"] == "recording"

    uploaded = client.post(
        f"/api/sessions/{session_id}/chunks",
        files={"file": ("0000.wav", make_wav(), "audio/wav")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["chunks"] == 1

    finished = client.post(f"/api/sessions/{session_id}/finish")
    assert finished.status_code == 202

    detail = client.get(f"/api/sessions/{session_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "ready"
    assert body["duration_sec"] == 1
    assert body["summary"]["total_words"] > 0
    assert body["summary"]["replace"]
    assert body["summary"]["filler"]
    assert any(word["category"] == "replace" for word in body["words"])
    assert any(word["category"] == "loan_ok" or word["category"] == "kk" for word in body["words"])


def test_finish_requires_audio(tmp_path):
    client = TestClient(create_app(tmp_path))
    session_id = client.post("/api/sessions").json()["id"]
    response = client.post(f"/api/sessions/{session_id}/finish")
    assert response.status_code == 400


def test_delete_session(tmp_path):
    client = TestClient(create_app(tmp_path))
    session_id = client.post("/api/sessions").json()["id"]
    deleted = client.delete(f"/api/sessions/{session_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/sessions/{session_id}").status_code == 404


def test_profile_flag_and_learn(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/profile").json()["xp"] == 0

    session_id = client.post("/api/sessions").json()["id"]
    client.post(
        f"/api/sessions/{session_id}/chunks",
        files={"file": ("0000.wav", make_wav(), "audio/wav")},
    )
    client.post(f"/api/sessions/{session_id}/finish")
    detail = client.get(f"/api/sessions/{session_id}").json()
    word = next(item for item in detail["words"] if item["category"] == "replace")

    flagged = client.patch(
        f"/api/sessions/{session_id}/words/{word['idx']}",
        json={"user_flag": "asr_error"},
    )
    assert flagged.status_code == 200
    assert flagged.json()["user_flag"] == "asr_error"

    invalid = client.patch(
        f"/api/sessions/{session_id}/words/{word['idx']}",
        json={"user_flag": "bad"},
    )
    assert invalid.status_code == 422

    learned = client.post(f"/api/sessions/{session_id}/words/{word['idx']}/learn")
    assert learned.status_code == 200
    assert learned.json()["status"] == "learned"
    assert learned.json()["xp"] == 20
    assert learned.json()["already_learned"] is False

    again = client.post(f"/api/sessions/{session_id}/words/{word['idx']}/learn")
    assert again.status_code == 200
    assert again.json()["already_learned"] is True
    assert again.json()["xp"] == 20

    profile = client.get("/api/profile").json()
    assert profile["xp"] == 20
    assert profile["words"]["learned"] == 1
    first = next(item for item in profile["achievements"] if item["key"] == "first_session")
    assert first["unlocked"] is True
