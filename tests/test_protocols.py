from echoturn.protocols import ASRClient, LLMClient, TTSClient
from echoturn.providers.base import WholeClipTTS


class ForeignASR:
    """Something a host already owns: no import of ours anywhere in it."""

    def transcribe(self, audio, *, sample_rate, fmt, lang):
        return "hello"


class ForeignTTS(WholeClipTTS):
    def synth(self, text, *, emotion=None, voice=None):
        return b"audio"


class ForeignLLM:
    def stream(self, messages):
        yield "hi"


class NotATranscriber:
    def listen(self, audio):
        return "hello"


def test_a_host_class_satisfies_a_protocol_without_inheriting_anything():
    assert isinstance(ForeignASR(), ASRClient)
    assert isinstance(ForeignLLM(), LLMClient)


def test_a_class_with_the_wrong_method_is_not_a_provider():
    """The check has to be able to fail, or it is decoration."""
    assert not isinstance(NotATranscriber(), ASRClient)
    assert not isinstance(ForeignASR(), LLMClient)


def test_a_whole_clip_provider_still_looks_like_a_streaming_one():
    client = ForeignTTS()
    assert isinstance(client, TTSClient)


def test_the_whole_clip_fallback_hands_the_audio_to_the_callback():
    seen = []
    client = ForeignTTS()
    assert client.synth_stream("hi", chunk_cb=seen.append) is None
    assert seen == [b"audio"]


def test_the_whole_clip_fallback_returns_the_audio_without_a_callback():
    assert ForeignTTS().synth_stream("hi") == b"audio"
