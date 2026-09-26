package io.bemylens.app.tts

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.speech.tts.TextToSpeech

/**
 * Lists the text-to-speech engines installed on the device. Nothing is hard coded:
 * every engine that answers the platform TTS service intent shows up in settings.
 * Needs the `android.intent.action.TTS_SERVICE` entry in the manifest `<queries>` block
 * on Android 11+.
 */
object TtsEngines {
    fun installed(context: Context): List<TtsEngineOption> {
        val packageManager = context.packageManager
        val services = runCatching {
            packageManager.queryIntentServices(Intent(TextToSpeech.Engine.INTENT_ACTION_TTS_SERVICE), 0)
        }.getOrNull().orEmpty()

        val engines = services.mapNotNull { resolveInfo ->
            val serviceInfo = resolveInfo.serviceInfo ?: return@mapNotNull null
            TtsEngineOption(
                componentName = ComponentName(serviceInfo.packageName, serviceInfo.name)
                    .flattenToString(),
                packageName = serviceInfo.packageName,
                label = resolveInfo.loadLabel(packageManager)
                    ?.toString()
                    ?.takeIf { it.isNotBlank() }
                    ?: serviceInfo.packageName,
            )
        }

        return TtsCatalog.orderedEngines(engines)
    }
}
