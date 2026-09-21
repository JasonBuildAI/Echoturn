
from echoturn.store import (
    KEEP_MESSAGES,
    WINDOW_MESSAGES,
    InMemoryStore,
    TranscriptStore,
)


class Clock:
    """A clock a test can move by hand."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def store(**kwargs) -> InMemoryStore:
    clock = kwargs.pop("clock", None) or Clock()
    return InMemoryStore(clock=clock, **kwargs)


def test_an_unknown_conversation_has_an_empty_window():
    assert store().window("nobody") == []


def test_messages_come_back_in_the_order_they_were_added():
    held = store()
    held.append("k", "user", "hello")
    held.append("k", "assistant", "hi")
    assert held.window("k") == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_conversations_do_not_see_each_other():
    held = store()
    held.append("a", "user", "from a")
    held.append("b", "user", "from b")
    assert held.window("a") == [{"role": "user", "content": "from a"}]
    assert held.window("b") == [{"role": "user", "content": "from b"}]


def test_the_window_is_capped_at_the_window_size():
    held = store(window=4, keep=8)
    for index in range(10):
        held.append("k", "user", str(index))
    assert [m["content"] for m in held.window("k")] == ["6", "7", "8", "9"]


def test_what_is_kept_is_bounded_too():
    held = store(window=2, keep=5)
    for index in range(20):
        held.append("k", "user", str(index))
    assert held.window("k") == [
        {"role": "user", "content": "18"},
        {"role": "user", "content": "19"},
    ]
    assert held.keys() == ["k"]


def test_a_long_quiet_gap_reopens_the_window():
    clock = Clock()
    held = store(idle_sec=600, clock=clock)
    held.append("k", "user", "are you there")
    clock.advance(601)
    assert held.window("k") == []


def test_a_short_gap_leaves_the_window_alone():
    clock = Clock()
    held = store(idle_sec=600, clock=clock)
    held.append("k", "user", "are you there")
    clock.advance(599)
    assert held.window("k") == [{"role": "user", "content": "are you there"}]


def test_reading_the_window_counts_as_activity():
    """A screen somebody is looking at is not an abandoned one."""
    clock = Clock()
    held = store(idle_sec=600, clock=clock)
    held.append("k", "user", "hello")
    for _ in range(5):
        clock.advance(500)
        assert held.window("k") == [{"role": "user", "content": "hello"}]


def test_speaking_again_after_a_gap_starts_a_fresh_window():
    clock = Clock()
    held = store(idle_sec=600, clock=clock)
    held.append("k", "user", "hello")
    clock.advance(601)
    held.append("k", "user", "hello again")
    assert held.window("k") == [{"role": "user", "content": "hello again"}]


def test_the_gap_comes_from_the_settings_by_default(monkeypatch):
    clock = Clock()
    held = store(clock=clock)
    held.append("k", "user", "hello")
    monkeypatch.setenv("ECHOTURN_IDLE_SPLIT_SEC", "10")
    clock.advance(11)
    assert held.window("k") == []


def test_a_window_handed_out_cannot_be_used_to_change_the_stored_one():
    held = store()
    held.append("k", "user", "hello")
    handed = held.window("k")
    handed[0]["content"] = "something else"
    handed.append({"role": "user", "content": "extra"})
    assert held.window("k") == [{"role": "user", "content": "hello"}]


def test_clearing_forgets_one_conversation_and_no_other():
    held = store()
    held.append("a", "user", "one")
    held.append("b", "user", "two")
    held.clear("a")
    assert held.window("a") == []
    assert held.keys() == ["b"]
    assert held.window("b") == [{"role": "user", "content": "two"}]


def test_the_reference_store_satisfies_the_protocol():
    assert isinstance(store(), TranscriptStore)


def test_the_shipped_sizes_keep_more_than_they_send():
    assert WINDOW_MESSAGES < KEEP_MESSAGES


def test_a_keep_smaller_than_the_window_is_raised_to_the_window():
    """Otherwise the window would promise more than the store retains."""
    held = store(window=8, keep=2)
    assert held.keep == 8


def test_an_unknown_role_is_stored_as_it_was_given():
    held = store()
    held.append("k", "tool", "result")
    assert held.window("k") == [{"role": "tool", "content": "result"}]


def test_nothing_is_stored_for_a_key_that_was_only_read():
    held = store()
    assert held.window("k") == []
    assert held.keys() == []


def test_a_window_size_of_zero_still_sends_the_last_message():
    """A window of nothing would send a prompt with no context at all."""
    held = store(window=0)
    for index in range(3):
        held.append("k", "user", str(index))
    assert len(held.window("k")) == 1
