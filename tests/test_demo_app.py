import base64
import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from echoturn.audio import pcm16_to_wav
from echoturn.config import dials
from echoturn.store import InMemoryStore
from pipeline_helpers import FakeASR, FakeLLM, FakeTTS

REPLY = "第一句话要写得足够长才不会被并进上一片。第二句话也要足够长才能单独成一片。"
DEMO_APP = (
    Path(__file__).resolve().parent.parent / "examples" / "minimal_call" / "app.py"
)


@pytest.fixture
def demo(monkeypatch):
    """The demo module, loaded by path so no installed package can shadow it."""
    monkeypatch.setenv("ECHOTURN_LLM_PROVIDER", "mock")
    monkeypatch.setenv("ECHOTURN_TTS_PROVIDER", "mock")
    monkeypatch.setenv("ECHOTURN_ASR_PROVIDER", "mock")
    spec = importlib.util.spec_from_file_location("echoturn_demo_app", DEMO_APP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(demo, *, llm=None, tts=None, asr=None, store=None):
    app = demo.create_app(
        llm=llm or FakeLLM([REPLY]),
        tts=tts if tts is not None else FakeTTS(),
        asr=asr or FakeASR(),
        store=store or InMemoryStore(),
    )
    return TestClient(app)


def frames(response):
    """The events of an SSE body, in order."""
    out = []
    for frame in response.text.split("\n\n"):
        if frame.startswith("data: "):
            out.append(json.loads(frame[len("data: "):]))
    return out


def test_the_page_is_served(demo):
    response = build(demo).get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "/api/turn" in response.text


def test_the_config_route_is_the_dial_table_itself(demo):
    values = build(demo).get("/config").json()
    assert values == dials()


def test_the_browser_client_is_served_beside_the_page(demo):
    """A page imports the client, so the demo has to be able to hand it over."""
    client = build(demo)
    entry = client.get("/client/echoturn-client.js")
    assert entry.status_code == 200
    assert "javascript" in entry.headers["content-type"]
    # The processor is loaded by the client from its own directory, so the two
    # have to be served from the same place.
    worklet = client.get("/client/worklet.js")
    assert worklet.status_code == 200
    assert "echoturn-mic" in worklet.text


def test_a_turn_streams_the_events_the_client_expects(demo):
    response = build(demo).post("/api/turn", json={"text": "hello"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    kinds = [event["type"] for event in frames(response)]
    assert kinds[0] == "ack"
    assert "sentence" in kinds
    assert "audio" in kinds
    assert kinds[-1] == "done"


def test_the_reply_is_cleaned_out_of_the_model_output(demo):
    client = build(demo, llm=FakeLLM(["Certainly. </think>Only this."]))
    events = frames(client.post("/api/turn", json={"text": "hello"}))
    assert events[-1]["reply"] == "Only this."


def test_both_sides_of_the_turn_are_written_to_the_window(demo):
    store = InMemoryStore()
    client = build(demo, store=store)
    client.post("/api/turn", json={"text": "are you there"})
    assert store.window("demo") == [
        {"role": "user", "content": "are you there"},
        {"role": "assistant", "content": REPLY},
    ]


def test_the_next_turn_is_given_the_one_before_it(demo):
    llm = FakeLLM([REPLY])
    client = build(demo, llm=llm)
    client.post("/api/turn", json={"text": "first thing"})
    client.post("/api/turn", json={"text": "second thing"})
    prompt = llm.prompts[1]
    assert [message["role"] for message in prompt] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert prompt[1]["content"] == "first thing"
    assert prompt[2]["content"] == REPLY
    assert prompt[3]["content"] == "second thing"


def test_two_conversations_keep_separate_windows(demo):
    store = InMemoryStore()
    client = build(demo, store=store)
    client.post("/api/turn", json={"text": "mine", "session": "a"})
    client.post("/api/turn", json={"text": "yours", "session": "b"})
    assert store.window("a")[0]["content"] == "mine"
    assert store.window("b")[0]["content"] == "yours"


def test_a_text_only_turn_returns_no_audio(demo):
    client = build(demo)
    events = frames(
        client.post("/api/turn", json={"text": "hello", "speak": False})
    )
    assert [event["type"] for event in events if event["type"] == "audio"] == []
    assert events[-1]["type"] == "done"


def test_the_system_prompt_can_be_replaced_by_the_caller(demo):
    llm = FakeLLM([REPLY])
    client = build(demo, llm=llm)
    client.post("/api/turn", json={"text": "hello", "system_prompt": "Be brief."})
    assert llm.prompts[0][0] == {"role": "system", "content": "Be brief."}


def test_the_default_system_prompt_is_used_when_none_is_given(demo):
    llm = FakeLLM([REPLY])
    client = build(demo, llm=llm)
    client.post("/api/turn", json={"text": "hello"})
    assert llm.prompts[0][0]["content"] == demo.DEFAULT_SYSTEM_PROMPT


def test_recognising_a_clip_reports_the_ask_and_the_probe(demo, monkeypatch, tmp_path):
    monkeypatch.setenv("ECHOTURN_MODEL_DIR", str(tmp_path))
    asr = FakeASR("are you there")
    wav = pcm16_to_wav(b"\x00\x00" * 16000, 16000)
    body = build(demo, asr=asr).post(
        "/api/transcribe", json={"audio": base64.b64encode(wav).decode()}
    ).json()
    assert body["text"] == "are you there"
    assert asr.calls == [
        {"bytes": len(wav), "sample_rate": 16000, "fmt": "wav", "lang": "auto"}
    ]
    assert "vad" in body


def test_the_clip_format_is_the_caller_s_choice(demo, monkeypatch, tmp_path):
    """The route passes the format through instead of assuming one."""
    monkeypatch.setenv("ECHOTURN_MODEL_DIR", str(tmp_path))
    asr = FakeASR("are you there")
    wav = pcm16_to_wav(b"\x00\x00" * 16000, 16000)
    build(demo, asr=asr).post(
        "/api/transcribe",
        json={
            "audio": base64.b64encode(wav).decode(),
            "fmt": "pcm",
            "sample_rate": 8000,
            "lang": "en",
        },
    )
    assert asr.calls == [
        {"bytes": len(wav), "sample_rate": 8000, "fmt": "pcm", "lang": "en"}
    ]


def test_the_probe_says_when_the_speech_model_is_not_there(demo, monkeypatch, tmp_path):
    """A host that thinks it installed a model has to be able to find out."""
    monkeypatch.setenv("ECHOTURN_MODEL_DIR", str(tmp_path))
    wav = pcm16_to_wav(b"\x00\x00" * 16000, 16000)
    body = build(demo).post(
        "/api/transcribe", json={"audio": base64.b64encode(wav).decode()}
    ).json()
    assert body["vad"]["engine"] == "energy"
    assert body["vad"]["fallback"] is True
    assert "turn" not in body


def test_a_recording_that_is_not_sixteen_k_mono_is_refused_by_the_probe(
    demo, monkeypatch, tmp_path
):
    monkeypatch.setenv("ECHOTURN_MODEL_DIR", str(tmp_path))
    wav = pcm16_to_wav(b"\x00\x00" * 8000, 8000)
    body = build(demo).post(
        "/api/transcribe", json={"audio": base64.b64encode(wav).decode()}
    ).json()
    assert body["vad"]["fallback"] is True
    assert "16 kHz" in body["vad"]["reason"]


def test_audio_that_is_not_base64_is_a_client_error(demo):
    response = build(demo).post("/api/transcribe", json={"audio": "not base64 !!"})
    assert response.status_code == 400


def test_empty_audio_is_a_client_error(demo):
    response = build(demo).post("/api/transcribe", json={"audio": ""})
    assert response.status_code == 400


def test_an_interrupted_turn_records_what_was_actually_said(demo):
    store = InMemoryStore()
    list(
        demo.record_turn(
            [
                {"type": "sentence", "i": 0, "text": "half a "},
                {"type": "sentence", "i": 0, "text": "sentence"},
                {"type": "aborted", "reason": "superseded"},
            ],
            store,
            "k",
        )
    )
    assert store.window("k") == [
        {"role": "assistant", "content": "half a sentence"}
    ]


def test_an_interrupted_turn_with_nothing_said_records_nothing(demo):
    store = InMemoryStore()
    list(demo.record_turn([{"type": "aborted", "reason": "superseded"}], store, "k"))
    assert store.window("k") == []


def test_a_failed_turn_records_no_reply(demo):
    store = InMemoryStore()
    list(demo.record_turn([{"type": "error", "error": "nope"}], store, "k"))
    assert store.window("k") == []
