package io.bemylens.app.data

import retrofit2.http.Body
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part

data class DescribeResponse(
    val sessionId: String,
    val description: String,
)

data class ReadContentsResponse(
    val sessionId: String,
    val contents: String,
)

data class ChatResponse(
    val sessionId: String,
    val answer: String,
)

data class FollowUpRequest(
    val sessionId: String,
    val question: String,
)

data class FollowUpResponse(
    val answer: String,
)

interface LensApi {
    @Multipart
    @POST("describe")
    suspend fun describe(
        @Part image: okhttp3.MultipartBody.Part,
    ): DescribeResponse

    @Multipart
    @POST("read")
    suspend fun readContents(
        @Part image: okhttp3.MultipartBody.Part,
    ): ReadContentsResponse

    @Multipart
    @POST("chat")
    suspend fun askQuestion(
        @Part image: okhttp3.MultipartBody.Part,
        @Part("question") question: okhttp3.RequestBody,
    ): ChatResponse

    @POST("followup")
    suspend fun followUp(
        @Body request: FollowUpRequest,
    ): FollowUpResponse
}
