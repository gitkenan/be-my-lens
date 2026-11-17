# Prompts

Be My Lens serves Arabic-speaking users only. Arabic is the only language the app and
backend support, and there is deliberately no setting to change it.

| Directory | Status |
| --- | --- |
| `ar/` | **In use.** The backend always loads these (`PROMPT_LOCALE = "ar"` in `app.py`). |
| `en/` | **Not used.** An English reference kept only to make adding a language easier later. It is never loaded, and nothing tests that it stays in step with `ar/`, so review it before reusing it. |

Each directory holds the same four files, one per backend task: `describe_image.txt`,
`read_contents.txt`, `ask_question.txt` and `translate_text.txt`.

## Adding a language later

A prompt directory alone is not enough. Supporting another language means changing:

1. **Backend language selection.** `app.py` hard-codes `PROMPT_LOCALE = "ar"`. Make it
   configurable (or choose it per request), and fail fast on unknown values rather than
   falling back silently.
2. **Backend text outside the prompts.** The fixed questions (`DESCRIBE_IMAGE_QUESTION`,
   `READ_CONTENTS_QUESTION`) and the error details returned to clients in `app.py` are
   Arabic.
3. **Translation target.** `translate_text.txt` translates into Arabic, in both
   directories.
4. **Android app.** UI strings exist only in `app/src/main/res/values/strings.xml`
   (Arabic), and `TtsCatalog.arabicVoices` lists only Arabic text-to-speech voices.
5. **Jieshuo plugins.** The labels and spoken messages in `dist/jieshuo-lua/` are Arabic.
6. **Tests.** `server/tests/test_service_configuration.py` asserts Arabic-only behaviour.
