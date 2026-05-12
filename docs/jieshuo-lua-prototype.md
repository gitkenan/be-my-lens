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
    local file = File("/sdcard/", "be_my_lens_jieshuo.png")
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

1. Launch without image.
   This verifies component/action/extras and should show Be My Lens' no-image
   error screen.

2. Launch with a hardcoded image URI.
   Use a URI obtained from an existing image share or Jieshuo's own
   `this.getUriForFile(File(...))`.

3. Capture screenshot, save to PNG, call `this.getUriForFile(file)`, then launch
   Be My Lens with `mode = "describe_screen"`.

4. Repeat with `mode = "focused_item"`.

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
