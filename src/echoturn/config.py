"""Settings, read from the environment at the moment they are asked for.

Nothing here is copied into a module-level constant. A host that changes a
setting while the process is running - an operator editing a config file, a test
patching the environment - has to see the new value, and a snapshot taken at
import time cannot do that. The failure that follows is the quiet kind: the
running process keeps using the old number and no log line ever mentions it.

Two shapes live in this module and they are worth telling apart. :func:`env_str`
and friends read one variable. :data:`DIALS` is the table of every turn-taking
threshold the pipeline uses, and it is the only place those numbers are written
down - a second copy in a provider, or in a demo page, is how one of them ends up
stale while everything still looks fine.

The third thing this module does is refuse to be quiet. Every fallback below
still returns the shipped value rather than failing, because one mistyped line in
a config file must not stop a conversation - but it also writes one log line
naming the variable, the value it could not read and the default it used. A
setting that looks changed while the process runs the old number is the most
expensive kind of bug there is: nothing is red, and the symptom is "I told it to
do something else and it did not".
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, NamedTuple

log = logging.getLogger("echoturn.config")

# Every setting this package reads starts with this. A generic name like LANG or
# TIMEOUT does not belong to us, and a host that already sets one for its own
# reasons should not silently retune our pipeline by doing so.
ENV_PREFIX = "ECHOTURN_"

# The spellings a configuration file may use for "no". Anything else is true,
# including an empty string, because an empty value is how a file says "leave
# the default alone" and blank-is-unset is handled before this point.
FALSE_VALUES = ("0", "off", "no", "false")

# Where the packages that are too big to ship inside a wheel are looked for. The
# speech and endpointing models are tens of megabytes each, so they are fetched
# on demand by a script and live outside version control - which means the
# location has to be a setting rather than a convention.
DEFAULT_MODEL_DIR = "models"


def env_str(name: str, default: str = "") -> str:
    """Read ``name``; a blank value counts as unset.

    This is not fussiness. A config file line of ``ECHOTURN_TTS_PROVIDER=`` means
    "use the default", but the environment hands back an empty string, and a
    factory that takes it at face value reports an unknown provider called "".
    From the outside that reads as "it stopped speaking and nobody changed
    anything".
    """
    value = os.getenv(name, "")
    return value.strip() if value and value.strip() else str(default)


# Names that have already had their one line. A value is read every time it is
# used - some of these are read per request - and a warning that repeats is a
# warning nobody reads, which is the same failure as no warning at all.
_warned: set[str] = set()


def warn_once(name: str, text: str, *args: Any) -> None:
    """Say one thing about one setting, once per process."""
    if name in _warned:
        return
    _warned.add(name)
    log.warning(text, *args)


def _env_fallback(name: str, raw: str, default: Any, kind: str) -> None:
    """Report a value that could not be read, naming what was used instead."""
    warn_once(
        name,
        "%s=%r is not %s, so this setting runs on its default %s; fix the value "
        "for it to take effect",
        name,
        raw,
        kind,
        default,
    )


def env_int(name: str, default: int) -> int:
    """Read an integer; a blank value takes ``default``, an unreadable one says so.

    Blank and unreadable are deliberately different answers to the same reading.
    ``KEY=`` is how a config file says "leave this alone", so it is not worth a
    log line. ``KEY=12,5`` is somebody who meant to change this and did not, and
    that one is worth exactly one line.
    """
    raw = env_str(name, "")
    if not raw:
        return int(default)
    try:
        return int(raw)
    except ValueError:
        _env_fallback(name, raw, default, "an integer")
        return int(default)


def env_float(name: str, default: float) -> float:
    """Read a float; the same two answers as :func:`env_int`."""
    raw = env_str(name, "")
    if not raw:
        return float(default)
    try:
        return float(raw)
    except ValueError:
        _env_fallback(name, raw, default, "a number")
        return float(default)


def env_bool(name: str, default: bool = False) -> bool:
    """Read a flag; see :data:`FALSE_VALUES` for what counts as off."""
    return env_str(name, "1" if default else "0").lower() not in FALSE_VALUES


class Dial(NamedTuple):
    """One tunable number, its environment variable and its shipped value."""

    env: str
    key: str
    kind: str
    default: Any
    options: tuple[str, ...] = ()


# The turn-taking thresholds. Each number is a measured one, and the comment on
# the group says what it was measured against - a threshold without its
# measurement is a guess that later readers will treat as a decision.
#
# Write them as environment variables, not as code. Two hosts running the same
# version with different microphones, rooms or accents need different numbers,
# and the difference between a conversation that works and one that talks over
# people is usually one of these values, not a code change.
DIALS: tuple[Dial, ...] = (
    # What the recogniser is sent and how long it may take.
    Dial(ENV_PREFIX + "ASR_SAMPLE_RATE", "sample_rate", "int", 16000),
    # "auto" rather than a fixed language: the recogniser can usually work it out,
    # and a wrong fixed language is worse than none - it transcribes confidently
    # into the wrong language instead of reporting that it is unsure.
    Dial(ENV_PREFIX + "ASR_LANG", "lang", "str", "auto"),
    Dial(ENV_PREFIX + "ASR_INCREMENTAL_MS", "incremental_ms", "int", 700),
    # Silence alone cannot answer "has this person finished talking": a speaker
    # pausing mid-sentence is normal, and a recogniser handed a pause answers
    # anyway. So the pipeline measures how much actual speech it heard.
    Dial(
        ENV_PREFIX + "VAD_ENGINE",
        "vad_engine",
        "str",
        "silero",
        ("silero", "energy"),
    ),
    Dial(ENV_PREFIX + "SMART_TURN", "smart_turn", "bool", True),
    # The fallback: quiet for this long ends the turn regardless of what the
    # endpointing model thinks. 600 ms of typing, 700 ms inside a call, where a
    # pause in the middle of a thought is shorter.
    Dial(ENV_PREFIX + "VAD_END_MS", "vad_end_ms", "int", 600),
    Dial(ENV_PREFIX + "VAD_END_CALL_MS", "vad_end_call_ms", "int", 700),
    # Shorter than this is not a sentence, and sending it is not free: a table
    # knock of a few tens of milliseconds comes back as a hallucinated word.
    Dial(ENV_PREFIX + "MIN_SPEECH_MS", "min_speech_ms", "int", 300),
    # After deciding "not finished yet", wait at least this long before giving up
    # and ending the turn anyway. Ending a turn early is the better mistake: a
    # wrong "not finished" leaves the speaker talking to something that looks
    # broken, while a wrong "finished" is a reply they can simply talk over.
    Dial(ENV_PREFIX + "REOPEN_MS", "reopen_ms", "int", 800),
    # Start recognising at this silence, before the turn has ended, so the text is
    # already on its way when the turn does end. Must stay below the end point.
    Dial(ENV_PREFIX + "SPECULATE_MS", "speculate_ms", "int", 300),
    # Barge-in: how loud, and for how long, speech has to be before it counts as
    # the listener interrupting. The test is max(floor, echo * ratio) sustained
    # for the given time - an absolute floor so keyboard and breathing never
    # reach it, and a ratio so playback coming back through the microphone does
    # not either. Learned from experience: with the ratio too low, a speaker on
    # loudspeakers interrupts itself halfway through every reply.
    Dial(ENV_PREFIX + "BARGE_MS", "barge_ms", "int", 700),
    Dial(ENV_PREFIX + "BARGE_FLOOR", "barge_floor", "float", 0.10),
    Dial(ENV_PREFIX + "BARGE_RATIO", "barge_ratio", "float", 3.5),
    # Synthesis chunking: how many characters are buffered before a request goes
    # out. One sentence per request gives audible seams between sentences, since
    # each request starts its intonation from scratch; waiting for more costs
    # first-sound latency. The first chunk has its own, much smaller threshold -
    # listeners judge speed almost entirely on the first sound - and a call, where
    # a turn is usually one or two sentences, gets a smaller one again.
    Dial(ENV_PREFIX + "TTS_FIRST_CHARS", "tts_first_chars", "int", 7),
    Dial(ENV_PREFIX + "TTS_FIRST_MIN", "tts_first_min", "int", 5),
    Dial(ENV_PREFIX + "TTS_CHUNK_CHARS", "tts_chunk_chars", "int", 36),
    Dial(ENV_PREFIX + "TTS_CHUNK_MIN", "tts_chunk_min", "int", 16),
    Dial(ENV_PREFIX + "TTS_FIRST_CALL_CHARS", "tts_first_call_chars", "int", 5),
    Dial(ENV_PREFIX + "TTS_FIRST_CALL_MIN", "tts_first_call_min", "int", 4),
    # How many synthesis requests may be in flight for the whole process. It is
    # sized for the provider's tolerance of concurrency, not for the number of
    # people talking: a pool per turn would put fifteen hundred threads on the
    # machine at five hundred simultaneous calls, and the time everybody spends
    # waiting for a free core is time they spend not hearing anything. Read when
    # the pool is built, which is once per process.
    Dial(ENV_PREFIX + "TTS_POOL_SIZE", "tts_pool_size", "int", 32),
    # How long a quiet gap reopens the context given to the model. Within it, the
    # conversation continues; past it, the model starts fresh and the tokens are
    # saved. It affects nothing else: history, transcripts and everything stored
    # are untouched by it, and there is exactly one such clock in the system.
    Dial(ENV_PREFIX + "IDLE_SPLIT_SEC", "idle_split_sec", "int", 600),
)


def dial_env(key: str) -> str:
    """The environment variable behind one dial. Unknown keys raise KeyError."""
    for dial in DIALS:
        if dial.key == key:
            return dial.env
    raise KeyError(key)


def dial_typed(kind: str, text: str, default: Any, name: str = "") -> Any:
    """Turn the text of one dial into a value, falling back to ``default``.

    The fallback is the whole point: a config file is edited by hand and a typo
    in it must not take the process down. It must also not be read as something
    else - an unreadable "barge ratio" of ``3,5`` is the default ratio, never
    zero, which would make every sound from the microphone an interruption.

    ``name`` is the environment variable the text came from, when there is one.
    With it, an unreadable value gets one line in the log; without it (a caller
    passing a literal, as the demo page does when it prints the shipped values)
    nothing is reported, because nothing was misconfigured.
    """
    text = str(text).strip()
    if kind == "int":
        try:
            return int(text)
        except ValueError:
            if name:
                _env_fallback(name, text, default, "an integer")
            return int(default)
    if kind == "float":
        try:
            return float(text)
        except ValueError:
            if name:
                _env_fallback(name, text, default, "a number")
            return float(default)
    if kind == "bool":
        return text.lower() not in FALSE_VALUES
    value = text.lower()
    return value or str(default)


def dials() -> dict[str, Any]:
    """Every dial's current value, read from the environment now.

    A function rather than a constant, so that a configuration change is visible
    to the next request instead of needing a restart.
    """
    out: dict[str, Any] = {}
    for dial in DIALS:
        text = env_str(dial.env, str(dial.default))
        value = dial_typed(dial.kind, text, dial.default, dial.env)
        if dial.options and value not in dial.options:
            # An engine name that is not one of the engines would otherwise be
            # carried all the way to the code that builds one, and fail there.
            warn_once(
                dial.env,
                "%s=%r is not one of %s, so this setting runs on its default %s",
                dial.env,
                text,
                ", ".join(dial.options),
                dial.default,
            )
            out[dial.key] = dial.default
            continue
        out[dial.key] = value
    return out


def model_dir() -> Path:
    """The directory the optional model files are looked for in.

    Relative to the working directory by default, and expanded when it is not:
    a path written as ``~/.cache/echoturn`` in a config file has to mean the same
    thing to the script that downloads a model and to the process that loads it.
    """
    return Path(env_str(ENV_PREFIX + "MODEL_DIR", DEFAULT_MODEL_DIR)).expanduser()
