import io

import pytest

from echoturn import models

SILERO = models.by_name("silero_vad.onnx")
TURN = models.by_name("smart-turn-v3.2-cpu.onnx")


@pytest.fixture(autouse=True)
def model_home(monkeypatch, tmp_path):
    """Point the model directory at a temporary one for every test here."""
    monkeypatch.setenv("ECHOTURN_MODEL_DIR", str(tmp_path))
    return tmp_path


def serving(body, calls=None):
    """A stand-in for the download that answers with the given bytes."""

    def opener(request, timeout=None):
        if calls is not None:
            calls.append(request.full_url)
        return io.BytesIO(body)

    return opener


def test_the_directory_is_read_from_the_settings(model_home):
    assert models.path_of(SILERO) == model_home / "silero_vad.onnx"
    assert models.path_of("silero_vad.onnx") == model_home / "silero_vad.onnx"


def test_an_unknown_name_raises_like_a_typo_should():
    with pytest.raises(KeyError):
        models.by_name("not-a-model.onnx")


def test_installed_means_the_right_number_of_bytes(model_home):
    target = model_home / SILERO.name
    target.write_bytes(b"\0" * (SILERO.size - 1))
    assert models.installed(SILERO) is False
    target.write_bytes(b"\0" * SILERO.size)
    assert models.installed(SILERO) is True


def test_status_tells_absent_from_truncated(model_home):
    (model_home / SILERO.name).write_bytes(b"half")
    rows = {row["name"]: row for row in models.status()}
    assert rows[SILERO.name]["actual"] == 4
    assert rows[SILERO.name]["ok"] is False
    assert rows[TURN.name]["actual"] is None
    assert len(rows) == len(models.MODELS)


def test_a_complete_transfer_takes_its_real_name(monkeypatch, model_home):
    monkeypatch.setattr(
        models.urllib.request, "urlopen", serving(b"\0" * SILERO.size)
    )
    assert models.download(SILERO) is True
    assert (model_home / SILERO.name).stat().st_size == SILERO.size
    assert not (model_home / (SILERO.name + ".part")).exists()


def test_a_short_transfer_leaves_nothing_behind(monkeypatch, model_home):
    monkeypatch.setattr(models.urllib.request, "urlopen", serving(b"\0" * 10))
    assert models.download(SILERO) is False
    assert not (model_home / SILERO.name).exists()
    assert not (model_home / (SILERO.name + ".part")).exists()


def test_a_broken_transfer_is_reported_not_raised(monkeypatch, model_home):
    def opener(_request, timeout=None):
        raise OSError("the network is gone")

    monkeypatch.setattr(models.urllib.request, "urlopen", opener)
    assert models.download(SILERO) is False
    assert not (model_home / SILERO.name).exists()


def test_an_installed_model_is_not_downloaded_again(monkeypatch, model_home):
    (model_home / SILERO.name).write_bytes(b"\0" * SILERO.size)
    calls = []
    monkeypatch.setattr(
        models.urllib.request, "urlopen", serving(b"", calls)
    )
    assert models.download(SILERO) is True
    assert calls == []


def test_force_downloads_what_is_already_there(monkeypatch, model_home):
    (model_home / SILERO.name).write_bytes(b"old")
    calls = []
    monkeypatch.setattr(
        models.urllib.request,
        "urlopen",
        serving(b"\0" * SILERO.size, calls),
    )
    assert models.download(SILERO, force=True) is True
    assert len(calls) == 1
    assert (model_home / SILERO.name).stat().st_size == SILERO.size


def test_fetching_names_what_is_still_missing(monkeypatch, model_home):
    monkeypatch.setattr(
        models.urllib.request, "urlopen", serving(b"\0" * SILERO.size)
    )
    assert models.fetch_all() == [TURN.name]


def test_the_check_does_not_download_and_reports_what_is_missing(model_home):
    assert models.main(["--check"]) == 1
    assert not (model_home / SILERO.name).exists()


def test_a_failed_download_exits_non_zero(monkeypatch, model_home, capsys):
    monkeypatch.setattr(models.urllib.request, "urlopen", serving(b"\0" * 3))
    assert models.main([]) == 1
    assert "still missing" in capsys.readouterr().out
