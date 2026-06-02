package com.aubeetoilee.aubevideo.net

import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.HTTP
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

interface AubeVideoApi {

    // ---- Auth ----
    @POST("api/v1/auth/login")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @POST("api/v1/auth/logout")
    suspend fun logout(): Map<String, Boolean>

    @GET("api/v1/auth/me")
    suspend fun me(): ChannelDto

    // ---- Feeds ----
    @GET("api/v1/feed")
    suspend fun feed(
        @Query("category") category: String? = null,
        @Query("page") page: Int = 1,
        @Query("per_page") perPage: Int = 24,
    ): Page<VideoDto>

    @GET("api/v1/trending")
    suspend fun trending(
        @Query("page") page: Int = 1, @Query("per_page") perPage: Int = 24,
    ): Page<VideoDto>

    @GET("api/v1/shorts")
    suspend fun shorts(
        @Query("page") page: Int = 1, @Query("per_page") perPage: Int = 20,
    ): Page<VideoDto>

    @GET("api/v1/subscriptions")
    suspend fun subscriptionsFeed(
        @Query("page") page: Int = 1, @Query("per_page") perPage: Int = 24,
    ): Page<VideoDto>

    @GET("api/v1/recommended")
    suspend fun recommended(
        @Query("page") page: Int = 1, @Query("per_page") perPage: Int = 24,
    ): Page<VideoDto>

    // ---- Search ----
    @GET("api/v1/search")
    suspend fun search(
        @Query("q") q: String,
        @Query("sort") sort: String = "relevance",
        @Query("page") page: Int = 1,
    ): SearchResult

    @GET("api/v1/suggest")
    suspend fun suggest(@Query("q") q: String): List<String>

    // ---- Video ----
    @GET("api/v1/videos/{id}")
    suspend fun video(@Path("id") id: Int): VideoDto

    @GET("api/v1/videos/{id}/suggestions")
    suspend fun videoSuggestions(@Path("id") id: Int): List<VideoDto>

    @POST("api/v1/videos/{id}/view")
    suspend fun registerView(@Path("id") id: Int): Map<String, Boolean>

    @POST("api/v1/videos/{id}/progress")
    suspend fun saveProgress(@Path("id") id: Int, @Body body: ProgressBody): Map<String, Boolean>

    @POST("api/v1/videos/{id}/react")
    suspend fun react(@Path("id") id: Int, @Body body: ReactionRequest): ReactionResponse

    @GET("api/v1/videos/{id}/comments")
    suspend fun listComments(
        @Path("id") id: Int,
        @Query("sort") sort: String = "top",
        @Query("page") page: Int = 1,
    ): Page<CommentDto>

    @POST("api/v1/videos/{id}/comments")
    suspend fun addComment(@Path("id") id: Int, @Body body: CommentBody): CommentDto

    @GET("api/v1/comments/{id}/replies")
    suspend fun replies(@Path("id") id: Int): List<CommentDto>

    @POST("api/v1/comments/{id}/like")
    suspend fun likeComment(@Path("id") id: Int): Map<String, Any>

    // ---- Channels ----
    @GET("api/v1/channels/{username}")
    suspend fun channel(@Path("username") username: String): ChannelDto

    @POST("api/v1/channels/{id}/subscribe")
    suspend fun subscribe(@Path("id") channelId: Int): SubscribeResponse

    @GET("api/v1/me/subscriptions")
    suspend fun mySubscriptions(): List<ChannelDto>

    // ---- Library ----
    @GET("api/v1/me/watch-later")
    suspend fun watchLater(): List<VideoDto>

    @POST("api/v1/me/watch-later/{id}")
    suspend fun addWatchLater(@Path("id") id: Int): Map<String, Boolean>

    @DELETE("api/v1/me/watch-later/{id}")
    suspend fun removeWatchLater(@Path("id") id: Int): Map<String, Boolean>

    @GET("api/v1/me/history")
    suspend fun history(@Query("page") page: Int = 1): Page<VideoDto>

    @HTTP(method = "DELETE", path = "api/v1/me/history", hasBody = false)
    suspend fun clearHistory(): Map<String, Boolean>

    // ---- Playlists ----
    @GET("api/v1/me/playlists")
    suspend fun myPlaylists(): List<Map<String, Any?>>

    @GET("api/v1/playlists/{id}")
    suspend fun playlist(@Path("id") id: Int): Map<String, Any?>

    @POST("api/v1/me/playlists")
    suspend fun createPlaylist(@Body body: Map<String, String>): Map<String, Any?>

    @POST("api/v1/me/playlists/{pid}/videos/{vid}")
    suspend fun addToPlaylist(@Path("pid") pid: Int, @Path("vid") vid: Int): Map<String, Boolean>

    @DELETE("api/v1/me/playlists/{pid}/videos/{vid}")
    suspend fun removeFromPlaylist(@Path("pid") pid: Int, @Path("vid") vid: Int): Map<String, Boolean>

    // ---- Notifs ----
    @GET("api/v1/me/notifications")
    suspend fun notifications(): List<Notif>

    @POST("api/v1/me/notifications/read")
    suspend fun notificationsRead(): Map<String, Boolean>

    @GET("api/v1/me/notifications/unread-count")
    suspend fun unread(): UnreadCount

    // ---- Studio ----
    @GET("api/v1/me/videos")
    suspend fun myVideos(): Map<String, Any?>

    @PATCH("api/v1/videos/{id}")
    suspend fun updateVideo(@Path("id") id: Int, @Body body: Map<String, String>): Map<String, Any?>

    @DELETE("api/v1/videos/{id}")
    suspend fun deleteVideo(@Path("id") id: Int): Map<String, Boolean>

    // ---- Preferences ----
    @GET("api/v1/me/preferences")
    suspend fun preferences(): Preferences

    @PUT("api/v1/me/preferences")
    suspend fun setPreferences(@Body body: Preferences): Map<String, Boolean>
}
