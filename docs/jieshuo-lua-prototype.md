# Jieshuo Lua Prototype Notes

This note captures the current discovery work for a future Jieshuo `.ppk`
extension. The end-to-end Jieshuo to Be My Lens launch path has now been
validated on a real device, but the files here are still prototype-level scripts
rather than a polished packaged extension.

## Real-Device Validation

Validated on a real device with Jieshuo installed:

- no-image explicit launch opens Be My Lens
- `describe_screen` screenshot flow opens Be My Lens and processes the image
- `focused_item` screenshot flow opens Be My Lens and processes the image
- Be My Lens receives the URI, copies it locally, sends it through the existing
  Android/backend image pipeline, and speaks the result

No Android app contract issue was found during this test pass.

## Sources Found

No Jieshuo `.ppk` or Lua extension examples exist in this repository.

Public examples show Jieshuo extensions/custom functions using AndroLua-style
Lua:

- `require "import"`
- `import "android.content.*"` or specific Android classes
- `Intent()` construction from Lua
- `ComponentName(...)` for explicit Activity launch
- `this.startActivity(intent)` as the launch call

[Accessible Android's Jieshuo browser article][accessible-android-browser]
documents a Jieshuo custom function that explicitly launches an Activity with:

```lua
require "import"
import "android.content.*"
i = Intent()
  .setComponent(ComponentName("com.nirenr.talkman", "com.nirenr.talkman.WebActivity"))
this.startActivity(i)
```

A public forum example for a Jieshuo plugin shows screenshot capture with:

```lua
this.getScreenShot(node, {
  onScreenCaptureDone = function(bitmap)
    bitmap.compress(Bitmap.CompressFormat.PNG, 90, FileOutputStream(File("/sdcard/", "master_kaushik.jpg")))
    this.startActivity(Intent(Intent.ACTION_SEND)
      .setType("image/*")
      .setPackage(app_pkg)
      .putExtra(Intent.EXTRA_STREAM, this.getUriForFile(File("/sdcard/master_kaushik.jpg"))))
  end
})
```

That suggests Jieshuo may expose:

- `node`, probably the current accessibility focus node
- `this.getScreenShot(node, callback)`
- callback method `onScreenCaptureDone`
- a bitmap-like callback value that supports `compress(...)`
- `this.getUriForFile(File(...))`, returning a shareable content URI

These Jieshuo-specific APIs are now confirmed for the tested device/version, but
they are still not documented in an official English SDK.

Android's platform APIs support the underlying pieces used here:

- explicit Activity targeting with `Intent.setComponent(...)`
- application-specific actions with `Intent.setAction(...)`
- data/type image URI delivery with `Intent.setDataAndType(...)`
- package scoping with `Intent.setPackage(...)`
- `ComponentName(package, className)` construction
- accessibility screenshot capture in native Android accessibility services
  via `AccessibilityService.takeScreenshot(...)`

## Can Jieshuo Launch Be My Lens?

Yes. This has been validated on a real device.

The Android side exposes an exported Activity:

```text
io.bemylens.app/.JieshuoEntryActivity
```

The recommended explicit launch uses:

```text
action = io.bemylens.app.action.DESCRIBE_IMAGE
package = io.bemylens.app
component = io.bemylens.app/io.bemylens.app.JieshuoEntryActivity
```

Using an explicit component should avoid chooser UI and should work even if
intent-filter matching changes later.

## Most Likely Lua Shape

The original diagnostic harness is:

```text
prototypes/jieshuo/describe_image.lua
```

It has a single `TEST_MODE` setting near the top:

```lua
local TEST_MODE = "describe_screen"
```

Supported prototype test modes:

| `TEST_MODE` | Purpose |
| --- | --- |
| `no_image` | Launches Be My Lens explicitly without an image URI. This verifies Jieshuo can start the Activity. |
| `describe_screen` | Captures a screenshot and launches Be My Lens with `mode = "describe_screen"`. |
| `focused_item` | Captures a screenshot and launches Be My Lens with `mode = "focused_item"`. |

The no-image smoke test launches:

```text
package = io.bemylens.app
activity = io.bemylens.app.JieshuoEntryActivity
action = io.bemylens.app.action.DESCRIBE_IMAGE
mode = describe_screen
autoSpeak = true
```

with no image URI. Be My Lens should open and show its no-image error. That is
expected for this smoke test.

The current user-facing prototype actions are:

```text
prototypes/jieshuo/describe_screen.lua
prototypes/jieshuo/describe_focused_item.lua
```

These are standalone scripts intended to be easier to import or bind as Jieshuo
actions. They keep only concise user-facing feedback:

- `Be My Lens: Describe screen with Be My Lens`
- `Be My Lens: Describe focused item with Be My Lens`
- `Be My Lens: Opening`
- short failure messages if capture, file save, URI generation, or launch fails

Detailed file paths and URIs are printed for debugging and can be surfaced as
toasts by setting `DEBUG = true` near the top of either script.

Current action-script shape, abridged:

```lua
require "import"
import "android.content.Intent"
import "android.content.ComponentName"
import "android.graphics.Bitmap"
import "android.widget.Toast"
import "java.io.File"
import "java.io.FileOutputStream"

local MODE = "describe_screen" -- or "focused_item"

local function launchBeMyLens(uri)
  local intent = Intent()
    .setAction("io.bemylens.app.action.DESCRIBE_IMAGE")
    .setComponent(ComponentName(
      "io.bemylens.app",
      "io.bemylens.app.JieshuoEntryActivity"
    ))
    .setPackage("io.bemylens.app")
    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    .putExtra("mode", MODE)
    .putExtra("autoSpeak", true)

  intent.setDataAndType(uri, "image/png")
  intent.putExtra(Intent.EXTRA_STREAM, uri)
  intent.putExtra("io.bemylens.app.extra.IMAGE_URI", uri)
  this.startActivity(intent)
end

this.getScreenShot(node, {
  onScreenCaptureDone = function(bitmap)
    -- The runnable scripts save to cache first, then fall back if needed.
    local uri = saveScreenshotAndCreateUri(bitmap)
    launchBeMyLens(uri)
  end
})
```

Focused-item mode uses the same capture and launch path with:

```lua
local MODE = "focused_item"
```

If Jieshuo provides a cropped focused-node screenshot, pass that. If it only
captures the full screen, pass the full screenshot and use `mode =
"focused_item"` so Be My Lens applies the focused-item prompt.

## Setting Data, Type, Extras

If an image URI is available, the most compatible launch sends the same URI in
three places:

```lua
intent.setDataAndType(uri, "image/png")
intent.putExtra(Intent.EXTRA_STREAM, uri)
intent.putExtra("io.bemylens.app.extra.IMAGE_URI", uri)
intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
```

Be My Lens reads URI sources in this order:

1. `Intent.EXTRA_STREAM`
2. `io.bemylens.app.extra.IMAGE_URI`
3. `Intent.data`

So any one of these should work, but sending all three makes the first prototype
easier to diagnose.

## Prototype Storage Path

The user-facing Lua scripts save screenshots in this order:

1. Jieshuo/context external cache directory from `this.getExternalCacheDir()`
2. Jieshuo/context cache directory from `this.getCacheDir()`
3. `/sdcard/BeMyLens` as a temporary prototype fallback

The filename is timestamped and mode-specific:

```text
be_my_lens_<mode>_<timestamp>.png
```

The `/sdcard/` fallback is only for first-device testing. If it is the only
path that works, the final `.ppk` should revisit storage and URI grants before
release.

If saving or `this.getUriForFile(file)` fails for one location, the scripts try
the next location before reporting an error.

## Prototype Feedback

The user-facing scripts use short Android `Toast` messages plus `print(...)`.
They report:

- action started
- Be My Lens opening
- screenshot/capture/save/URI/launch failures

The diagnostic harness remains noisier and can still be used when something
breaks. In the user-facing scripts, set `DEBUG = true` for file path and URI
toasts.

## Focused Text And Bounds

Because Jieshuo scripts appear to receive a `node` object, the likely Android
accessibility-node shape is:

```lua
local text = node and node.getText and node.getText()
local desc = node and node.getContentDescription and node.getContentDescription()
```

Node bounds probably follow Android `AccessibilityNodeInfo`:

```lua
import "android.graphics.Rect"

local rect = Rect()
if node ~= nil then
  node.getBoundsInScreen(rect)
end
```

This is not used by the current Android contract. It becomes useful later if we
add a richer focused-item contract with bounds or text extras.

## Screenshot Format

The only public Jieshuo screenshot example found returns a bitmap-like value to
`onScreenCaptureDone`. That bitmap is saved by the Lua script using
`Bitmap.compress(...)`, then converted to a URI with `this.getUriForFile(...)`.

Practical implication: for the MVP, the Jieshuo side should convert the bitmap
to a PNG/JPEG file and pass a content URI to Be My Lens. This matches the stable
Android-side contract.

## Simplest First Tests

1. Set `TEST_MODE = "no_image"`.
   Run `prototypes/jieshuo/describe_image.lua` from Jieshuo. This verifies
   component/action/extras and should show Be My Lens' no-image error screen.

2. Run `prototypes/jieshuo/describe_screen.lua`.
   This should capture a screenshot, save it to a timestamped PNG, create a URI,
   and launch Be My Lens with
   `mode = "describe_screen"`.

3. Run `prototypes/jieshuo/describe_focused_item.lua`.
   This uses the same screenshot capture path, but launches Be My Lens with
   `mode = "focused_item"`.

4. If capture fails, use a hardcoded image URI from Jieshuo's existing
   screenshot/share behavior or another known readable image and call
   `launchBeMyLens(uri, "describe_screen", nil, true)`.

## Real-Device Test Checklist

Use a real device with Jieshuo installed and Be My Lens debug installed. The
first pass of this checklist has already succeeded.

1. Build and install Be My Lens debug APK.
   Example from this repo: `./gradlew :app:assembleDebug`, then install the APK
   from `app/build/outputs/apk/debug/app-debug.apk`.

2. Install or open Jieshuo and confirm its screen-reader service is active.

3. Import or run `prototypes/jieshuo/describe_image.lua` in Jieshuo for the
   diagnostic no-image test.

4. Run the no-image launch test with `TEST_MODE = "no_image"`.

5. Verify Be My Lens opens directly to `JieshuoEntryActivity`.

6. Verify Be My Lens shows the expected no-image error.

7. Import or run `prototypes/jieshuo/describe_screen.lua`.

8. Verify screenshot capture is attempted and succeeds according to toast/log
   output.

9. Verify the generated URI is logged. Set `DEBUG = true` in the action script
   if it needs to be surfaced as a toast.

10. Verify Be My Lens opens, processing starts, and the result is spoken.

11. Import or run `prototypes/jieshuo/describe_focused_item.lua`.

12. Verify the result uses the focused-item behavior, or record that Jieshuo only
   supplied a full-screen image.

13. Trigger repeated launches quickly and verify Be My Lens does not speak stale
   results from an older request.

14. Verify Be My Lens can read the URI/file. A backend result means URI reading,
   local copy, upload, and processing all worked.

## Expected Failures

`Activity does not open`

The explicit `ComponentName` may be wrong, Be My Lens may not be installed, the
debug package name may differ, or Jieshuo may block `startActivity` from that
script context.

`Activity opens but says no image received`

The no-image smoke test is working as intended, or the capture test launched
without a URI because screenshot capture, file save, or URI generation failed.
Check the toast/log line immediately before launch.

`Screenshot capture fails`

Jieshuo may not expose `this.getScreenShot(node, ...)` in this version, the
script may not be running in a context with screenshot permission, or the
callback method names may differ.

`File saves but Be My Lens cannot read it`

The URI may not grant read permission, `this.getUriForFile(file)` may not map
that path, or the saved location may be inaccessible. Prefer the Jieshuo cache
directory if it works; `/sdcard/` is only a fallback.

`Be My Lens reads old image`

The script may be reusing an old URI/file, Jieshuo may cache the URI, or the
timestamped filename did not change. Confirm the file path and URI toast include
a fresh timestamp.

`Result appears but is not spoken`

Check that `autoSpeak` is true, device TTS is enabled, and Be My Lens has not
been interrupted by a newer request. The Android entrypoint already guards
against stale requests speaking after a newer launch.

`Focused item gives full-screen result instead of cropped/focused result`

The current usable prototype uses Jieshuo screenshot capture and changes the
`mode` prompt. If a tester expects a cropped result, a better final `.ppk` may
need Jieshuo node bounds, a cropped focused-node screenshot, or extra focused
text/bounds in the Android contract.

## Packaging Path

The simplest path toward a reusable Jieshuo add-on is:

1. Keep two standalone actions:
   `describe_screen.lua` and `describe_focused_item.lua`.

2. Import each script into Jieshuo as a custom function/action and assign clear
   labels:
   `Describe screen with Be My Lens` and
   `Describe focused item with Be My Lens`.

3. Bind each action to a gesture, menu item, or Jieshuo extension command.

4. Test with Be My Lens installed from the debug APK first.

5. Once the import flow is repeatable, package the same two scripts into the
   smallest `.ppk` structure Jieshuo expects.

6. Keep `describe_image.lua` out of the tester-facing package unless a
   diagnostic action is intentionally needed.

The final package should avoid shared Lua modules unless Jieshuo's `.ppk`
loader is confirmed to resolve local imports reliably. Standalone scripts are
more repetitive, but they are safer for the first shareable blind-tester build.

## Unknowns Requiring Real Jieshuo Testing

- Exact `.ppk` directory/metadata format for the target Jieshuo build.
- Whether standalone scripts or shared Lua modules are preferred inside `.ppk`.
- Whether `this.getExternalCacheDir()` is available across all target Jieshuo
  versions and Android versions.
- Whether the fallback `/sdcard/BeMyLens` path is ever needed on tester devices.
- Whether `node` always refers to the focused item for extension launches across
  Jieshuo versions.
- Whether Jieshuo exposes a built-in cropped focused-node screenshot API.
- Whether Jieshuo exposes current focused text or bounds through direct helper
  APIs in addition to raw `node` methods.

## References

- [Accessible Android: Jieshuo Web Browser][accessible-android-browser]
- [Android `Intent` reference][android-intent]
- [Android `ComponentName` reference][android-component-name]
- [Android `AccessibilityService.takeScreenshot(...)` reference][android-accessibility-screenshot]
- [4PDA forum snippet showing a Jieshuo screenshot/share plugin][jieshuo-forum-screenshot]

[accessible-android-browser]: https://accessibleandroid.com/jieshuo-web-browser/
[android-intent]: https://developer.android.com/reference/android/content/Intent
[android-component-name]: https://developer.android.com/reference/android/content/ComponentName
[android-accessibility-screenshot]: https://developer.android.com/reference/android/accessibilityservice/AccessibilityService#takeScreenshot(int,%20java.util.concurrent.Executor,%20android.accessibilityservice.AccessibilityService.TakeScreenshotCallback)
[jieshuo-forum-screenshot]: https://4pda.to/forum/index.php?showtopic=1083937&st=4180
