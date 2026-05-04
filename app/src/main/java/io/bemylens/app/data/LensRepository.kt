package io.bemylens.app.data

import android.content.Context
import android.net.Uri
import io.bemylens.app.BuildConfig
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit

class LensRepository(
    private val context: Context,
) {
    private val api: LensApi by lazy {
        val logger = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }

        val client = OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(90, TimeUnit.SECONDS)
            .writeTimeout(90, TimeUnit.SECONDS)
            .addInterceptor(logger)
            .build()

        Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL)
            .client(client)
            .addConverterFactory(LensJson.converterFactory())
            .build()
            .create(LensApi::class.java)
    }

    suspend fun describeImage(imageUri: Uri): DescribeResponse {
        return api.describe(imagePartFor(imageUri))
    }

    suspend fun readContents(imageUri: Uri): ReadContentsResponse {
        return api.readContents(imagePartFor(imageUri))
    }

    suspend fun askQuestion(imageUri: Uri, question: String): ChatResponse {
        return api.askQuestion(
            image = imagePartFor(imageUri),
            question = question.toRequestBody("text/plain".toMediaType()),
        )
    }

    suspend fun followUp(sessionId: String, question: String): FollowUpResponse {
        return api.followUp(
            FollowUpRequest(
                sessionId = sessionId,
                question = question,
            ),
        )
    }

    private fun imagePartFor(imageUri: Uri): MultipartBody.Part {
        val imageBytes = readCompressedJpeg(context, imageUri)
        val requestBody = imageBytes.toRequestBody("image/jpeg".toMediaType())
        return MultipartBody.Part.createFormData(
            name = "image",
            filename = "image.jpg",
            body = requestBody,
        )
    }
}
