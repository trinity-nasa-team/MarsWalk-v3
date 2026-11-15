"""IA del hábitat (018) con el modelo fingido: sin red ni clave real."""

from marsmap.api.routers.habitat import Telemetry, telemetry_text
from tests.api.conftest import make_client


def _fake(reply="Autorizado. Continúa por la ruta."):
    calls = []

    def llm(api_key, model, messages, timeout_s):
        calls.append({"key": api_key, "model": model, "messages": messages})
        return {"choices": [{"message": {"content": reply}}]}

    return llm, calls


def test_without_key_returns_503(data_dir):
    c = make_client(data_dir, groq_api_key="")
    r = c.post("/api/habitat/chat", json={"message": "hola"})
    assert r.status_code == 503
    assert r.json() == {
        "error": "La IA del hábitat no está configurada.",
        "code": "assistant_unavailable",
    }


def test_chat_sends_prompt_and_telemetry(data_dir):
    c = make_client(data_dir, groq_api_key="test-key", groq_model="m")
    llm, calls = _fake()
    c.app.state.llm_chat = llm
    body = {
        "message": "¿Puedo continuar?",
        "lang": "en",
        "telemetry": {"state": "hold", "o2_pct": 35.5, "hazards": 2, "pending_kind": "reroute"},
        "history": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
    }
    r = c.post("/api/habitat/chat", json=body)
    assert r.status_code == 200
    assert r.json() == {"reply": "Autorizado. Continúa por la ruta.", "model": "m"}
    m = calls[0]["messages"]
    assert calls[0]["key"] == "test-key"
    assert m[0]["role"] == "system" and "Marswalk" in m[0]["content"]
    assert "oxígeno: 36 %" in m[1]["content"] and "Responde en inglés" in m[1]["content"]
    assert [x["role"] for x in m[2:]] == ["user", "assistant", "user"]
    assert m[-1]["content"] == "¿Puedo continuar?"


def test_validation_and_upstream_errors(data_dir):
    c = make_client(data_dir, groq_api_key="k")
    assert c.post("/api/habitat/chat", json={"message": ""}).status_code == 422
    assert c.post("/api/habitat/chat", json={"message": "x" * 401}).status_code == 422
    assert (
        c.post("/api/habitat/chat", json={"message": "x", "telemetry": {"o2_pct": 140}}).status_code
        == 422
    )

    def broken(*_):
        raise TimeoutError

    c.app.state.llm_chat = broken
    r = c.post("/api/habitat/chat", json={"message": "x"})
    assert r.status_code == 502 and r.json()["code"] == "upstream_unavailable"


def test_telemetry_text_marks_missing_values():
    txt = telemetry_text(Telemetry(), "es")
    assert "oxígeno: sin dato" in txt and "ninguna" in txt and "Responde en español" in txt
