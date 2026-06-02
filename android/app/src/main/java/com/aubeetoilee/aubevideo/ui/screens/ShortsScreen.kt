package com.aubeetoilee.aubevideo.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.pager.VerticalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChatBubbleOutline
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView as Media3PlayerView
import androidx.compose.ui.viewinterop.AndroidView
import androidx.navigation.NavController
import coil3.compose.AsyncImage
import com.aubeetoilee.aubevideo.AubeVideoApplication
import com.aubeetoilee.aubevideo.net.ReactionRequest
import com.aubeetoilee.aubevideo.net.VideoDto
import com.aubeetoilee.aubevideo.ui.components.absoluteUrl
import com.aubeetoilee.aubevideo.util.formatCount
import kotlinx.coroutines.launch

@Composable
fun ShortsScreen(app: AubeVideoApplication, navController: NavController) {
    var items by remember { mutableStateOf<List<VideoDto>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        runCatching {
            items = app.network.api.shorts(page = 1).items
        }
        loading = false
    }

    val ctx = LocalContext.current
    val player = remember {
        ExoPlayer.Builder(ctx).build().apply {
            repeatMode = Player.REPEAT_MODE_ONE
            playWhenReady = true
        }
    }
    DisposableEffect(Unit) { onDispose { player.release() } }

    val pagerState = rememberPagerState(pageCount = { items.size })
    LaunchedEffect(pagerState.currentPage, items) {
        val v = items.getOrNull(pagerState.currentPage) ?: return@LaunchedEffect
        val url = absoluteUrl(v.stream) ?: v.stream
        player.setMediaItem(MediaItem.fromUri(url))
        player.prepare()
        player.playWhenReady = true
        // Préchargement de la suivante
        runCatching { app.network.api.registerView(v.id) }
    }

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        when {
            loading && items.isEmpty() ->
                CircularProgressIndicator(Modifier.align(Alignment.Center))
            items.isEmpty() ->
                Text("Aucun short pour l'instant", color = Color.White,
                    modifier = Modifier.align(Alignment.Center))
            else -> VerticalPager(state = pagerState, modifier = Modifier.fillMaxSize()) { page ->
                val v = items[page]
                ShortItem(
                    v = v,
                    player = if (page == pagerState.currentPage) player else null,
                    onLike = {
                        runCatching {
                            val cur = v.userReaction
                            app.network.api.react(
                                v.id,
                                ReactionRequest(if (cur == "like") null else "like")
                            )
                        }
                    },
                    onChannel = { navController.navigate("channel/${v.channel?.username}") },
                )
            }
        }
    }
}

@Composable
private fun ShortItem(
    v: VideoDto,
    player: ExoPlayer?,
    onLike: suspend () -> Unit,
    onChannel: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var liked by remember(v.id) { mutableStateOf(v.userReaction == "like") }
    var likeCount by remember(v.id) { mutableStateOf(v.likes) }

    Box(Modifier.fillMaxSize()) {
        if (player != null) {
            AndroidView(
                modifier = Modifier
                    .fillMaxSize()
                    .pointerInput(Unit) {
                        detectTapGestures(onTap = {
                            player.playWhenReady = !player.playWhenReady
                        })
                    },
                factory = { ctx ->
                    Media3PlayerView(ctx).apply {
                        this.player = player
                        useController = false
                        resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                        setBackgroundColor(android.graphics.Color.BLACK)
                    }
                },
                update = { it.player = player },
            )
        } else {
            AsyncImage(
                model = absoluteUrl(v.thumbnail),
                contentDescription = null,
                modifier = Modifier.fillMaxSize().background(Color.DarkGray),
            )
        }

        // Right action rail
        Column(
            Modifier
                .align(Alignment.CenterEnd)
                .padding(end = 12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            AsyncImage(
                model = absoluteUrl(v.channel?.avatar),
                contentDescription = null,
                modifier = Modifier
                    .size(48.dp)
                    .clip(CircleShape)
                    .background(Color.Gray)
                    .clip(CircleShape)
            )
            ShortAction(
                icon = if (liked) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
                label = formatCount(likeCount),
            ) {
                liked = !liked
                likeCount = (likeCount + if (liked) 1 else -1).coerceAtLeast(0)
                scope.launch { onLike() }
            }
            ShortAction(icon = Icons.Filled.ChatBubbleOutline, label = formatCount(v.comments)) {}
            ShortAction(icon = Icons.Filled.Share, label = "Partager") {}
        }

        // Bottom info
        Column(
            Modifier
                .align(Alignment.BottomStart)
                .fillMaxWidth()
                .padding(16.dp)
                .padding(bottom = 12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "@${v.channel?.username ?: ""}",
                    color = Color.White,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.clip(CircleShape)
                )
            }
            Spacer(Modifier.height(6.dp))
            Text(v.title, color = Color.White, maxLines = 2)
        }
    }
}

@Composable
private fun ShortAction(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    onClick: () -> Unit,
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier
            .clip(CircleShape)
            .background(Color(0x66000000))
            .padding(8.dp),
    ) {
        Icon(icon, contentDescription = null, tint = Color.White,
            modifier = Modifier.size(28.dp))
        Text(label, color = Color.White, style = MaterialTheme.typography.bodySmall)
    }
}
