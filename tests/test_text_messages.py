from echoturn.text.messages import shape_messages, split_messages


def test_a_dash_line_splits_messages():
    assert split_messages("一\n---\n二") == ["一", "二"]


def test_a_blank_line_splits_messages():
    assert split_messages("一\n\n二") == ["一", "二"]


def test_a_stray_dash_run_inside_a_line_is_removed():
    assert split_messages("等一下---我马上来") == ["等一下我马上来"]


def test_empty_parts_are_dropped():
    assert split_messages("\n\n---\n\n一\n\n") == ["一"]


def test_stage_directions_are_removed_per_message():
    assert split_messages("一（点头）\n\n二") == ["一", "二"]


def test_shaping_merges_when_there_are_too_many_messages():
    out = shape_messages("aaa\n\nbbbbb\n\ncc", 2)
    assert out == ["aaa", "bbbbb\ncc"]


def test_shaping_merges_neighbours_and_keeps_the_order():
    out = shape_messages("一\n\n二\n\n三", 2)
    assert out == ["一\n二", "三"]


def test_shaping_never_splits_to_reach_a_target():
    """Half a sentence sent on its own is still filler."""
    assert shape_messages("只说一句。", 4) == ["只说一句。"]


def test_shaping_with_zero_is_treated_as_one():
    assert len(shape_messages("一\n\n二", 0)) == 1


def test_shaping_empty_text_gives_no_messages():
    assert shape_messages("", 3) == []
