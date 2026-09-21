from echoturn.vad import EnergyVad, SileroVad, Vad, build_vad


def test_the_model_is_the_default_when_it_is_there(monkeypatch, tmp_path):
    model = tmp_path / "silero_vad.onnx"
    model.write_bytes(b"not really a model")
    chosen = build_vad("silero", model_path=str(model))
    assert isinstance(chosen.detector, SileroVad)
    assert chosen.engine == "silero"
    assert chosen.fallback is False
    assert chosen.reason == ""


def test_a_missing_model_falls_back_and_says_so(tmp_path):
    chosen = build_vad("silero", model_path=str(tmp_path / "nowhere.onnx"))
    assert isinstance(chosen.detector, EnergyVad)
    assert chosen.engine == "energy"
    assert chosen.fallback is True
    assert "not at" in chosen.reason


def test_the_level_engine_can_be_asked_for_on_purpose(tmp_path):
    """Choosing it is not a fallback, and the answer must not look like one."""
    chosen = build_vad("energy", model_path=str(tmp_path / "nowhere.onnx"))
    assert isinstance(chosen.detector, EnergyVad)
    assert chosen.fallback is False
    assert chosen.reason == ""


def test_the_engine_comes_from_the_settings_when_it_is_not_named(monkeypatch, tmp_path):
    monkeypatch.setenv("ECHOTURN_VAD_ENGINE", "energy")
    assert build_vad(model_path=str(tmp_path / "nowhere.onnx")).engine == "energy"


def test_an_engine_name_that_is_not_one_of_ours_does_not_stop_the_audio(tmp_path):
    """This runs mid-conversation: a typo in a config file is not a reason to fail."""
    chosen = build_vad("enery", model_path=str(tmp_path / "nowhere.onnx"))
    assert chosen.engine in ("silero", "energy")
    assert chosen.fallback is True


def test_a_chosen_detector_reports_speech_the_same_way(tmp_path):
    chosen = build_vad("energy", model_path=str(tmp_path / "nowhere.onnx"))
    assert chosen.report([0.3] * 16000)["speech_ms"] > 400


def test_a_detector_that_breaks_reports_rather_than_raises():
    class Broken:
        def report(self, _samples):
            raise RuntimeError("no idea")

    assert "no idea" in Vad("energy", False, "", Broken()).report([])["error"]
