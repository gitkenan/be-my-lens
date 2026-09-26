package io.bemylens.app

import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import io.bemylens.app.tts.TtsSpeaker

class MainActivity : ComponentActivity() {
    private val speaker by lazy { TtsSpeaker.getInstance(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i("BeMyLens", "Starting build ${BuildConfig.BUILD_MARKER}")
        enableEdgeToEdge()

        setContent {
            BeMyLensApp(speaker = speaker)
        }
    }
}
