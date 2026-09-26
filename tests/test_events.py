import base64
import json

from echoturn import events


def test_every_builder_uses_a_name_from_the_contract():
    built = [
        events.ack("m1"),
        events.sentence(0, "hello"),
        events.audio(0, 0, b"wav"),
        events.sink(),
        events.aborted("superseded"),
        events.done("hello"),
        events.error("it broke"),
    ]
    assert [event["type"] for event in built] == list(events.EVENT_TYPES)


def test_audio_carries_its_ordering_key_and_its_message():
    event = events.audio(3, 1, b"RIFF....")
    assert event["idx"] == 3
    assert event["i"] == 1
    assert event["mime"] == "audio/wav"
    assert base64.b64decode(event["data"]) == b"RIFF...."


def test_a_string_is_never_mistaken_for_the_numbered_form():
    """A JSON round trip must not turn an index into a string."""
    event = events.audio(2, 0, b"x")
    assert json.loads(json.dumps(event))["idx"] == 2


def test_done_always_has_a_place_for_timings_and_warnings():
    event = events.done("hello")
    assert event["timings"] == {}
    assert event["warnings"] == []
    assert event["unspoken"] == []
    assert "extra" not in event


def test_done_keeps_host_fields_out_of_the_contract():
    event = events.done("hello", extra={"topic": 3})
    assert event["extra"] == {"topic": 3}
    assert set(event) == {"type", "reply", "timings", "warnings", "unspoken", "extra"}


def test_unspoken_messages_are_indices_even_when_they_arrive_as_strings():
    """The list is read as message indices, so a round trip must not break it."""
    event = events.done("hello", unspoken=["0", 2])
    assert event["unspoken"] == [0, 2]


def test_three_endings_are_terminal_and_nothing_else_is():
    assert set(events.TERMINAL) == {"aborted", "done", "error"}
    for name in events.EVENT_TYPES:
        assert (name in events.TERMINAL) == (name in ("aborted", "done", "error"))


def test_the_reason_this_package_emits_is_named_once():
    assert events.aborted(events.SUPERSEDED)["reason"] == "superseded"


def test_encoding_is_one_sse_frame():
    assert events.encode(events.sentence(0, "hi")) == (
        'data: {"type": "sentence", "i": 0, "text": "hi"}\n\n'
    )


def test_encoding_leaves_text_readable():
    """No escapes for non-ASCII: it is UTF-8 all the way to the browser."""
    frame = events.encode(events.sentence(0, "你好"))
    assert "你好" in frame
    assert "\\u" not in frame


def test_the_stream_encodes_in_order():
    frames = list(
        events.iter_encoded([events.ack("m1"), events.error("nope")])
    )
    assert frames[0].startswith('data: {"type": "ack"')
    assert frames[1].endswith("\n\n")
