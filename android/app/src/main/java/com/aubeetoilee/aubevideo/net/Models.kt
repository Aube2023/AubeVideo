package com.aubeetoilee.aubevideo.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class LoginRequest(
    val username: String,
    val password: String,
    val device: String? = null,
    val platform: String = "android",
    val otp: String? = null
)

@Serializable
data class LoginResponse(
    val token: String,
    val user: UserSummary
)

@Serializable
data class UserSummary(
    val id: Int,
    val username: String,
    @SerialName("display_name") val displayName: String,
    val avatar: String? = null
)

@Serializable
data class ChannelDto(
    val id: Int,
    val username: String,
    @SerialName("display_name") val displayName: String,
    val bio: String = "",
    val avatar: String? = null,
    val banner: String? = null,
    val subscribers: Long = 0,
    @SerialName("total_views") val totalViews: Long = 0,
    @SerialName("is_verified") val isVerified: Boolean = false,
    @SerialName("is_admin") val isAdmin: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null,
    val videos: List<VideoDto>? = null,
    @SerialName("is_subscribed") val isSubscribed: Boolean? = null
)

@Serializable
data class VideoChannel(
    val id: Int,
    val username: String,
    @SerialName("display_name") val displayName: String,
    val avatar: String? = null,
    val subscribers: Long = 0
)

@Serializable
data class VideoDto(
    val id: Int,
    val title: String,
    val description: String? = null,
    val thumbnail: String,
    val stream: String,
    val duration: Int = 0,
    val views: Long = 0,
    val likes: Long = 0,
    val dislikes: Long = 0,
    val comments: Long = 0,
    val category: String? = null,
    val tags: List<String> = emptyList(),
    @SerialName("is_short") val isShort: Boolean = false,
    @SerialName("is_live") val isLive: Boolean = false,
    val visibility: String? = null,
    @SerialName("age_restricted") val ageRestricted: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null,
    val qualities: List<String> = emptyList(),
    val channel: VideoChannel? = null,
    @SerialName("user_reaction") val userReaction: String? = null,
    @SerialName("is_subscribed") val isSubscribed: Boolean = false,
    @SerialName("in_watch_later") val inWatchLater: Boolean = false,
    val captions: List<CaptionDto>? = null,
    val chapters: List<ChapterDto>? = null,
    @SerialName("watched_at") val watchedAt: String? = null,
    @SerialName("progress_seconds") val progressSeconds: Int? = null
)

@Serializable
data class CaptionDto(
    val id: Int,
    val lang: String,
    val label: String,
    val url: String,
    val auto: Boolean = false
)

@Serializable
data class ChapterDto(val start: Int, val title: String)

@Serializable
data class CommentDto(
    val id: Int,
    @SerialName("video_id") val videoId: Int? = null,
    @SerialName("parent_id") val parentId: Int? = null,
    val content: String,
    val likes: Long = 0,
    @SerialName("is_pinned") val isPinned: Boolean = false,
    val hearted: Boolean = false,
    @SerialName("reply_count") val replyCount: Int = 0,
    @SerialName("created_at") val createdAt: String? = null,
    val author: CommentAuthor
)

@Serializable
data class CommentAuthor(
    val username: String,
    @SerialName("display_name") val displayName: String,
    val avatar: String? = null
)

@Serializable
data class Page<T>(
    val page: Int = 1,
    @SerialName("per_page") val perPage: Int = 24,
    val items: List<T> = emptyList(),
    @SerialName("has_more") val hasMore: Boolean = false
)

@Serializable
data class ReactionRequest(val reaction: String?)

@Serializable
data class ReactionResponse(
    val likes: Long, val dislikes: Long, val reaction: String?
)

@Serializable
data class SubscribeResponse(val subscribed: Boolean, val count: Long)

@Serializable
data class CommentBody(
    val content: String,
    @SerialName("parent_id") val parentId: Int? = null
)

@Serializable
data class Notif(
    val id: Int, val type: String,
    val title: String, val body: String = "",
    val link: String = "",
    @SerialName("is_read") val isRead: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null
)

@Serializable
data class UnreadCount(val unread: Int)

@Serializable
data class ProgressBody(val seconds: Int)

@Serializable
data class SearchResult(
    val videos: List<VideoDto> = emptyList(),
    val channels: List<ChannelDto> = emptyList()
)

@Serializable
data class Preferences(
    val theme: String = "dark",
    val autoplay: Boolean = true,
    @SerialName("default_quality") val defaultQuality: String = "auto",
    val language: String = "fr",
    @SerialName("safe_mode") val safeMode: Boolean = false,
    @SerialName("background_play") val backgroundPlay: Boolean = true
)

@Serializable
data class ErrorBody(val error: String? = null)
