"""Asistente de voz del HUD con Groq fingido: sin red ni clave real."""

import base64
import json

from marsmap.api.routers.assistant import SYSTEM_PROMPT, parse_interpretation
from tests.api.conftest import make_client


def _llm(payload):
    calls = []

    def llm(api_key, model, messages, timeout_s):
        calls.append({"key": api_key, "model": model, "messages": messages})
        content = payload if isinstance(payload, str) else json.dumps(payload)
        return {"choices": [{"message": {"content": content}}]}

    return llm, calls


def _client(data_dir, payload, heard="Turn a little to the left."):
    c = make_client(data_dir, groq_api_key="test-key", groq_model="m")
    llm, calls = _llm(payload)
    c.app.state.llm_json = llm
    c.app.state.llm_transcribe = lambda key, audio, mime, t: heard
    return c, calls


MOVE = {
    "heard_en": "Turn a little to the left.",
    "kind": "move",
    "robot_cmd": "left",
    "reply_en": "Turning left.",
}
ANSWER = {
    "heard_en": "How far is Mars from the Sun?",
    "kind": "answer",
    "robot_cmd": None,
    "reply_en": "About 228 million kilometers on average.",
}


def test_without_key_returns_503(data_dir):
    c = make_client(data_dir, groq_api_key="")
    r = c.post("/api/assistant/text", json={"message": "gira a la izquierda"})
    assert r.status_code == 503
    assert r.json()["code"] == "assistant_unavailable"


def test_text_move_in_spanish(data_dir):
    c, calls = _client(data_dir, MOVE)
    r = c.post("/api/assistant/text", json={"message": "muévete un poquito a la izquierda"})
    assert r.status_code == 200
    assert r.json() == {**MOVE, "model": "m"}
    msgs = calls[0]["messages"]
    assert msgs[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert msgs[-1] == {"role": "user", "content": "muévete un poquito a la izquierda"}


def test_text_general_question(data_dir):
    c, _ = _client(data_dir, ANSWER)
    r = c.post("/api/assistant/text", json={"message": "¿qué tan lejos está Marte del Sol?"})
    assert r.status_code == 200
    assert r.json()["kind"] == "answer"
    assert r.json()["robot_cmd"] is None


def test_voice_transcribes_then_interprets(data_dir):
    c, calls = _client(data_dir, MOVE, heard="Turn a little to the left.")
    audio = base64.b64encode(b"\x1aE\xdf\xa3" + b"\x00" * 64).decode()
    r = c.post("/api/assistant/voice", json={"audio_b64": audio, "mime": "audio/webm"})
    assert r.status_code == 200
    assert r.json()["robot_cmd"] == "left"
    assert calls[0]["messages"][-1] == {"role": "user", "content": "Turn a little to the left."}


def test_voice_without_speech_and_bad_audio(data_dir):
    c, _ = _client(data_dir, MOVE, heard="")
    audio = base64.b64encode(b"\x00" * 64).decode()
    assert c.post("/api/assistant/voice", json={"audio_b64": audio}).json()["code"] == "no_speech"
    r = c.post("/api/assistant/voice", json={"audio_b64": "esto-no-es-base64!!!!"})
    assert r.status_code == 422
    r = c.post("/api/assistant/voice", json={"audio_b64": audio, "mime": "video/x-evil"})
    assert r.status_code == 422


def test_unknown_robot_command_never_moves(data_dir):
    c, _ = _client(
        data_dir,
        {"heard_en": "Dance.", "kind": "move", "robot_cmd": "dance", "reply_en": "I can't dance."},
    )
    r = c.post("/api/assistant/text", json={"message": "baila"})
    assert r.status_code == 200
    assert r.json()["robot_cmd"] is None
    assert r.json()["kind"] == "answer"


def test_invalid_model_output_is_502_without_details(data_dir):
    c, _ = _client(data_dir, "lo siento, no puedo")
    r = c.post("/api/assistant/text", json={"message": "hola"})
    assert r.status_code == 502
    assert r.json() == {"error": "The assistant is not responding.", "code": "upstream_unavailable"}


def test_parse_interpretation_tolerates_extra_text_and_fixes_kind():
    got = parse_interpretation(
        'Here you go: {"heard_en":"Stop!","kind":"answer","robot_cmd":"stop","reply_en":"Stopping."}'
    )
    assert got.kind == "move" and got.robot_cmd == "stop"


def test_message_too_long_is_rejected(data_dir):
    c, _ = _client(data_dir, ANSWER)
    r = c.post("/api/assistant/text", json={"message": "x" * 401})
    assert r.status_code == 422


def test_route_approval_never_moves_the_robot():
    got = parse_interpretation(
        '{"heard_en":"Authorize the route","kind":"move","robot_cmd":"forward","reply_en":"Moving forward."}'
    )
    assert got.robot_cmd is None and got.kind == "answer"
