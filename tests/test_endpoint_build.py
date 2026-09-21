from echoturn.endpoint import SmartTurn, Turn, build_turn


def test_the_model_is_used_when_its_file_is_there(tmp_path):
    model = tmp_path / "smart-turn-v3.2-cpu.onnx"
    model.write_bytes(b"not really a model")
    chosen = build_turn(model_path=str(model))
    assert isinstance(chosen.judge, SmartTurn)
    assert chosen.engine == "smart-turn"
    assert chosen.fallback is False
    assert chosen.reason == ""
    assert chosen.ready() is True


def test_a_missing_file_falls_back_and_says_so(tmp_path):
    chosen = build_turn(model_path=str(tmp_path / "nowhere.onnx"))
    assert chosen.judge is None
    assert chosen.engine == "none"
    assert chosen.fallback is True
    assert "no endpoint model" in chosen.reason


def test_switching_the_model_off_is_not_reported_as_a_fallback(tmp_path):
    chosen = build_turn(False, model_path=str(tmp_path / "nowhere.onnx"))
    assert chosen.judge is None
    assert chosen.engine == "none"
    assert chosen.fallback is False
    assert chosen.reason == ""
    assert chosen.ready() is False


def test_the_switch_comes_from_the_settings_when_it_is_not_named(monkeypatch, tmp_path):
    monkeypatch.setenv("ECHOTURN_SMART_TURN", "off")
    assert build_turn(model_path=str(tmp_path / "nowhere.onnx")).fallback is False


def test_no_judge_means_no_verdict_rather_than_an_exception(tmp_path):
    assert build_turn(False).verdict([0.0] * 100) is None


def test_a_judge_that_breaks_says_nothing_instead_of_raising():
    class Broken:
        def judge(self, _samples):
            raise RuntimeError("no idea")

    assert Turn("smart-turn", False, "", Broken()).verdict([]) is None


def test_a_working_judge_reports_its_verdict_through(tmp_path):
    class Fixed:
        def judge(self, _samples):
            return {"complete": True, "prob": 0.9}

    assert Turn("smart-turn", False, "", Fixed()).verdict([])["complete"] is True
