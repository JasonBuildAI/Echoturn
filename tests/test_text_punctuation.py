from echoturn.text.punctuation import cap_ellipsis, cap_tilde, strip_decorations


def test_ellipsis_budget_of_one_keeps_the_first_run():
    assert cap_ellipsis("……嗯……我看看……", 1) == "……嗯，我看看"


def test_extra_ellipsis_mid_sentence_becomes_a_comma():
    assert cap_ellipsis("我画了……还没画完", 0) == "我画了，还没画完"


def test_extra_ellipsis_at_a_sentence_end_disappears():
    assert cap_ellipsis("不对。……我再改一版", 0) == "不对。我再改一版"


def test_no_dangling_punctuation_is_left_behind():
    assert "，。" not in cap_ellipsis("真的……。算了", 0)


def test_dotted_and_unicode_ellipsis_are_the_same_thing():
    assert cap_ellipsis("a... b... c", 1) == "a... b， c"


def test_ellipsis_capping_never_removes_words():
    text = "先这样……然后那样"
    stripped = cap_ellipsis(text, 0)
    assert "先这样" in stripped and "然后那样" in stripped


def test_tildes_are_all_removed_by_default():
    assert cap_tilde("好～，我马上来～") == "好，我马上来"


def test_one_trailing_tilde_survives_when_budgeted():
    assert cap_tilde("知道啦～", 1) == "知道啦～"


def test_a_mid_sentence_tilde_never_spends_the_budget():
    assert cap_tilde("好～我这就来", 1) == "好我这就来"


def test_a_tilde_run_counts_as_one():
    assert cap_tilde("嗯～～", 1) == "嗯～～"


def test_decorations_are_untouched_by_default():
    text = "真的！^_^ 好耶 🎉"
    assert strip_decorations(text) == text


def test_exclamation_folding_is_opt_in():
    assert strip_decorations("真的！", fold_exclamation=True) == "真的。"
    assert strip_decorations("什么?!", fold_exclamation=True) == "什么。"


def test_emoji_and_kaomoji_removal_is_opt_in():
    assert strip_decorations("好耶 🎉^_^", drop_emoji=True) == "好耶 "
    assert strip_decorations("ok T_T", drop_emoji=True) == "ok "


def test_removing_decorations_does_not_leave_a_dangling_comma():
    assert strip_decorations("好耶，^_^。", drop_emoji=True) == "好耶。"
