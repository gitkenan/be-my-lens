package io.bemylens.app.tts

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.activity.compose.BackHandler
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.bemylens.app.R
import java.util.Locale

/**
 * Lets the user pick the installed TTS engine and one of its Arabic voices, then hear the
 * result. Options are plain `selectable` radio rows, so Jieshuo and TalkBack announce the
 * label and the selected state on their own without custom announcements.
 */
@Composable
fun TtsSettingsScreen(
    speaker: TtsSpeaker,
    onBack: () -> Unit,
) {
    val state by speaker.state.collectAsStateWithLifecycle()
    val testPhrase = stringResource(R.string.settings_test_phrase)
    BackHandler(onBack = onBack)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            IconButton(
                onClick = onBack,
                modifier = Modifier.size(56.dp),
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = stringResource(R.string.action_back),
                )
            }
            Text(
                text = stringResource(R.string.settings_title),
                modifier = Modifier.semantics { heading() },
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
        }

        EngineSection(
            state = state,
            onSelectEngine = speaker::selectEngine,
        )

        VoiceSection(
            state = state,
            onSelectVoice = speaker::selectVoice,
        )

        Button(
            onClick = { speaker.speak(testPhrase) },
            enabled = state.isReady,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 56.dp),
        ) {
            Text(stringResource(R.string.action_test_voice))
        }
    }
}

@Composable
private fun EngineSection(
    state: TtsSettingsState,
    onSelectEngine: (String?) -> Unit,
) {
    SettingsCard(titleRes = R.string.settings_engine_title) {
        if (state.engines.isEmpty()) {
            Note(stringResource(R.string.settings_engine_none))
        } else {
            OptionRow(
                selected = state.engineComponent == null,
                onClick = { onSelectEngine(null) },
                title = stringResource(R.string.settings_engine_system_default),
            )
            state.engines.forEach { engine ->
                OptionRow(
                    selected = state.engineComponent == engine.componentName,
                    onClick = { onSelectEngine(engine.componentName) },
                    title = engine.label,
                    subtitle = engine.packageName,
                )
            }
        }
    }
}

@Composable
private fun VoiceSection(
    state: TtsSettingsState,
    onSelectVoice: (String?) -> Unit,
) {
    SettingsCard(titleRes = R.string.settings_voice_title) {
        when {
            !state.isInitialised -> LoadingRow()
            !state.isReady -> Note(stringResource(R.string.settings_engine_unavailable))
            state.voices.isEmpty() -> Note(stringResource(R.string.settings_voice_none))
            else -> {
                OptionRow(
                    selected = state.voiceId == null,
                    onClick = { onSelectVoice(null) },
                    title = stringResource(R.string.settings_voice_system_default),
                )
                state.voices.forEach { voice ->
                    OptionRow(
                        selected = state.voiceId == voice.voiceId,
                        onClick = { onSelectVoice(voice.voiceId) },
                        title = voice.localeLabel().ifBlank { voice.languageTag },
                        subtitle = voice.name.takeIf { it.isNotBlank() },
                    )
                }
            }
        }
    }
}

@Composable
private fun SettingsCard(
    titleRes: Int,
    content: @Composable () -> Unit,
) {
    Card(shape = RoundedCornerShape(24.dp)) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = stringResource(titleRes),
                modifier = Modifier.semantics { heading() },
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
            )
            content()
        }
    }
}

@Composable
private fun OptionRow(
    selected: Boolean,
    onClick: () -> Unit,
    title: String,
    subtitle: String? = null,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .selectable(
                selected = selected,
                role = Role.RadioButton,
                onClick = onClick,
            )
            .heightIn(min = 56.dp)
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // The row owns the click and the selected state, so the button itself is not
        // interactive: screen readers get one target per option instead of two.
        RadioButton(selected = selected, onClick = null)
        Column(
            modifier = Modifier.padding(start = 12.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.bodyLarge,
            )
            subtitle?.let { text ->
                Text(
                    text = text,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun Note(text: String) {
    Text(
        text = text,
        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun LoadingRow() {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 56.dp)
            .semantics { liveRegion = LiveRegionMode.Polite },
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        CircularProgressIndicator(modifier = Modifier.size(24.dp))
        Text(
            text = stringResource(R.string.settings_loading),
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

/** Localized locale name, e.g. `العربية (السعودية)` on an Arabic device. */
private fun TtsVoiceOption.localeLabel(): String {
    if (languageTag.isBlank()) return ""
    return Locale.forLanguageTag(languageTag).getDisplayName(Locale.getDefault())
}
