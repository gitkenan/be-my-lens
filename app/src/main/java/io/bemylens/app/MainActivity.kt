package io.bemylens.app

import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import java.util.Locale

class MainActivity : ComponentActivity() {
    private var speaker: TextToSpeech? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i("BeMyLens", "Starting build ${BuildConfig.BUILD_MARKER}")
        enableEdgeToEdge()

        speaker = TextToSpeech(this) { status ->
            if (status == TextToSpeech.SUCCESS) {
                speaker?.language = Locale("ar")
            }
        }

        setContent {
            BeMyLensApp(
                onSpeakText = { text ->
                    speaker?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "be-my-lens")
                },
            )
        }
    }

    override fun onDestroy() {
        speaker?.stop()
        speaker?.shutdown()
        speaker = null
        super.onDestroy()
    }
}
