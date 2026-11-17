"""Reads the Android side of the Jieshuo integration contract straight from the app sources.

The plugin tests assert against these values instead of copies of them, so renaming an
action, extra or mode in Kotlin (or the activity in the manifest) breaks these tests
until the Lua plugins are updated to match.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "app"
CONTRACT_KT = APP_DIR / "src/main/java/io/bemylens/app/integration/ExternalIntegrationContract.kt"
MANIFEST_XML = APP_DIR / "src/main/AndroidManifest.xml"
BUILD_GRADLE = APP_DIR / "build.gradle.kts"

ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


@dataclass(frozen=True)
class ExportedActivity:
    class_name: str
    actions: frozenset[str]


@dataclass(frozen=True)
class AndroidContract:
    application_id: str
    action_describe_image: str
    extras: dict[str, str]
    modes: dict[str, str]
    supported_modes: frozenset[str]
    exported_activities: dict[str, ExportedActivity]

    def extra(self, kotlin_name: str) -> str:
        return self.extras[kotlin_name]

    def mode(self, kotlin_name: str) -> str:
        return self.modes[kotlin_name]


def load_android_contract() -> AndroidContract:
    source = CONTRACT_KT.read_text(encoding="utf-8")
    extras = _string_constants(_object_body(source, "Extras"))
    modes_body = _object_body(source, "Modes")
    modes = _string_constants(modes_body)
    supported = re.search(r"val\s+SUPPORTED\s*=\s*setOf\(([^)]*)\)", modes_body)
    action = re.search(r'const\s+val\s+ACTION_DESCRIBE_IMAGE\s*=\s*"([^"]+)"', source)
    if not (extras and modes and supported and action):
        raise AssertionError(f"Could not read the integration contract from {CONTRACT_KT}")

    supported_names = [name.strip() for name in supported.group(1).split(",") if name.strip()]
    return AndroidContract(
        application_id=_gradle_string("applicationId"),
        action_describe_image=action.group(1),
        extras=extras,
        modes=modes,
        supported_modes=frozenset(modes[name] for name in supported_names),
        exported_activities=_exported_activities(_gradle_string("namespace")),
    )


def _object_body(source: str, name: str) -> str:
    match = re.search(rf"\bobject\s+{name}\s*\{{", source)
    if match is None:
        raise AssertionError(f"object {name} not found in {CONTRACT_KT}")
    depth, start = 1, match.end()
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index]
    raise AssertionError(f"object {name} is not closed in {CONTRACT_KT}")


def _string_constants(body: str) -> dict[str, str]:
    return dict(re.findall(r'const\s+val\s+(\w+)\s*=\s*"([^"]*)"', body))


def _gradle_string(key: str) -> str:
    match = re.search(rf'\b{key}\s*=\s*"([^"]+)"', BUILD_GRADLE.read_text(encoding="utf-8"))
    if match is None:
        raise AssertionError(f"{key} not found in {BUILD_GRADLE}")
    return match.group(1)


def _exported_activities(namespace: str) -> dict[str, ExportedActivity]:
    application = ElementTree.parse(MANIFEST_XML).getroot().find("application")
    activities = {}
    for activity in application.findall("activity"):
        if activity.get(f"{ANDROID_NS}exported") != "true":
            continue
        name = activity.get(f"{ANDROID_NS}name")
        class_name = namespace + name if name.startswith(".") else name
        actions = frozenset(
            action.get(f"{ANDROID_NS}name")
            for intent_filter in activity.findall("intent-filter")
            for action in intent_filter.findall("action")
        )
        activities[class_name] = ExportedActivity(class_name=class_name, actions=actions)
    return activities
