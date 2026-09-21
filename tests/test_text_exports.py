import echoturn.text as text


def test_the_documented_names_are_exported():
    expected = {
        "ChunkPolicy",
        "SpeechStyle",
        "TEXT_STYLE",
        "VOICE_STYLE",
        "clean_reply",
        "get_style",
        "has_reasoning",
        "is_message_sep",
        "is_speakable",
        "iter_message_sentences",
        "iter_sentences",
        "normalize_speech",
        "prepare_for_tts",
        "shape_messages",
        "split_messages",
        "strip_reasoning",
        "strip_stage_directions",
    }
    assert expected <= set(text.__all__)
    for name in expected:
        assert hasattr(text, name), name
