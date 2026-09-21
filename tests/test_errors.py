from echoturn.errors import EchoturnError, MissingDependencyError, ProviderError


def test_a_missing_extra_names_the_extra_and_what_it_provides():
    error = MissingDependencyError("pitch and speed processing", "dsp", "numpy")
    message = str(error)
    assert "pitch and speed processing" in message
    assert "echoturn[dsp]" in message
    assert "numpy" in message
    assert (error.feature, error.extra, error.packages) == (
        "pitch and speed processing",
        "dsp",
        "numpy",
    )


def test_a_missing_extra_is_one_of_ours():
    assert issubclass(MissingDependencyError, EchoturnError)
    assert issubclass(ProviderError, EchoturnError)


def test_a_provider_failure_separates_what_a_user_may_see_from_what_a_log_gets():
    error = ProviderError("speech synthesis failed", detail="<html>502</html>")
    assert str(error) == "speech synthesis failed"
    assert error.message == "speech synthesis failed"
    assert error.detail == "<html>502</html>"


def test_a_provider_failure_without_detail_falls_back_to_the_message():
    assert ProviderError("speech synthesis failed").detail == "speech synthesis failed"
