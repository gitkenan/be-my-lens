package io.bemylens.app

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import io.bemylens.app.ui.LensViewModel
import java.io.File

@Composable
fun BeMyLensApp(
    onSpeakText: (String) -> Unit,
    viewModel: LensViewModel = viewModel(),
) {
    MaterialTheme {
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
            Surface(modifier = Modifier.fillMaxSize()) {
                LensScreen(
                    viewModel = viewModel,
                    onSpeakText = onSpeakText,
                )
            }
        }
    }
}

@Composable
private fun LensScreen(
    viewModel: LensViewModel,
    onSpeakText: (String) -> Unit,
) {
    val context = LocalContext.current
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    var pendingCameraUri by remember { mutableStateOf<Uri?>(null) }

    val takePhotoLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicture(),
    ) { success ->
        if (success) {
            pendingCameraUri?.let(viewModel::onImageSelected)
        }
    }

    val photoPickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
    ) { uri ->
        uri?.let(viewModel::onImageSelected)
    }

    fun launchCameraCapture() {
        val imageDir = File(context.cacheDir, "camera").apply { mkdirs() }
        val imageFile = File.createTempFile("lens_capture_", ".jpg", imageDir)
        val imageUri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            imageFile,
        )
        pendingCameraUri = imageUri
        takePhotoLauncher.launch(imageUri)
    }

    Scaffold { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background)
                .padding(innerPadding),
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .statusBarsPadding()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 20.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Header()

                if (state.selectedImageUri == null) {
                    EmptyState(
                        onTakePhoto = ::launchCameraCapture,
                        onChoosePhoto = {
                            photoPickerLauncher.launch(
                                PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly),
                            )
                        },
                    )
                } else {
                    SelectedImagePanel(
                        imageUri = state.selectedImageUri!!,
                        onDescribe = viewModel::describeSelectedImage,
                        onAskQuestion = viewModel::openChat,
                        onReadContents = viewModel::readSelectedImage,
                        isLoading = state.isLoading,
                    )
                }

                state.errorMessage?.let { error ->
                    MessageCard(
                        title = stringResource(R.string.error_something_went_wrong),
                        body = error,
                        containerColor = MaterialTheme.colorScheme.errorContainer,
                    )
                }

                state.latestAnswer?.let { answer ->
                    AnswerCard(
                        answer = answer,
                        onSpeak = { onSpeakText(answer) },
                    )
                }

                if (state.selectedImageUri != null && state.isChatOpen) {
                    FollowUpSection(
                        enabled = !state.isLoading,
                        currentQuestion = state.followUpQuestion,
                        messages = state.messages,
                        onQuestionChange = viewModel::updateFollowUpQuestion,
                        onSend = { viewModel.sendFollowUp() },
                        onShortcut = viewModel::sendShortcut,
                    )
                }
            }

            if (state.isLoading) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Color.Black.copy(alpha = 0.2f)),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator()
                }
            }
        }
    }
}

@Composable
private fun Header() {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            text = stringResource(R.string.app_name),
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = stringResource(R.string.home_tagline),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (BuildConfig.DEBUG) {
            Text(
                text = stringResource(
                    R.string.debug_build_api,
                    BuildConfig.BUILD_MARKER,
                    BuildConfig.API_BASE_URL,
                ),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun EmptyState(
    onTakePhoto: () -> Unit,
    onChoosePhoto: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        shape = RoundedCornerShape(24.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                text = stringResource(R.string.empty_state_title),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = stringResource(R.string.empty_state_body),
                style = MaterialTheme.typography.bodyMedium,
            )
            Button(
                onClick = onTakePhoto,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
            ) {
                Text(stringResource(R.string.action_take_photo))
            }
            OutlinedButton(
                onClick = onChoosePhoto,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
            ) {
                Text(stringResource(R.string.action_choose_photo))
            }
        }
    }
}

@Composable
private fun SelectedImagePanel(
    imageUri: Uri,
    onDescribe: () -> Unit,
    onAskQuestion: () -> Unit,
    onReadContents: () -> Unit,
    isLoading: Boolean,
) {
    Card(shape = RoundedCornerShape(24.dp)) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            AsyncImage(
                model = imageUri,
                contentDescription = stringResource(R.string.selected_image_preview),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(280.dp),
                contentScale = ContentScale.Crop,
            )
            Column(
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Button(
                    onClick = onDescribe,
                    enabled = !isLoading,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                ) {
                    Text(stringResource(R.string.action_describe_image))
                }
                OutlinedButton(
                    onClick = onAskQuestion,
                    enabled = !isLoading,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                ) {
                    Text(stringResource(R.string.action_ask_question))
                }
                OutlinedButton(
                    onClick = onReadContents,
                    enabled = !isLoading,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                ) {
                    Text(stringResource(R.string.action_read_contents))
                }
            }
        }
    }
}

@Composable
private fun AnswerCard(
    answer: String,
    onSpeak: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
        shape = RoundedCornerShape(24.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.answer_latest),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = answer,
                style = MaterialTheme.typography.bodyLarge,
            )
            TextButton(onClick = onSpeak, contentPadding = PaddingValues(0.dp)) {
                Text(stringResource(R.string.action_read_aloud))
            }
        }
    }
}

@Composable
private fun FollowUpSection(
    enabled: Boolean,
    currentQuestion: String,
    messages: List<ChatMessage>,
    onQuestionChange: (String) -> Unit,
    onSend: () -> Unit,
    onShortcut: (String) -> Unit,
) {
    val shortcuts = listOf(
        stringResource(R.string.shortcut_objects),
        stringResource(R.string.shortcut_hazards),
        stringResource(R.string.shortcut_more_detail),
    )

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            text = stringResource(R.string.question_section_title),
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.SemiBold,
        )

        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(shortcuts) { shortcut ->
                AssistChip(
                    onClick = { onShortcut(shortcut) },
                    enabled = enabled,
                    label = { Text(shortcut) },
                )
            }
        }

        OutlinedTextField(
            value = currentQuestion,
            onValueChange = onQuestionChange,
            modifier = Modifier.fillMaxWidth(),
            enabled = enabled,
            label = { Text(stringResource(R.string.question_label)) },
            placeholder = { Text(stringResource(R.string.question_placeholder)) },
        )

        Button(
            onClick = onSend,
            enabled = enabled && currentQuestion.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.action_send_question))
        }

        if (messages.isNotEmpty()) {
            HorizontalDivider()
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                messages.forEach { message ->
                    MessageBubble(message = message)
                }
            }
        }
    }
}

@Composable
private fun MessageBubble(message: ChatMessage) {
    val isAssistant = message.role == ChatRole.ASSISTANT
    val background = if (isAssistant) {
        MaterialTheme.colorScheme.secondaryContainer
    } else {
        MaterialTheme.colorScheme.surfaceVariant
    }

    Card(
        colors = CardDefaults.cardColors(containerColor = background),
        shape = RoundedCornerShape(18.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(
                text = if (isAssistant) {
                    stringResource(R.string.chat_role_assistant)
                } else {
                    stringResource(R.string.chat_role_user)
                },
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = message.text,
                style = MaterialTheme.typography.bodyLarge,
            )
        }
    }
}

@Composable
private fun MessageCard(
    title: String,
    body: String,
    containerColor: Color,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = containerColor),
        shape = RoundedCornerShape(20.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Text(text = body, style = MaterialTheme.typography.bodyMedium)
        }
    }
}
