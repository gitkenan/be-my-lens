# Jieshuo Integration Contract

Be My Lens exposes a small Android intent contract for screen-reader extensions that can provide a screenshot or cropped image URI. The first supported caller is expected to be a Jieshuo `.ppk` extension, but the same contract works for any Android app that can launch an intent with read access to an image URI.

## Supported Action

```text
io.bemylens.app.action.DESCRIBE_IMAGE
```

The Activity also supports the standard Android share action:

```text
android.intent.action.SEND
```

with MIME type:

```text
image/*
```

## Supported Extras

| Key | Type | Required | Notes |
| --- | --- | --- | --- |
| `android.intent.extra.STREAM` | `Uri` | Yes, unless another image URI source is used | Standard Android share image URI. |
| `io.bemylens.app.extra.IMAGE_URI` | `Uri` or URI string | Yes, unless `EXTRA_STREAM` or `Intent.data` is used | Custom direct-launch image URI. |
| `Intent.data` | `Uri` | Yes, unless an image extra is used | Supports `content://` and `file://` schemes. |
| `mode` | `String` | No | Defaults to `describe_screen`. |
| `prompt` | `String` | Required only for `custom_prompt` | Optional mode-specific instruction. |
| `autoSpeak` | `Boolean` | No | Defaults to `true`. |

Image URI lookup order:

1. `Intent.EXTRA_STREAM`
2. `io.bemylens.app.extra.IMAGE_URI`
3. `Intent.data`

The receiving Activity copies the image into app cache before processing, so callers only need to grant temporary read permission for launch.

## Supported Modes

| Mode | Behavior without `prompt` | Behavior with `prompt` |
| --- | --- | --- |
| `describe_screen` | Uses the normal image description endpoint. | Uses the image chat endpoint with the provided prompt. |
| `focused_item` | Uses a focused-item prompt: describe only the focused item/control and ignore unrelated background content unless necessary. | Uses the provided prompt. |
| `read_text` | Uses the existing read/OCR-style endpoint. | Uses the image chat endpoint with the provided prompt. |
| `custom_prompt` | Invalid. Shows a clear error. | Uses the image chat endpoint with the provided prompt. |

Unsupported mode values are rejected with a validation error.

## ADB Examples

Replace `$CONTENT_URI` with a readable image URI on the device, for example a MediaStore image URI.

Standard Android share intent:

```bash
adb shell am start --grant-read-uri-permission \
  -a android.intent.action.SEND \
  -t image/jpeg \
  --eu android.intent.extra.STREAM "$CONTENT_URI" \
  -p io.bemylens.app
```

Custom action with `EXTRA_STREAM`:

```bash
adb shell am start --grant-read-uri-permission \
  -a io.bemylens.app.action.DESCRIBE_IMAGE \
  -t image/jpeg \
  --eu android.intent.extra.STREAM "$CONTENT_URI" \
  --es mode describe_screen \
  --ez autoSpeak true \
  -p io.bemylens.app
```

Custom action with custom image URI extra:

```bash
adb shell am start --grant-read-uri-permission \
  -a io.bemylens.app.action.DESCRIBE_IMAGE \
  --eu io.bemylens.app.extra.IMAGE_URI "$CONTENT_URI" \
  --es mode focused_item \
  --ez autoSpeak true \
  -p io.bemylens.app
```

Custom action with `Intent.data` and MIME type, equivalent to `setDataAndType(...)`:

```bash
adb shell am start --grant-read-uri-permission \
  -a io.bemylens.app.action.DESCRIBE_IMAGE \
  -d "$CONTENT_URI" \
  -t image/jpeg \
  --es prompt "Describe this screen" \
  -p io.bemylens.app
```

Custom action with `Intent.data` only, equivalent to `setData(...)`:

```bash
adb shell am start --grant-read-uri-permission \
  -a io.bemylens.app.action.DESCRIBE_IMAGE \
  -d "$CONTENT_URI" \
  -p io.bemylens.app
```

Read text mode:

```bash
adb shell am start --grant-read-uri-permission \
  -a io.bemylens.app.action.DESCRIBE_IMAGE \
  -t image/jpeg \
  --eu android.intent.extra.STREAM "$CONTENT_URI" \
  --es mode read_text \
  -p io.bemylens.app
```

Custom prompt mode:

```bash
adb shell am start --grant-read-uri-permission \
  -a io.bemylens.app.action.DESCRIBE_IMAGE \
  -t image/jpeg \
  --eu android.intent.extra.STREAM "$CONTENT_URI" \
  --es mode custom_prompt \
  --es prompt "Describe the selected button and say whether it looks enabled." \
  -p io.bemylens.app
```

## Expected Jieshuo `.ppk` Behavior

A future Jieshuo extension should:

1. Capture or obtain a screenshot/cropped image URI.
2. Launch `io.bemylens.app.action.DESCRIBE_IMAGE`.
3. Pass the image through `Intent.EXTRA_STREAM`, `io.bemylens.app.extra.IMAGE_URI`, or `Intent.data`.
4. Add `FLAG_GRANT_READ_URI_PERMISSION`.
5. Set `mode` to one of `describe_screen`, `focused_item`, `read_text`, or `custom_prompt`.
6. Optionally set `prompt` and `autoSpeak`.

For a first Jieshuo MVP:

```text
action = io.bemylens.app.action.DESCRIBE_IMAGE
mode = describe_screen
autoSpeak = true
image = screenshot content URI
```

For focused item:

```text
action = io.bemylens.app.action.DESCRIBE_IMAGE
mode = focused_item
autoSpeak = true
image = cropped focused-item screenshot URI, or full screenshot if cropping is unavailable
```

## Current Limitations

- The contract requires an image URI. Be My Lens does not currently receive raw bitmap bytes, base64 image payloads, or text-only accessibility node data.
- Processing runs in the exported Activity, not a foreground service.
- There is no Android accessibility service in Be My Lens.
- The backend keeps image sessions in memory only.
- The entry screen is intentionally minimal and separate from the main app UI.
- `file://` is accepted for testing and compatibility, but `content://` with temporary read permission is preferred.

## Why Image URI Instead Of App Internals

Android apps cannot generally inspect arbitrary other app screens, view hierarchies, or private UI internals. A screen reader or automation layer may have more context, but passing that directly would require a larger, Jieshuo-specific contract and careful privacy handling.

For the MVP, a screenshot/image URI is the most stable boundary: Jieshuo owns capture and focus context, Be My Lens owns image understanding, speech, and backend communication.
