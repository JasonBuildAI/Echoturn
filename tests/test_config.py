import pytest

from echoturn import config


def test_a_missing_variable_reads_as_the_default():
    assert config.env_str("ECHOTURN_TEST_MISSING", "fallback") == "fallback"


def test_a_blank_variable_counts_as_unset(monkeypatch):
    """A config file writes `KEY=` to mean "leave the default alone"."""
    monkeypatch.setenv("ECHOTURN_TEST_BLANK", "   ")
    assert config.env_str("ECHOTURN_TEST_BLANK", "fallback") == "fallback"


def test_surrounding_whitespace_is_not_part_of_the_value(monkeypatch):
    monkeypatch.setenv("ECHOTURN_TEST_SPACED", " value ")
    assert config.env_str("ECHOTURN_TEST_SPACED", "fallback") == "value"


def test_a_number_that_cannot_be_read_falls_back(monkeypatch):
    monkeypatch.setenv("ECHOTURN_TEST_INT", "twelve")
    assert config.env_int("ECHOTURN_TEST_INT", 12) == 12
    monkeypatch.setenv("ECHOTURN_TEST_FLOAT", "")
    assert config.env_float("ECHOTURN_TEST_FLOAT", 0.5) == 0.5


def test_numbers_that_can_be_read_are_read(monkeypatch):
    monkeypatch.setenv("ECHOTURN_TEST_INT", "7")
    monkeypatch.setenv("ECHOTURN_TEST_FLOAT", "3.5")
    assert config.env_int("ECHOTURN_TEST_INT", 12) == 7
    assert config.env_float("ECHOTURN_TEST_FLOAT", 0.5) == 3.5


@pytest.mark.parametrize("text", ["0", "off", "no", "false", "OFF", "No"])
def test_the_spellings_of_off_are_all_off(monkeypatch, text):
    monkeypatch.setenv("ECHOTURN_TEST_FLAG", text)
    assert config.env_bool("ECHOTURN_TEST_FLAG", True) is False


@pytest.mark.parametrize("text", ["1", "on", "yes", "true", "anything else"])
def test_anything_that_is_not_off_is_on(monkeypatch, text):
    monkeypatch.setenv("ECHOTURN_TEST_FLAG", text)
    assert config.env_bool("ECHOTURN_TEST_FLAG", False) is True


def test_an_unset_flag_keeps_the_default():
    assert config.env_bool("ECHOTURN_TEST_MISSING_FLAG", True) is True
    assert config.env_bool("ECHOTURN_TEST_MISSING_FLAG", False) is False


def test_dial_typing_reads_each_kind():
    assert config.dial_typed("int", "600", 1) == 600
    assert config.dial_typed("float", "0.10", 1.0) == 0.10
    assert config.dial_typed("bool", "yes", False) is True
    assert config.dial_typed("str", "energy", "silero") == "energy"


def test_dial_typing_falls_back_rather_than_guessing():
    """An unreadable ratio must not become zero: zero makes every sound a barge-in."""
    assert config.dial_typed("int", "six", 600) == 600
    assert config.dial_typed("float", "3,5", 3.5) == 3.5
    assert config.dial_typed("str", "", "auto") == "auto"
    assert config.dial_typed("str", "   ", "auto") == "auto"


def test_every_dial_names_its_variable_under_our_prefix():
    for dial in config.DIALS:
        assert dial.env.startswith(config.ENV_PREFIX)
        assert dial.key == dial.key.lower()


def test_dial_keys_and_variables_are_unique():
    keys = [dial.key for dial in config.DIALS]
    envs = [dial.env for dial in config.DIALS]
    assert len(set(keys)) == len(keys)
    assert len(set(envs)) == len(envs)


def test_dial_env_finds_the_variable_and_refuses_an_unknown_key():
    assert config.dial_env("vad_end_ms") == "ECHOTURN_VAD_END_MS"
    with pytest.raises(KeyError):
        config.dial_env("not_a_dial")


def test_the_shipped_thresholds_are_the_measured_ones():
    """These numbers were measured: changing one changes how talking works."""
    values = config.dials()
    assert values["vad_end_ms"] == 600
    assert values["vad_end_call_ms"] == 700
    assert values["min_speech_ms"] == 300
    assert values["reopen_ms"] == 800
    assert values["speculate_ms"] == 300
    assert values["barge_ms"] == 700
    assert values["barge_floor"] == 0.10
    assert values["barge_ratio"] == 3.5
    assert values["tts_first_chars"] == 7
    assert values["tts_chunk_chars"] == 36


def test_the_language_default_lets_the_recogniser_decide():
    assert config.dials()["lang"] == "auto"


def test_the_dials_follow_the_environment(monkeypatch):
    """Read now, not at import: a changed setting must not need a restart."""
    monkeypatch.setenv("ECHOTURN_VAD_END_MS", "450")
    assert config.dials()["vad_end_ms"] == 450


def test_a_value_outside_the_allowed_set_falls_back(monkeypatch):
    monkeypatch.setenv("ECHOTURN_VAD_ENGINE", "enery")
    assert config.dials()["vad_engine"] == "silero"
    monkeypatch.setenv("ECHOTURN_VAD_ENGINE", "ENERGY")
    assert config.dials()["vad_engine"] == "energy"


def test_the_model_directory_is_a_setting_and_expands_a_home_path(monkeypatch):
    monkeypatch.delenv("ECHOTURN_MODEL_DIR", raising=False)
    assert str(config.model_dir()) == config.DEFAULT_MODEL_DIR
    monkeypatch.setenv("ECHOTURN_MODEL_DIR", "~/.cache/echoturn")
    assert "~" not in str(config.model_dir())
