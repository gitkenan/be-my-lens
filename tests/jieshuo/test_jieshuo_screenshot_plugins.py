"""The screenshot plugins in dist/jieshuo-lua: capture, save, share and launch Be My Lens.

Each test runs a real plugin file in the fake Jieshuo host and checks what a blind user
would experience: whether Be My Lens opens with a readable image, and what is announced
when something goes wrong. None of these scenarios may crash the script.
"""

import pytest

from jieshuo_host import EXTERNAL_CACHE, INTERNAL_CACHE, SAMPLE_PNG, Intent, Screenshot, ScreenshotBitmap

# (plugin file, Kotlin name of the mode it must request)
SCREENSHOT_PLUGINS = [
    pytest.param("describe_picture.lua", "DESCRIBE_SCREEN", id="describe_picture"),
    pytest.param("read_picture_text.lua", "READ_TEXT", id="read_picture_text"),
    pytest.param("translate_picture.lua", "CUSTOM_PROMPT", id="translate_picture"),
]

pytestmark = pytest.mark.parametrize("plugin, mode", SCREENSHOT_PLUGINS)

SAVE_FAILED = "تعذر حفظ لقطة الشاشة"
CAPTURE_FAILED = "فشل التقاط الشاشة"
CAPTURE_UNAVAILABLE = "تعذر التقاط الشاشة"
OPEN_FAILED = "تعذر فتح التطبيق"
OPENING = "عين الراشد: جار الفتح"


def announced(jieshuo, phrase: str) -> bool:
    return any(phrase in toast for toast in jieshuo.toasts)


def test_opens_be_my_lens_with_the_captured_screenshot(jieshuo, contract, plugin, mode):
    jieshuo.run(plugin)

    intent = jieshuo.only_launch()
    assert intent.action == contract.action_describe_image
    assert intent.component.getPackageName() == contract.application_id
    assert intent.package == contract.application_id
    assert intent.extras[contract.extra("MODE")] == contract.mode(mode)
    assert intent.has_flag(Intent.FLAG_GRANT_READ_URI_PERMISSION)

    # One URI, offered through every lookup route the app supports, typed as the PNG it is.
    uri = intent.data
    assert intent.extras[Intent.EXTRA_STREAM] == uri
    assert intent.extras[contract.extra("IMAGE_URI")] == uri
    assert intent.type == "image/png"
    saved = jieshuo.file_behind(uri)
    assert saved.suffix == ".png"
    assert saved.read_bytes() == SAMPLE_PNG


def test_captures_the_screen_around_the_focused_node(jieshuo, plugin, mode):
    jieshuo.run(plugin)

    assert jieshuo.screenshot_requests == [jieshuo.node]


def test_announces_the_action_then_that_be_my_lens_is_opening(jieshuo, plugin, mode):
    jieshuo.run(plugin)

    assert len(jieshuo.toasts) == 2
    assert jieshuo.toasts[0].startswith("عين الراشد: ")
    assert jieshuo.toasts[1] == OPENING


def test_every_run_shares_a_new_file_so_a_stale_screenshot_is_never_described(jieshuo, plugin, mode):
    jieshuo.run(plugin)
    jieshuo.run(plugin)

    first, second = (intent.data for intent in jieshuo.launched)
    assert first != second
    assert jieshuo.file_behind(first) != jieshuo.file_behind(second)


def test_prefers_the_external_cache(jieshuo, plugin, mode):
    jieshuo.run(plugin)

    saved = jieshuo.file_behind(jieshuo.only_launch().data)
    assert saved.is_relative_to(jieshuo.host_path(EXTERNAL_CACHE))


def test_falls_back_to_internal_cache_without_external_storage(jieshuo, plugin, mode):
    jieshuo.external_cache_available = False

    jieshuo.run(plugin)

    saved = jieshuo.file_behind(jieshuo.only_launch().data)
    assert saved.is_relative_to(jieshuo.host_path(INTERNAL_CACHE))
    assert saved.read_bytes() == SAMPLE_PNG


def test_falls_back_when_the_external_cache_cannot_be_written(jieshuo, plugin, mode):
    jieshuo.break_directory(EXTERNAL_CACHE)

    jieshuo.run(plugin)

    saved = jieshuo.file_behind(jieshuo.only_launch().data)
    assert saved.is_relative_to(jieshuo.host_path(INTERNAL_CACHE))


def test_uses_sdcard_as_last_resort(jieshuo, plugin, mode):
    jieshuo.external_cache_available = False
    jieshuo.internal_cache_available = False

    jieshuo.run(plugin)

    saved = jieshuo.file_behind(jieshuo.only_launch().data)
    assert saved.is_relative_to(jieshuo.host_path("/sdcard/BeMyLens"))


def test_announces_failure_and_stays_closed_when_nowhere_is_writable(jieshuo, plugin, mode):
    jieshuo.break_directory(EXTERNAL_CACHE)
    jieshuo.break_directory(INTERNAL_CACHE)
    jieshuo.break_directory("/sdcard")

    jieshuo.run(plugin)

    assert jieshuo.launched == []
    assert announced(jieshuo, SAVE_FAILED)
    assert jieshuo.open_streams == []


def test_a_bitmap_that_fails_to_compress_is_never_shared(jieshuo, plugin, mode):
    jieshuo.screenshot = Screenshot.succeeds(ScreenshotBitmap(compress_result=False))

    jieshuo.run(plugin)

    assert jieshuo.launched == []
    assert announced(jieshuo, SAVE_FAILED)


def test_closes_the_file_when_compression_throws(jieshuo, plugin, mode):
    jieshuo.screenshot = Screenshot.succeeds(ScreenshotBitmap(compress_result=RuntimeError("recycled bitmap")))

    jieshuo.run(plugin)

    assert jieshuo.launched == []
    assert jieshuo.open_streams == []
    assert announced(jieshuo, SAVE_FAILED)


def test_does_not_launch_without_a_shareable_uri(jieshuo, plugin, mode):
    jieshuo.file_provider_works = False

    jieshuo.run(plugin)

    assert jieshuo.launched == []
    assert announced(jieshuo, SAVE_FAILED)


@pytest.mark.parametrize(
    "screenshot, reason",
    [
        pytest.param(Screenshot.fails(error_code=3), "3", id="capture-failed"),
        pytest.param(
            Screenshot.errors("MediaProjection was revoked"), "MediaProjection was revoked", id="capture-error"
        ),
    ],
)
def test_announces_why_the_screenshot_failed(jieshuo, plugin, mode, screenshot, reason):
    jieshuo.screenshot = screenshot

    jieshuo.run(plugin)

    assert jieshuo.launched == []
    assert announced(jieshuo, CAPTURE_FAILED)
    assert announced(jieshuo, reason)


def test_survives_a_jieshuo_version_without_the_screenshot_api(jieshuo, plugin, mode):
    jieshuo.screenshot_api_available = False

    jieshuo.run(plugin)

    assert jieshuo.launched == []
    assert announced(jieshuo, CAPTURE_UNAVAILABLE)


def test_announces_when_be_my_lens_is_not_installed(jieshuo, plugin, mode):
    jieshuo.be_my_lens_installed = False

    jieshuo.run(plugin)

    assert jieshuo.launched == []
    assert announced(jieshuo, OPEN_FAILED)


def test_does_nothing_until_the_screenshot_arrives(jieshuo, plugin, mode):
    jieshuo.screenshot = Screenshot(outcome="never")

    jieshuo.run(plugin)

    assert jieshuo.launched == []
    assert len(jieshuo.screenshot_requests) == 1
