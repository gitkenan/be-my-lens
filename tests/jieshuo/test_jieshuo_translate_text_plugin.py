"""dist/jieshuo-lua/translate_text.lua: send the focused item's text to Be My Lens for translation."""

import pytest

from jieshuo_host import CharSequence, FocusedNode, Intent, RuntimeException

PLUGIN = "translate_text.lua"
NO_TEXT_FOUND = "لم يتم العثور على نص محدد"
OPEN_FAILED = "تعذر فتح التطبيق"


def sent_text(jieshuo, contract) -> str:
    return jieshuo.only_launch().extras[contract.extra("TEXT")]


def test_sends_the_focused_text_for_translation(jieshuo, contract):
    jieshuo.node = FocusedNode(text="Exit 12A is 300 meters ahead")

    jieshuo.run(PLUGIN)

    intent = jieshuo.only_launch()
    assert intent.action == contract.action_describe_image
    assert intent.component.getPackageName() == contract.application_id
    assert intent.extras[contract.extra("MODE")] == contract.mode("TRANSLATE_TEXT")
    assert intent.extras[contract.extra("TEXT")] == "Exit 12A is 300 meters ahead"
    assert intent.extras[contract.extra("AUTO_SPEAK")] is True


def test_shares_no_screenshot_or_image(jieshuo, contract):
    jieshuo.run(PLUGIN)

    intent = jieshuo.only_launch()
    assert jieshuo.screenshot_requests == []
    assert intent.data is None
    assert Intent.EXTRA_STREAM not in intent.extras
    assert contract.extra("IMAGE_URI") not in intent.extras
    assert not intent.has_flag(Intent.FLAG_GRANT_READ_URI_PERMISSION)


def test_sends_multiline_and_non_latin_text_verbatim(jieshuo, contract):
    text = "  Ausfahrt 12A\n東京駅 →  "
    jieshuo.node = FocusedNode(text=text)

    jieshuo.run(PLUGIN)

    assert sent_text(jieshuo, contract) == text


def test_converts_styled_java_text_to_a_plain_string(jieshuo, contract):
    jieshuo.node = FocusedNode(text=CharSequence("Styled label"))

    jieshuo.run(PLUGIN)

    assert sent_text(jieshuo, contract) == "Styled label"


@pytest.mark.parametrize("text", [None, ""], ids=["no-text", "empty-text"])
def test_falls_back_to_the_content_description(jieshuo, contract, text):
    jieshuo.node = FocusedNode(text=text, content_description="Close button")

    jieshuo.run(PLUGIN)

    assert sent_text(jieshuo, contract) == "Close button"


def test_falls_back_to_the_content_description_when_reading_text_throws(jieshuo, contract):
    jieshuo.node = FocusedNode(text_error=RuntimeException("node was recycled"), content_description="Play")

    jieshuo.run(PLUGIN)

    assert sent_text(jieshuo, contract) == "Play"


@pytest.mark.parametrize(
    "node",
    [
        pytest.param(None, id="nothing-focused"),
        pytest.param(FocusedNode(text=None, content_description=None), id="no-text-or-description"),
        pytest.param(FocusedNode(text="", content_description=""), id="empty-text-and-description"),
    ],
)
def test_announces_when_there_is_no_text_and_does_not_open_the_app(jieshuo, node):
    jieshuo.node = node

    jieshuo.run(PLUGIN)

    assert jieshuo.launched == []
    assert any(NO_TEXT_FOUND in toast for toast in jieshuo.toasts)


def test_announces_when_be_my_lens_is_not_installed(jieshuo):
    jieshuo.be_my_lens_installed = False

    jieshuo.run(PLUGIN)

    assert jieshuo.launched == []
    assert any(OPEN_FAILED in toast for toast in jieshuo.toasts)
