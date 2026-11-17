"""Every Lua plugin, shipped or prototype, launches an intent Be My Lens will accept.

Plugins are discovered by globbing, so a new plugin is covered without new test code.
Expectations come from the app's own sources (ExternalIntegrationContract.kt,
AndroidManifest.xml, build.gradle.kts) via android_contract.py.
"""

import pytest

from jieshuo_host import PLUGIN_DIR, PROTOTYPE_DIR, Intent

ALL_PLUGINS = sorted(PLUGIN_DIR.glob("*.lua")) + sorted(PROTOTYPE_DIR.glob("*.lua"))
PLUGIN_IDS = [f"{path.parent.name}/{path.name}" for path in ALL_PLUGINS]


def test_plugins_are_discovered():
    assert len(list(PLUGIN_DIR.glob("*.lua"))) >= 1


@pytest.mark.parametrize("plugin", ALL_PLUGINS, ids=PLUGIN_IDS)
def test_launch_satisfies_the_android_integration_contract(jieshuo, contract, plugin):
    jieshuo.run(plugin)
    intent = jieshuo.only_launch()

    # Addressed explicitly to an exported activity that declares this action.
    activity = contract.exported_activities[intent.component.getClassName()]
    assert intent.action == contract.action_describe_image
    assert intent.action in activity.actions
    assert intent.component.getPackageName() == contract.application_id
    assert intent.package == contract.application_id

    # Only keys the app reads, so a typo cannot be silently ignored.
    known_keys = {Intent.EXTRA_STREAM, *contract.extras.values()}
    assert set(intent.extras) <= known_keys

    mode = intent.extras[contract.extra("MODE")]
    assert mode in contract.supported_modes

    auto_speak = intent.extras.get(contract.extra("AUTO_SPEAK"), True)
    assert isinstance(auto_speak, bool)

    if mode == contract.mode("TRANSLATE_TEXT"):
        text = intent.extras.get(contract.extra("TEXT"))
        assert isinstance(text, str) and text.strip(), "translate_text needs non-blank TEXT"
        return

    assert intent.extras.get(Intent.EXTRA_STREAM) is not None, f"{mode} needs an image URI"
    assert intent.has_flag(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Be My Lens cannot read the image without a grant"
    if mode == contract.mode("CUSTOM_PROMPT"):
        prompt = intent.extras.get(contract.extra("PROMPT"))
        assert isinstance(prompt, str) and prompt.strip(), "custom_prompt needs a non-blank prompt"
