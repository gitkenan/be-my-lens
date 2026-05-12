# Jieshuo Lua Prototype Notes

This note captures the current discovery work for a future Jieshuo `.ppk`
extension. It is intentionally a prototype-level note, not the final extension
contract.

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

These APIs still need real-device validation because they appear to be
Jieshuo-specific and are not documented in an official English SDK.

Android's platform APIs support the underlying pieces used here:

- explicit Activity targeting with `Intent.setComponent(...)`
- application-specific actions with `Intent.setAction(...)`
- data/type image URI delivery with `Intent.setDataAndType(...)`
- package scoping with `Intent.setPackage(...)`
- `ComponentName(package, className)` construction
- accessibility screenshot capture in native Android accessibility services
  via `AccessibilityService.takeScreenshot(...)`

## Can Jieshuo Launch Be My Lens?

Most likely yes.

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

The runnable prototype is:

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

Full screen or focused-item screenshot path:

```lua
require "import"
import "android.content.Intent"
import "android.content.ComponentName"
import "android.graphics.Bitmap"
import "java.io.File"
import "java.io.FileOutputStream"

local packageName = "io.bemylens.app"
local activityName = "io.bemylens.app.JieshuoEntryActivity"
local action = "io.bemylens.app.action.DESCRIBE_IMAGE"
local extraImageUri = "io.bemylens.app.extra.IMAGE_URI"

local function launchBeMyLens(imageUri, mode, prompt, autoSpeak)
  local intent = Intent()
    .setAction(action)
    .setComponent(ComponentName(packageName, activityName))
    .setPackage(packageName)
    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    .putExtra("mode", mode or "describe_screen")
    .putExtra("autoSpeak", autoSpeak ~= false)

  if prompt ~= nil and prompt ~= "" then
    intent.putExtra("prompt", prompt)
  end

  if imageUri ~= nil then
    intent.setDataAndType(imageUri, "image/png")
    intent.putExtra(Intent.EXTRA_STREAM, imageUri)
    intent.putExtra(extraImageUri, imageUri)
  end

  this.startActivity(intent)
end

this.getScreenShot(node, {
  onScreenCaptureDone = function(bitmap)
    local file = File("/sdcard/", "be_my_lens_jieshuo_<timestamp>.png")
    bitmap.compress(Bitmap.CompressFormat.PNG, 90, FileOutputStream(file))
    local uri = this.getUriForFile(file)
    launchBeMyLens(uri, "describe_screen", nil, true)
  end
})
```

Focused-item mode probably uses the same capture API first:

```lua
launchBeMyLens(uri, "focused_item", nil, true)
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

The Lua prototype tries to save screenshots in this order:

1. Jieshuo/context external cache directory from `this.getExternalCacheDir()`
2. Jieshuo/context cache directory from `this.getCacheDir()`
3. `/sdcard/` as a temporary prototype fallback

The filename is timestamped:

```text
be_my_lens_jieshuo_<timestamp>.png
```

The `/sdcard/` fallback is only for first-device testing. If it is the only
path that works, the final `.ppk` should revisit storage and URI grants before
release.

## Prototype Feedback

The script uses both `print(...)` and Android `Toast` messages where available.
It reports:

- starting launch
- screenshot capture attempted
- screenshot capture succeeded or failed
- file save path
- generated URI
- `startActivity` call
- exception messages from launch, capture, save, and URI generation

This is intentionally noisy so the first blind-user testing pass has audible or
debuggable progress feedback.

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
   Run the script from Jieshuo. This verifies component/action/extras and should
   show Be My Lens' no-image error screen.

2. Set `TEST_MODE = "describe_screen"`.
   Run the script from Jieshuo. This should capture a screenshot, save it to a
   timestamped PNG, create a URI, and launch Be My Lens with
   `mode = "describe_screen"`.

3. Set `TEST_MODE = "focused_item"`.
   Run the script from Jieshuo. This currently uses the same screenshot capture
   path, but launches Be My Lens with `mode = "focused_item"`.

4. If capture fails, use a hardcoded image URI from Jieshuo's existing
   screenshot/share behavior or another known readable image and call
   `launchBeMyLens(uri, "describe_screen", nil, true)`.

## Real-Device Test Checklist

Use a real device with Jieshuo installed and Be My Lens debug installed.

1. Build and install Be My Lens debug APK.
   Example from this repo: `./gradlew :app:assembleDebug`, then install the APK
   from `app/build/outputs/apk/debug/app-debug.apk`.

2. Install or open Jieshuo and confirm its screen-reader service is active.

3. Import or run `prototypes/jieshuo/describe_image.lua` in Jieshuo.

4. Run the no-image launch test with `TEST_MODE = "no_image"`.

5. Verify Be My Lens opens directly to `JieshuoEntryActivity`.

6. Verify Be My Lens shows the expected no-image error.

7. Run the full-screen screenshot test with `TEST_MODE = "describe_screen"`.

8. Verify screenshot capture is attempted and succeeds according to toast/log
   output.

9. Verify the generated URI is logged/toasted.

10. Verify Be My Lens opens, processing starts, and the result is spoken.

11. Run the focused-item screenshot test with `TEST_MODE = "focused_item"`.

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

The current prototype likely captures the full screen and only changes the
`mode` prompt. A better final `.ppk` may need Jieshuo node bounds, a cropped
focused-node screenshot, or extra focused text/bounds in the Android contract.

## Unknowns Requiring Real Jieshuo Testing

- Whether current Jieshuo versions still expose `this.getScreenShot(node, ...)`.
- Whether screenshot capture returns a mutable Android `Bitmap` or another
  wrapper type.
- Whether `this.getUriForFile(file)` grants temporary read permission to Be My
  Lens reliably, or whether `Intent.FLAG_GRANT_READ_URI_PERMISSION` is enough.
- Whether storage paths like `/sdcard/` are writable on the target Android
  versions without extra permission.
- Whether `node` always refers to the focused item for extension launches.
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
