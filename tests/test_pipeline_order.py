from echoturn.pipeline import _AudioOrder


def collector():
    """An ordering queue whose sink records what it was handed."""
    out: list[tuple[int, bytes]] = []
    return out, _AudioOrder(lambda idx, data: out.append((idx, data)))


def test_audio_comes_out_in_chunk_order_not_arrival_order():
    out, order = collector()
    order.piece(1, b"second")
    order.finish(1)
    order.piece(0, b"first")
    order.finish(0)
    assert out == [(0, b"first"), (1, b"second")]


def test_nothing_is_handed_over_before_its_turn():
    out, order = collector()
    order.piece(3, b"later")
    assert out == []


def test_a_chunk_still_streaming_is_not_treated_as_finished():
    """The bug this guards: chunk 0 finishing must not close chunk 1."""
    out, order = collector()
    order.piece(0, b"a1")
    order.piece(1, b"b1")
    order.finish(0)
    order.piece(1, b"b2")
    order.finish(1)
    assert out == [(0, b"a1"), (1, b"b1"), (1, b"b2")]


def test_a_chunk_with_no_audio_still_releases_the_ones_behind_it():
    out, order = collector()
    order.piece(2, b"c")
    order.finish(0)
    order.finish(1)
    order.finish(2)
    assert out == [(2, b"c")]


def test_pieces_of_one_chunk_do_not_overtake_each_other():
    """A piece arriving while the chunk is current still goes out in order."""
    out, order = collector()
    order.piece(1, b"b1")
    order.piece(1, b"b2")
    order.piece(0, b"a")
    order.finish(1)
    order.finish(0)
    assert out == [(0, b"a"), (1, b"b1"), (1, b"b2")]
