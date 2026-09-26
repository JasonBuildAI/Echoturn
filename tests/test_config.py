import logging

import pytest

from echoturn import config


@pytest.fixture
def warnings(monkeypatch, caplog):
    """Capture the config log, with the once-per-name set started empty.

    That set is process-wide on purpose - a value read per request must not print
    a line per request - so a test that wants to see a line has to be the first
    to ask for that name.
    """
    monkeypatch.setattr(config, "_warned", set())
    caplog.set_level(logging.WARNING, logger="echoturn.config")
    return caplog


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
    assert values["speculate_call_ms"] == 180
    assert values["barge_ms"] == 700
    assert values["barge_floor"] == 0.10
    assert values["barge_ratio"] == 3.5
    assert values["tts_first_chars"] == 7
    assert values["tts_chunk_chars"] == 36
    assert values["tts_first_call_chars"] == 3
    assert values["tts_first_call_min"] == 2


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


def test_a_value_that_cannot_be_read_says_so_once(monkeypatch, warnings):
    """The fallback stays - the process must not die on a typo - but not silently.

    A setting that looks changed while the process runs the old number has no
    symptom except behaviour, which is the most expensive thing to debug there is.
    One line, naming the variable, the value and the default it used.
    """
    monkeypatch.setenv("ECHOTURN_TEST_INT", "twelve")
    monkeypatch.setenv("ECHOTURN_TEST_FLOAT", "3,5")
    assert config.env_int("ECHOTURN_TEST_INT", 12) == 12
    assert config.env_int("ECHOTURN_TEST_INT", 12) == 12
    assert config.env_float("ECHOTURN_TEST_FLOAT", 3.5) == 3.5
    said = [record.getMessage() for record in warnings.records]
    assert len(said) == 2, said
    assert "ECHOTURN_TEST_INT" in said[0] and "twelve" in said[0]
    assert "12" in said[0], "the default it ran on has to be in the line"
    assert "ECHOTURN_TEST_FLOAT" in said[1] and "3,5" in said[1]


def test_a_value_that_can_be_read_says_nothing(monkeypatch, warnings):
    """The positive control: a line for a good value is noise, and noise is not read."""
    monkeypatch.setenv("ECHOTURN_TEST_INT", "9")
    monkeypatch.setenv("ECHOTURN_TEST_FLOAT", "0.25")
    assert config.env_int("ECHOTURN_TEST_INT", 12) == 9
    assert config.env_float("ECHOTURN_TEST_FLOAT", 3.5) == 0.25
    assert warnings.records == []


def test_a_blank_value_is_unset_and_not_a_mistake(monkeypatch, warnings):
    """``KEY=`` means "leave the default alone", so it is not worth a log line."""
    monkeypatch.setenv("ECHOTURN_TEST_INT", "  ")
    assert config.env_int("ECHOTURN_TEST_INT", 12) == 12
    assert warnings.records == []


def test_a_dial_that_cannot_be_read_names_its_variable(monkeypatch, warnings):
    monkeypatch.setenv("ECHOTURN_BARGE_RATIO", "2，4")
    assert config.dials()["barge_ratio"] == 3.5
    assert config.dials()["barge_ratio"] == 3.5
    said = [record.getMessage() for record in warnings.records]
    assert len(said) == 1, said
    assert "ECHOTURN_BARGE_RATIO" in said[0]


def test_an_engine_name_outside_the_list_names_itself(monkeypatch, warnings):
    """A name that is not one of the engines fails in the code that builds one."""
    monkeypatch.setenv("ECHOTURN_VAD_ENGINE", "enery")
    assert config.dials()["vad_engine"] == "silero"
    said = [record.getMessage() for record in warnings.records]
    assert len(said) == 1, said
    assert "ECHOTURN_VAD_ENGINE" in said[0] and "enery" in said[0]


def test_a_literal_that_is_not_a_setting_is_not_reported(warnings):
    """The demo page reads dials with literal text, and must not fill the log."""
    assert config.dial_typed("int", "six", 600) == 600
    assert config.dial_typed("float", "3,5", 3.5) == 3.5
    assert config.dial_typed("int", "600", 1, "ECHOTURN_X") == 600
    assert warnings.records == []


def test_the_model_directory_is_a_setting_and_expands_a_home_path(monkeypatch):
    monkeypatch.delenv("ECHOTURN_MODEL_DIR", raising=False)
    assert str(config.model_dir()) == config.DEFAULT_MODEL_DIR
    monkeypatch.setenv("ECHOTURN_MODEL_DIR", "~/.cache/echoturn")
    assert "~" not in str(config.model_dir())
