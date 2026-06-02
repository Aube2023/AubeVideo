package com.aubeetoilee.aubevideo.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import com.aubeetoilee.aubevideo.BuildConfig
import com.aubeetoilee.aubevideo.net.VideoDto
import com.aubeetoilee.aubevideo.util.formatCount
import com.aubeetoilee.aubevideo.util.formatDuration
import com.aubeetoilee.aubevideo.util.timeAgo

@Composable
fun VideoCard(
    video: VideoDto,
    onClick: () -> Unit,
    onChannelClick: ((String) -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(bottom = 16.dp)
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 9f)
                .clip(RoundedCornerShape(12.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant)
        ) {
            AsyncImage(
                model = absoluteUrl(video.thumbnail),
                contentDescription = video.title,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxWidth(),
            )
            Box(
                Modifier
                    .align(Alignment.BottomEnd)
                    .padding(8.dp)
                    .background(Color(0xCC000000), RoundedCornerShape(4.dp))
                    .padding(horizontal = 6.dp, vertical = 2.dp)
            ) {
                Text(
                    if (video.isLive) "EN DIRECT" else formatDuration(video.duration),
                    color = if (video.isLive) Color(0xFFE54444) else Color.White,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }

        Row(Modifier.padding(top = 10.dp, start = 4.dp, end = 4.dp)) {
            val avatarUrl = video.channel?.avatar
            if (avatarUrl != null) {
                AsyncImage(
                    model = absoluteUrl(avatarUrl),
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .size(36.dp)
                        .clip(CircleShape)
                        .background(MaterialTheme.colorScheme.surfaceVariant)
                        .let { m ->
                            if (onChannelClick != null && video.channel.username.isNotEmpty())
                                m.clickable { onChannelClick(video.channel.username) }
                            else m
                        }
                )
                Spacer(Modifier.width(10.dp))
            }
            Column(Modifier.fillMaxWidth()) {
                Text(
                    video.title,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    video.channel?.displayName ?: "",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    "${formatCount(video.views)} vues • ${timeAgo(video.createdAt)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

fun absoluteUrl(path: String?): String? {
    if (path.isNullOrBlank()) return null
    if (path.startsWith("http")) return path
    val base = BuildConfig.BASE_URL.trimEnd('/')
    return base + if (path.startsWith("/")) path else "/$path"
}
