package io.bemylens.app.data

import retrofit2.http.Body
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part

data class DescribeResponse(
    val sessionId: String,
    val description: String,
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

    @POST("followup")
    suspend fun followUp(
        @Body request: FollowUpRequest,
    ): FollowUpResponse
}
