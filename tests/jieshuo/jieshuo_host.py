"""A fake Jieshuo host that runs the Be My Lens Lua plugins off-device.

Jieshuo runs plugins on AndroLua (Lua 5.3 with a Java bridge). This module recreates the
part of that environment the plugins touch, so the real .lua files run unmodified:

* ``require "import"`` / ``import "java.class.Name"`` bind fake Java classes as globals;
  importing a class the host does not provide fails, as it would on a device.
* ``this`` is the Jieshuo service: cache directories, ``getUriForFile``,
  ``startActivity`` and the asynchronous ``getScreenShot(node, callbacks)``.
* ``node`` is the accessibility node that had focus when the action ran.
* ``File`` / ``FileOutputStream`` write real files under a temp directory, which is
  mounted at Android-looking paths (external cache, internal cache, /sdcard).
* ``startActivity`` resolves explicit intents against the exported activities in the
  app's real AndroidManifest.xml, so a wrong package or class name fails to launch.

Screenshots are delivered after the script's main chunk returns, matching Jieshuo's
callback-based API. Any Lua error that escapes a plugin raises ``PluginCrashed``.
"""

from __future__ import annotations

import posixpath
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from lupa import lua53

import lua_coverage
from android_contract import REPO_ROOT, AndroidContract

PLUGIN_DIR = REPO_ROOT / "dist" / "jieshuo-lua"
PROTOTYPE_DIR = REPO_ROOT / "prototypes" / "jieshuo"

HOST_PACKAGE = "com.nirenr.talkman"  # Jieshuo (docs/jieshuo-lua-prototype.md); used for virtual paths
EXTERNAL_CACHE = f"/storage/emulated/0/Android/data/{HOST_PACKAGE}/cache"
INTERNAL_CACHE = f"/data/user/0/{HOST_PACKAGE}/cache"
SDCARD = "/sdcard"
FILE_PROVIDER_AUTHORITY = f"{HOST_PACKAGE}.fileprovider"

# A PNG signature plus payload: what Bitmap.compress(PNG, ...) writes by default.
SAMPLE_PNG = b"\x89PNG\r\n\x1a\n" + b"jieshuo-screenshot"


class PluginCrashed(AssertionError):
    """A Lua error escaped the plugin. On a device Jieshuo would surface a script error."""


class ActivityNotFoundException(Exception):
    pass


class ClassNotFoundException(Exception):
    pass


class RuntimeException(Exception):
    pass


# Android values ------------------------------------------------------------------


class Uri:
    def __init__(self, value: str):
        self.value = value

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"Uri({self.value!r})"

    def __eq__(self, other) -> bool:
        return isinstance(other, Uri) and other.value == self.value

    def __hash__(self) -> int:
        return hash(self.value)


class ComponentName:
    def __init__(self, package_name: str, class_name: str):
        self.package_name = package_name
        self.class_name = class_name

    def getPackageName(self) -> str:
        return self.package_name

    def getClassName(self) -> str:
        return self.class_name

    def __str__(self) -> str:
        return f"{self.package_name}/{self.class_name}"


class Intent:
    """Records everything a plugin sets. Builder methods return the intent, as in Java."""

    FLAG_GRANT_READ_URI_PERMISSION = 0x00000001
    FLAG_ACTIVITY_NEW_TASK = 0x10000000
    ACTION_SEND = "android.intent.action.SEND"
    EXTRA_STREAM = "android.intent.extra.STREAM"
    EXTRA_TEXT = "android.intent.extra.TEXT"

    def __init__(self, action: str | None = None):
        self.action = action
        self.component: ComponentName | None = None
        self.package: str | None = None
        self.flags = 0
        self.extras: dict[str, object] = {}
        self.data: Uri | None = None
        self.type: str | None = None

    def setAction(self, action):
        self.action = action
        return self

    def setComponent(self, component):
        self.component = component
        return self

    def setPackage(self, package):
        self.package = package
        return self

    def addFlags(self, flags):
        self.flags |= int(flags)
        return self

    def setFlags(self, flags):
        self.flags = int(flags)
        return self

    def putExtra(self, key, value):
        self.extras[key] = value
        return self

    # Like Android, setData and setType each clear the other.
    def setData(self, uri):
        self.data, self.type = uri, None
        return self

    def setType(self, mime_type):
        self.data, self.type = None, mime_type
        return self

    def setDataAndType(self, uri, mime_type):
        self.data, self.type = uri, mime_type
        return self

    def has_flag(self, flag: int) -> bool:
        return bool(self.flags & flag)


class Bitmap:
    class CompressFormat:
        PNG = "PNG"
        JPEG = "JPEG"
        WEBP = "WEBP"


class ScreenshotBitmap:
    """The bitmap Jieshuo hands to onScreenCaptureDone.

    ``compress_result`` is what ``compress`` returns; pass an exception to make it throw
    (e.g. a recycled bitmap).
    """

    def __init__(self, png: bytes = SAMPLE_PNG, compress_result: bool | Exception = True):
        self.png = png
        self.compress_result = compress_result
        self.compress_calls: list[tuple[str, int]] = []

    def compress(self, compress_format, quality, stream):
        self.compress_calls.append((compress_format, quality))
        if isinstance(self.compress_result, Exception):
            raise self.compress_result
        if self.compress_result:
            stream.write(self.png)
        return self.compress_result


@dataclass
class FocusedNode:
    """The AccessibilityNodeInfo-like ``node`` global."""

    text: object = None
    content_description: object = None
    text_error: Exception | None = None

    def getText(self):
        if self.text_error is not None:
            raise self.text_error
        return self.text

    def getContentDescription(self):
        return self.content_description


class CharSequence:
    """A Java CharSequence (e.g. SpannableString) that is not a plain Lua string."""

    def __init__(self, value: str):
        self.value = value

    def __str__(self) -> str:
        return self.value


# The device -----------------------------------------------------------------------


@dataclass
class Screenshot:
    """How the next ``this.getScreenShot`` call completes."""

    outcome: str = "done"  # "done", "failed", "error" or "never"
    bitmap: ScreenshotBitmap = field(default_factory=ScreenshotBitmap)
    error_code: int = 3
    error_message: str = "MediaProjection was revoked"

    @classmethod
    def succeeds(cls, bitmap: ScreenshotBitmap | None = None) -> Screenshot:
        return cls(outcome="done", bitmap=bitmap or ScreenshotBitmap())

    @classmethod
    def fails(cls, error_code: int) -> Screenshot:
        return cls(outcome="failed", error_code=error_code)

    @classmethod
    def errors(cls, message: str) -> Screenshot:
        return cls(outcome="error", error_message=message)


class FakeJieshuo:
    """One phone with Jieshuo and (optionally) Be My Lens installed.

    State accumulates across ``run`` calls, so tests can run a plugin repeatedly.
    """

    def __init__(self, root: Path, contract: AndroidContract):
        self.root = root
        self.contract = contract
        self.mounts = {
            EXTERNAL_CACHE: root / "external-cache",
            INTERNAL_CACHE: root / "internal-cache",
            SDCARD: root / "sdcard",
        }
        for host_dir in self.mounts.values():
            host_dir.mkdir(parents=True, exist_ok=True)

        # Knobs tests turn to simulate device conditions.
        self.node: FocusedNode | None = FocusedNode(text="Focused item")
        self.screenshot = Screenshot.succeeds()
        self.screenshot_api_available = True
        self.external_cache_available = True
        self.internal_cache_available = True
        self.file_provider_works = True
        self.be_my_lens_installed = True

        # What happened.
        self.launched: list[Intent] = []
        self.toasts: list[str] = []
        self.log: list[str] = []
        self.screenshot_requests: list[object] = []
        self.uris_created: dict[Uri, Path] = {}
        self.open_streams: list[_OutputStream] = []
        self._clock = 1_700_000_000_000
        self._java_classes = {
            "android.content.Intent": Intent,
            "android.content.ComponentName": ComponentName,
            "android.graphics.Bitmap": Bitmap,
            "android.widget.Toast": _toast_class(self),
            "java.io.File": _file_class(self),
            "java.io.FileOutputStream": _output_stream_class(self),
            "java.lang.System": _system_class(self),
        }

    # Running plugins --------------------------------------------------------------

    def run(self, script: str | Path) -> FakeJieshuo:
        path = Path(script)
        if not path.is_absolute():
            path = PLUGIN_DIR / path
        runtime = self._new_runtime()
        name = lua_coverage.chunk_name(path, REPO_ROOT)
        chunk = self._compile(runtime, path, name)
        pending_callbacks: list[object] = []
        runtime.globals().this = _JieshuoService(self, pending_callbacks)

        if lua_coverage.enabled():
            lua_coverage.register_script(path, name)
            lua_coverage.install_hook(runtime)
        try:
            self._call_lua(path, chunk)
            for callbacks in pending_callbacks:
                self._deliver_screenshot(path, callbacks)
        finally:
            if lua_coverage.enabled():
                lua_coverage.collect()
        return self

    def only_launch(self) -> Intent:
        assert len(self.launched) == 1, f"expected exactly one launch, got {len(self.launched)}; toasts: {self.toasts}"
        return self.launched[0]

    def host_path(self, virtual_path: str) -> Path | None:
        for mount, host_dir in self.mounts.items():
            if virtual_path == mount or virtual_path.startswith(mount + "/"):
                return host_dir / posixpath.relpath(virtual_path, mount)
        return None

    def file_behind(self, uri: Uri) -> Path:
        return self.uris_created[uri]

    def break_directory(self, virtual_dir: str) -> None:
        """Make a directory unusable, the way a full or read-only volume would be."""
        host_dir = self.host_path(virtual_dir)
        shutil.rmtree(host_dir, ignore_errors=True)
        # A regular file where a directory is expected: mkdirs and opening files inside
        # it fail for every user, root included.
        host_dir.write_bytes(b"")

    # Internals --------------------------------------------------------------------

    def _new_runtime(self):
        runtime = lua53.LuaRuntime(
            unpack_returned_tuples=True,
            register_eval=False,
            register_builtins=False,
            encoding="utf-8",
        )
        lua_globals = runtime.globals()
        lua_globals.node = self.node
        lua_globals.print = runtime.eval(
            """
            function(log)
              return function(...)
                local parts = {}
                for i = 1, select("#", ...) do
                  parts[#parts + 1] = tostring((select(i, ...)))
                end
                log(table.concat(parts, "\t"))
              end
            end
            """
        )(self.log.append)
        # AndroLua: `require "import"` defines a global `import` that binds a Java class
        # to a global named after it, e.g. import "android.content.Intent" -> Intent.
        runtime.eval(
            """
            function(host_import)
              package.preload["import"] = function()
                function import(name)
                  local class = host_import(name)
                  _G[name:match("([^%.]+)$")] = class
                  return class
                end
                return import
              end
            end
            """
        )(self._import_class)
        return runtime

    @staticmethod
    def _compile(runtime, path: Path, name: str):
        # Lua's load returns the chunk on success and (nil, message) on a syntax error.
        result = runtime.globals().load(path.read_text(encoding="utf-8"), name)
        if isinstance(result, tuple):
            raise PluginCrashed(f"{path.name} does not compile: {result[1]}")
        return result

    @staticmethod
    def _call_lua(path: Path, function, *args):
        try:
            return function(*args)
        except lua53.LuaError as error:
            raise PluginCrashed(f"{path.name} raised: {error}") from error

    def _deliver_screenshot(self, path: Path, callbacks) -> None:
        shot = self.screenshot
        if shot.outcome == "done":
            self._call_lua(path, callbacks.onScreenCaptureDone, shot.bitmap)
        elif shot.outcome == "failed":
            self._call_lua(path, callbacks.onScreenCaptureFailed, shot.error_code)
        elif shot.outcome == "error":
            self._call_lua(path, callbacks.onScreenCaptureError, shot.error_message)

    def _import_class(self, name: str):
        if name not in self._java_classes:
            raise ClassNotFoundException(name)
        return self._java_classes[name]

    def _now_millis(self) -> int:
        self._clock += 1
        return self._clock

    def _start_activity(self, intent: Intent) -> None:
        component = intent.component
        activity = None
        if (
            self.be_my_lens_installed
            and component is not None
            and component.package_name == self.contract.application_id
        ):
            activity = self.contract.exported_activities.get(component.class_name)
        if activity is None:
            raise ActivityNotFoundException(f"Unable to find explicit activity class {component}")
        self.launched.append(intent)


class _JieshuoService:
    """The ``this`` global: Jieshuo's service context as seen by a plugin."""

    def __init__(self, device: FakeJieshuo, pending_callbacks: list):
        self._device = device
        self._pending_callbacks = pending_callbacks

    def getExternalCacheDir(self):
        if not self._device.external_cache_available:
            return None
        return self._device._import_class("java.io.File")(EXTERNAL_CACHE)

    def getCacheDir(self):
        if not self._device.internal_cache_available:
            raise RuntimeException("cache directory unavailable")
        return self._device._import_class("java.io.File")(INTERNAL_CACHE)

    def getUriForFile(self, file):
        if not self._device.file_provider_works:
            return None
        uri = Uri(f"content://{FILE_PROVIDER_AUTHORITY}/{file.getName()}")
        self._device.uris_created[uri] = file.host
        return uri

    def startActivity(self, intent):
        self._device._start_activity(intent)

    def getScreenShot(self, node, callbacks):
        if not self._device.screenshot_api_available:
            raise RuntimeException("getScreenShot is not available in this Jieshuo version")
        self._device.screenshot_requests.append(node)
        if self._device.screenshot.outcome != "never":
            self._pending_callbacks.append(callbacks)


class _OutputStream:
    def __init__(self, device: FakeJieshuo, host_file: Path):
        self._device = device
        # Deliberately not a context manager: like Java's FileOutputStream it stays open
        # until the plugin calls close(), which is what the leak checks observe.
        self._handle = open(host_file, "wb")
        device.open_streams.append(self)

    def write(self, data: bytes) -> None:
        self._handle.write(data)

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()
            self._device.open_streams.remove(self)


def _file_class(device: FakeJieshuo):
    class File:
        def __init__(self, parent, child=None):
            parent_path = parent.path if isinstance(parent, File) else str(parent)
            self.path = posixpath.normpath(posixpath.join(parent_path, child) if child else parent_path)
            self.host = device.host_path(self.path)

        def mkdirs(self) -> bool:
            if self.host is None or self.host.is_dir():
                return False
            try:
                self.host.mkdir(parents=True)
            except OSError:
                return False
            return True

        def exists(self) -> bool:
            return self.host is not None and self.host.exists()

        def getName(self) -> str:
            return posixpath.basename(self.path)

        def getAbsolutePath(self) -> str:
            return self.path

        def __str__(self) -> str:
            return self.path

    return File


def _output_stream_class(device: FakeJieshuo):
    def FileOutputStream(file):
        if file.host is None:
            raise PermissionError(f"{file.path}: open failed: EACCES (Permission denied)")
        return _OutputStream(device, file.host)

    return FileOutputStream


def _toast_class(device: FakeJieshuo):
    class _Toast:
        def __init__(self, text: str):
            self.text = text

        def show(self) -> None:
            device.toasts.append(self.text)

    class Toast:
        LENGTH_SHORT = 0
        LENGTH_LONG = 1

        @staticmethod
        def makeText(context, text, duration):
            return _Toast(str(text))

    return Toast


def _system_class(device: FakeJieshuo):
    class System:
        @staticmethod
        def currentTimeMillis() -> int:
            return device._now_millis()

    return System
