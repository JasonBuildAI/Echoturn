"""A small service that runs the whole pipeline in a browser.

This is the reference assembly, and it is deliberately thin: it owns a model, a
voice and a recogniser, one conversation window, and the four routes a page
needs. Everything interesting is in the package this imports, so a host that
wants a different shape can read this file and see exactly which parts are theirs
to replace.

Run it from a clone:

    pip install -e ".[web]"
    python examples/minimal_call/app.py

As a file rather than as ``-m examples.minimal_call.app``, because ``examples``
is a common name for an installed package and a directory that only wins when
nothing else claims the name is a directory that works on some machines.

It works with no keys at all: the offline providers answer with a beep and a
placeholder transcript, so the wiring can be heard before anything is signed up
for.
"""
from __future__ import annotations

import base64
import threading
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from echoturn.audio import decode_16k_mono
from echoturn.config import dials, env_str
from echoturn.endpoint import build_turn
from echoturn.integrations.starlette import LiveTurns, sse_response
from echoturn.pipeline import TurnDeps, TurnInput, run_turn
from echoturn.providers import make_asr, make_llm, make_tts
from echoturn.store import InMemoryStore, TranscriptStore
from echoturn.vad import build_vad

HERE = Path(__file__).resolve().parent
PAGE = HERE / "index.html"
# The browser client lives in the repository, not in the Python package: it is
# shipped as modules for a page to import, and this is where a page finds it.
CLIENT_DIR = HERE.parent.parent / "clients"

# The one thing this demo has to decide for itself. A host would use its own
# product's prompt here; a system line is not something a pipeline can guess.
DEFAULT_SYSTEM_PROMPT = env_str(
    "ECHOTURN_DEMO_SYSTEM",
    "You are a helpful voice assistant. Answer in one or two short sentences.",
)


class TurnRequest(BaseModel):
    """One turn, as the page asks for it."""

    text: str
    session: str = "demo"
    input_kind: str = "text"
    voice_call: bool = False
    speak: bool = True
    system_prompt: str = ""
    quote: dict | None = None


class TranscribeRequest(BaseModel):
    """A recording to recognise, as base64 WAV."""

    audio: str
    sample_rate: int | None = None
    lang: str | None = None


def record_turn(
    events: Iterable[Mapping[str, Any]],
    store: TranscriptStore,
    key: str,
) -> Iterator[dict]:
    """Pass events through, writing the reply to the window as it goes.

    The reply is written when the turn actually finishes, not when it starts: a
    turn that is interrupted should leave behind what was said, not what was
    planned. So an interrupted turn records the sentences that made it out - by
    the same rule that keeps its history readable, a half sentence is what the
    next turn has to make sense of.
    """
    said: list[str] = []
    for event in events:
        kind = event.get("type")
        if kind == "sentence":
            said.append(str(event.get("text", "")))
        elif kind == "done":
            store.append(key, "assistant", str(event.get("reply", "")))
        elif kind == "aborted" and said:
            store.append(key, "assistant", "".join(said))
        yield dict(event)


def probe(audio: bytes) -> dict:
    """Measure how much speech there was, and whether it was finished.

    Both answers come from a model when it is installed and from something worse
    when it is not, and which one happened is in the answer rather than in a log
    line: a host that believes it installed the speech model has to be able to
    find out that it did not. When nothing can judge the end of the turn there is
    no ``turn`` key at all, and the page falls back to the silence cursor it is
    running anyway.
    """
    samples = decode_16k_mono(audio)
    detector = build_vad()
    if samples is None:
        # Not 16 kHz mono. Resampling to guess would hand a model confident
        # nonsense, so the answer says what actually happened instead.
        return {
            "vad": {
                "engine": detector.engine,
                "fallback": True,
                "reason": "the recording is not 16 kHz mono",
            }
        }
    out: dict[str, Any] = {
        "vad": {"engine": detector.engine, **detector.report(samples),
                "fallback": detector.fallback}
    }
    verdict = build_turn().verdict(samples)
    if verdict is not None:
        out["turn"] = verdict
    return out


def create_app(
    *,
    llm: Any = None,
    tts: Any = None,
    asr: Any = None,
    store: TranscriptStore | None = None,
) -> FastAPI:
    """Build the demo service.

    Providers are built from the settings unless the caller injects them, which
    is what lets a test run the routes without a network or an API key.
    """
    app = FastAPI(title="Echoturn minimal call")
    model = llm if llm is not None else make_llm()
    voice = tts if tts is not None else make_tts()
    recogniser = asr if asr is not None else make_asr()
    window = store if store is not None else InMemoryStore()
    live = LiveTurns()

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(PAGE)

    # Served from its own directory so that `worklet.js` sits next to the module
    # that loads it: the client resolves the processor against its own URL, and
    # a page that has to tell it where the file is has a second place to be
    # wrong about it.
    app.mount("/client", StaticFiles(directory=CLIENT_DIR), name="client")

    @app.get("/config")
    def config() -> dict:
        """The whole dial table, so the page holds no copy of any of these numbers."""
        return dials()

    @app.post("/api/transcribe")
    def transcribe(req: TranscribeRequest) -> dict:
        try:
            audio = base64.b64decode(req.audio, validate=True)
        except Exception as exc:  # noqa: BLE001 - a bad body is a client error
            raise HTTPException(status_code=400, detail="audio is not base64") from exc
        if not audio:
            raise HTTPException(status_code=400, detail="audio is empty")
        values = dials()
        text = recogniser.transcribe(
            audio,
            sample_rate=int(req.sample_rate or values["sample_rate"]),
            fmt="wav",
            lang=str(req.lang or values["lang"]),
        )
        return {"text": text, **probe(audio)}

    @app.post("/api/turn")
    def turn(req: TurnRequest):
        key = str(req.session or "demo")
        deps = TurnDeps(llm=model, tts=voice if req.speak else None)
        cancel = threading.Event()
        # A turn that replaces another one under the same key stops it first, so
        # two replies cannot interleave in one window.
        live.begin(key, cancel)
        window.append(key, "user", req.text)
        events = run_turn(
            TurnInput(
                text=req.text,
                input_kind=req.input_kind,
                voice_call=req.voice_call,
                system_prompt=req.system_prompt or DEFAULT_SYSTEM_PROMPT,
                history=window.window(key)[:-1],
                quote=req.quote,
            ),
            deps,
            cancel=cancel,
        )
        return sse_response(
            record_turn(events, window, key),
            cancel,
            key=key,
            live=live,
        )

    return app


app = create_app()


def main() -> None:  # pragma: no cover - the server is the point
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()
