from echoturn.pipeline import TurnDeps, TurnInput, TurnRunner
from pipeline_helpers import FakeLLM


def messages_for(turn: TurnInput) -> list[dict]:
    return TurnRunner(turn, TurnDeps(llm=FakeLLM([]))).messages()


def test_the_prompt_is_the_system_line_then_the_window_then_the_message():
    turn = TurnInput(
        "what time is it",
        system_prompt="You are terse.",
        history=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
    )
    assert messages_for(turn) == [
        {"role": "system", "content": "You are terse."},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "what time is it"},
    ]


def test_a_blank_system_line_is_not_sent_at_all():
    """An empty system message is a request the model may refuse."""
    assert messages_for(TurnInput("hello", system_prompt="   ")) == [
        {"role": "user", "content": "hello"}
    ]


def test_the_window_is_copied_rather_than_referenced():
    """The host keeps mutating its window; this turn's prompt must not change."""
    window = [{"role": "user", "content": "hello"}]
    turn = TurnInput("and now", history=window)
    prompt = messages_for(turn)
    window[0]["content"] = "something else entirely"
    assert prompt[0] == {"role": "user", "content": "hello"}


def test_a_quoted_message_is_put_in_front_of_the_reply():
    turn = TurnInput("that one", quote={"role": "assistant", "text": "the first one"})
    assert messages_for(turn)[-1]["content"] == (
        'replying to assistant: "the first one"\nthat one'
    )


def test_a_quote_with_nothing_in_it_is_ignored():
    turn = TurnInput("hello", quote={"role": "assistant", "text": "   "})
    assert messages_for(turn)[-1]["content"] == "hello"


def test_a_history_entry_missing_a_role_is_treated_as_a_user_message():
    turn = TurnInput("hello", history=[{"content": "earlier"}])
    assert messages_for(turn)[0] == {"role": "user", "content": "earlier"}


def test_the_voice_style_is_used_only_when_there_is_a_voice():
    text_only = TurnRunner(TurnInput("hi"), TurnDeps(llm=FakeLLM([])))
    spoken = TurnRunner(TurnInput("hi"), TurnDeps(llm=FakeLLM([]), tts=object()))
    assert text_only.style.name == "text"
    assert spoken.style.name == "voice"
