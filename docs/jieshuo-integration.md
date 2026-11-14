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
| `android.intent.extra.STREAM` | `Uri` | Yes for image modes | Standard Android share image URI. |
| `io.bemylens.app.extra.IMAGE_URI` | `Uri` or URI string | Yes for image modes | Custom direct-launch image URI. |
| `Intent.data` | `Uri` | Yes for image modes | Supports `content://` and `file://` schemes. |
| `io.bemylens.app.extra.TEXT` | `String` | Yes for `translate_text` | Raw text to translate, taken from the caller's selected/focused text. |
| `mode` | `String` | No | Defaults to `describe_screen`. |
| `prompt` | `String` | Required only for `custom_prompt` | Optional mode-specific instruction. |
| `autoSpeak` | `Boolean` | No | Defaults to `true`. |

Image URI lookup order:

1. `Intent.EXTRA_STREAM`
2. `io.bemylens.app.extra.IMAGE_URI`
3. `Intent.data`

The receiving Activity copies the image into app cache before processing, so callers only need to grant temporary read permission for launch. `translate_text` does not need an image at all.

## Supported Modes

| Mode | Behavior without `prompt` | Behavior with `prompt` |
| --- | --- | --- |
| `describe_screen` | Uses the normal image description endpoint. | Uses the image chat endpoint with the provided prompt. |
| `focused_item` | Uses a focused-item prompt: describe only the focused item/control and ignore unrelated background content unless necessary. | Uses the provided prompt. |
| `read_text` | Uses the existing read/OCR-style endpoint. | Uses the image chat endpoint with the provided prompt. |
| `custom_prompt` | Invalid. Shows a clear error. | Uses the image chat endpoint with the provided prompt. |
| `translate_text` | Translates the text in `io.bemylens.app.extra.TEXT` through the text-only backend endpoint. No image is required or used. | `prompt` is ignored. |

Unsupported mode values are rejected with a validation error. `translate_text` without a usable `TEXT` extra is rejected with a no-text-received error.

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

Translate selected text mode, no image URI needed:

```bash
adb shell am start \
  -a io.bemylens.app.action.DESCRIBE_IMAGE \
  --es mode translate_text \
  --es io.bemylens.app.extra.TEXT "Exit 12A is 300 meters ahead" \
  -p io.bemylens.app
```

## Expected Jieshuo `.ppk` Behavior

A Jieshuo extension should:

1. Capture or obtain a screenshot/cropped image URI for image modes, or read the selected/focused text for `translate_text`.
2. Launch `io.bemylens.app.action.DESCRIBE_IMAGE`.
3. Pass the image through `Intent.EXTRA_STREAM`, `io.bemylens.app.extra.IMAGE_URI`, or `Intent.data` for image modes, or the text through `io.bemylens.app.extra.TEXT` for `translate_text`.
4. Add `FLAG_GRANT_READ_URI_PERMISSION` when passing an image URI.
5. Set `mode` to one of `describe_screen`, `focused_item`, `read_text`, `custom_prompt`, or `translate_text`.
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

For selected text:

```text
action = io.bemylens.app.action.DESCRIBE_IMAGE
mode = translate_text
autoSpeak = true
text = focused node text or content description
```

## Current Limitations

- Image modes require an image URI. `translate_text` requires the `io.bemylens.app.extra.TEXT` extra instead and does not accept raw bitmap bytes or base64 image payloads.
- `translate_text` translates into the backend's configured locale (`PROMPT_LOCALE`, Arabic by default) and does not let the caller choose a target language yet.
- Processing runs in the exported Activity, not a foreground service.
- There is no Android accessibility service in Be My Lens.
- The backend keeps image sessions in memory only.
- The entry screen is intentionally minimal and separate from the main app UI.
- `file://` is accepted for testing and compatibility, but `content://` with temporary read permission is preferred.

## Why Image URI Instead Of App Internals

Android apps cannot generally inspect arbitrary other app screens, view hierarchies, or private UI internals. A screen reader or automation layer may have more context, but passing that directly would require a larger, Jieshuo-specific contract and careful privacy handling.

For the MVP, a screenshot/image URI is the most stable boundary for image understanding, and the selected-text extra is the stable boundary for text translation: Jieshuo owns capture and focus context, Be My Lens owns image understanding, text translation, speech, and backend communication.
