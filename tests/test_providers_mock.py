import math
import struct

from echoturn.audio.pitch import measure_f0
from echoturn.audio.wav import WavInfo, read_wav, wav_seconds
from echoturn.providers.mock import SAMPLE_RATE, MockASR, MockLLM, MockTTS


def tone_of(wav: bytes) -> float:
    """Peak frequency of a mock clip, read back through the pitch estimator."""
    return measure_f0(read_wav(wav).pcm, SAMPLE_RATE)


def test_the_mock_voice_is_a_wav_at_the_rate_speech_models_expect():
    info = read_wav(MockTTS().synth("hello there"))
    assert info is not None
    assert (info.sample_rate, info.channels, info.bits) == (SAMPLE_RATE, 1, 16)


def test_the_clip_length_follows_the_text():
    client = MockTTS()
    short = wav_seconds(client.synth("hi"))
    long = wav_seconds(client.synth("hi" * 20))
    assert short < long


def test_a_tiny_reply_is_still_audible_and_a_huge_one_is_capped():
    client = MockTTS()
    assert wav_seconds(client.synth("")) == 0.9
    assert wav_seconds(client.synth("x" * 10000)) == 6.0


def test_the_same_text_twice_gives_the_same_audio():
    """Reproducibility is what makes an event-stream test worth writing."""
    assert MockTTS().synth("hello", emotion="calm") == MockTTS().synth(
        "hello", emotion="calm"
    )


def test_the_emotion_tag_changes_what_the_beep_sounds_like():
    client = MockTTS()
    low = tone_of(client.synth("same words here", emotion="sad"))
    high = tone_of(client.synth("same words here", emotion="flustered"))
    assert high > low * 1.5


def test_an_emotion_the_mock_does_not_know_still_speaks():
    assert tone_of(MockTTS().synth("hello", emotion="unheard-of")) > 0
    assert tone_of(MockTTS().synth("hello")) > 0


def test_the_voice_starts_and_ends_quietly():
    """A clip that starts at full level clicks in the speaker."""
    pcm = read_wav(MockTTS().synth("a sentence of some length")).pcm
    first = abs(struct.unpack("<h", pcm[:2])[0])
    peak = max(abs(value) for value in struct.unpack(f"<{len(pcm) // 2}h", pcm))
    assert first < peak * 0.1


def test_the_transcript_says_it_is_a_mock():
    wav = MockTTS().synth("whatever")
    text = MockASR().transcribe(wav, sample_rate=SAMPLE_RATE, fmt="wav", lang="auto")
    assert "mock" in text.lower()


def test_the_transcript_describes_the_audio_it_was_given():
    """One fixed string would travel the whole pipeline looking like success."""
    client = MockTTS()
    short = MockASR().transcribe(client.synth("hi"))
    long = MockASR().transcribe(client.synth("hi " * 40))
    assert short != long


def test_a_transcript_of_nothing_is_still_a_reported_length():
    assert MockASR().transcribe(b"", sample_rate=SAMPLE_RATE, fmt="wav", lang="auto")


def test_the_mock_model_answers_the_last_user_message():
    reply = "".join(
        MockLLM().stream(
            [
                {"role": "system", "content": "be brief"},
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "older reply"},
                {"role": "user", "content": "second"},
            ]
        )
    )
    assert "second" in reply
    assert "first" not in reply


def test_the_mock_model_streams_in_more_than_one_piece():
    pieces = list(MockLLM().stream([{"role": "user", "content": "a longer question"}]))
    assert len(pieces) > 1
    assert "".join(pieces) == "[mock reply] a longer question"


def test_the_mock_model_answers_an_empty_prompt():
    assert "".join(MockLLM().stream([])).strip()


def test_the_mock_voice_does_not_clip():
    pcm = read_wav(MockTTS().synth("x" * 200)).pcm
    values = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    assert max(values) < 32767
    assert min(values) > -32768
    assert math.isfinite(float(sum(values)))


def test_the_mock_voice_is_a_pcm_wav_and_not_something_else():
    info = read_wav(MockTTS().synth("hello"))
    assert isinstance(info, WavInfo)
