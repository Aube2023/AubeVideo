package com.aubeetoilee.aubevideo.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AddBox
import androidx.compose.material.icons.filled.PlaylistAdd
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.ThumbDown
import androidx.compose.material.icons.filled.ThumbUp
import androidx.compose.material.icons.outlined.ThumbDown
import androidx.compose.material.icons.outlined.ThumbUp
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.navigation.NavController
import coil3.compose.AsyncImage
import com.aubeetoilee.aubevideo.AubeVideoApplication
import com.aubeetoilee.aubevideo.net.CommentBody
import com.aubeetoilee.aubevideo.net.CommentDto
import com.aubeetoilee.aubevideo.net.ProgressBody
import com.aubeetoilee.aubevideo.net.ReactionRequest
import com.aubeetoilee.aubevideo.net.VideoDto
import com.aubeetoilee.aubevideo.player.VideoPlayer
import com.aubeetoilee.aubevideo.ui.components.VideoCard
import com.aubeetoilee.aubevideo.ui.components.absoluteUrl
import com.aubeetoilee.aubevideo.util.formatCount
import com.aubeetoilee.aubevideo.util.timeAgo
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun WatchScreen(app: AubeVideoApplication, navController: NavController, videoId: Int) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var video by remember { mutableStateOf<VideoDto?>(null) }
    var suggestions by remember { mutableStateOf<List<VideoDto>>(emptyList()) }
    var comments by remember { mutableStateOf<List<CommentDto>>(emptyList()) }
    var commentText by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var fullscreen by remember { mutableStateOf(false) }

    val activity = ctx as? android.app.Activity
    fun setFullscreen(on: Boolean) {
        fullscreen = on
        val act = activity ?: return
        act.requestedOrientation = if (on)
            android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        else
            android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        val controller = androidx.core.view.WindowCompat
            .getInsetsController(act.window, act.window.decorView)
        if (on) {
            controller.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            controller.systemBarsBehavior = androidx.core.view
                .WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        } else {
            controller.show(androidx.core.view.WindowInsetsCompat.Type.systemBars())
        }
    }
    // Retour matériel : sort du plein écran au lieu de quitter la vidéo
    androidx.activity.compose.BackHandler(enabled = fullscreen) { setFullscreen(false) }

    val player = remember(videoId) {
        ExoPlayer.Builder(ctx).build().apply { playWhenReady = true }
    }
    DisposableEffect(videoId) {
        onDispose {
            player.release()
            if (fullscreen) setFullscreen(false)
        }
    }

    LaunchedEffect(videoId) {
        loading = true
        try {
            val v = app.network.api.video(videoId)
            video = v
            // HLS adaptatif (qualité auto selon la connexion) si dispo, sinon MP4
            val hlsUrl = v.hls?.let { absoluteUrl(it) }
            val mp4Url = absoluteUrl(v.stream) ?: v.stream
            player.setMediaItem(MediaItem.fromUri(hlsUrl ?: mp4Url))
            player.prepare()
            // Repli MP4 si le flux HLS échoue
            if (hlsUrl != null) {
                player.addListener(object : androidx.media3.common.Player.Listener {
                    override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
                        val pos = player.currentPosition
                        player.setMediaItem(MediaItem.fromUri(mp4Url))
                        player.prepare()
                        if (pos > 0) player.seekTo(pos)
                        player.play()
                    }
                })
            }
            // Reprise au dernier progress connu si dispo
            v.progressSeconds?.takeIf { it > 5 }?.let { player.seekTo(it.toLong() * 1000L) }
            // Enregistre la vue
            runCatching { app.network.api.registerView(videoId) }
            // Suggestions + commentaires en parallèle
            scope.launch { suggestions = runCatching { app.network.api.videoSuggestions(videoId) }.getOrDefault(emptyList()) }
            scope.launch {
                comments = runCatching { app.network.api.listComments(videoId).items }.getOrDefault(emptyList())
            }
        } catch (e: Exception) {
            error = e.message
        }
        loading = false
    }

    // Sauve la progression toutes les 10 s
    LaunchedEffect(videoId) {
        while (true) {
            delay(10_000)
            val secs = (player.currentPosition / 1000).toInt()
            if (secs > 0) runCatching { app.network.api.saveProgress(videoId, ProgressBody(secs)) }
        }
    }

    if (loading && video == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }
    val v = video ?: return Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(error ?: "Vidéo introuvable", color = MaterialTheme.colorScheme.error)
    }

    // Mode plein écran : le lecteur occupe tout l'écran, rien d'autre
    if (fullscreen) {
        VideoPlayer(
            player = player,
            fullscreen = true,
            onToggleFullscreen = { setFullscreen(false) },
        )
        return
    }

    LazyColumn(Modifier.fillMaxSize()) {
        item {
            Box {
                VideoPlayer(
                    player = player,
                    onToggleFullscreen = { setFullscreen(true) },
                )
                IconButton(
                    onClick = { navController.popBackStack() },
                    modifier = Modifier.padding(8.dp),
                ) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Retour",
                        tint = Color.White)
                }
            }
        }

        item {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
                Text(v.title, style = MaterialTheme.typography.titleMedium,
                    maxLines = 3, overflow = TextOverflow.Ellipsis,
                    fontWeight = FontWeight.SemiBold)
                Text(
                    "${formatCount(v.views)} vues • ${timeAgo(v.createdAt)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        // Actions
        item {
            ActionsRow(v = v, app = app, onUpdate = { video = it })
        }

        // Channel header
        item { ChannelHeader(v = v, app = app, onUpdate = { video = it }, navController = navController) }

        // Description (collapsible)
        if (!v.description.isNullOrBlank()) {
            item {
                var expanded by remember { mutableStateOf(false) }
                Column(
                    Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                        .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp))
                        .clickable { expanded = !expanded }
                        .padding(12.dp)
                ) {
                    Text(
                        v.description,
                        maxLines = if (expanded) Int.MAX_VALUE else 3,
                        overflow = TextOverflow.Ellipsis,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }

        // Chapters
        v.chapters?.takeIf { it.isNotEmpty() }?.let { chapters ->
            item {
                Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                    Text("Chapitres", style = MaterialTheme.typography.titleSmall)
                    Spacer(Modifier.height(8.dp))
                    chapters.forEach { ch ->
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .clickable { player.seekTo(ch.start.toLong() * 1000L) }
                                .padding(vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                "%d:%02d".format(ch.start / 60, ch.start % 60),
                                color = MaterialTheme.colorScheme.primary,
                                fontWeight = FontWeight.Medium,
                            )
                            Spacer(Modifier.width(12.dp))
                            Text(ch.title)
                        }
                    }
                }
            }
        }

        // Commentaires (3 visibles + saisie)
        item {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                Text(
                    "Commentaires (${formatCount(v.comments)})",
                    style = MaterialTheme.typography.titleSmall,
                )
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = commentText,
                        onValueChange = { commentText = it },
                        placeholder = { Text("Ajouter un commentaire…") },
                        modifier = Modifier.weight(1f),
                        singleLine = false,
                        maxLines = 3,
                    )
                    Spacer(Modifier.width(8.dp))
                    TextButton(
                        enabled = commentText.isNotBlank(),
                        onClick = {
                            val content = commentText.trim()
                            scope.launch {
                                try {
                                    val c = app.network.api.addComment(videoId, CommentBody(content))
                                    comments = listOf(c) + comments
                                    commentText = ""
                                } catch (_: Exception) {}
                            }
                        }
                    ) { Text("Publier") }
                }
            }
        }
        items(comments.take(20), key = { it.id }) { c ->
            CommentItem(c)
        }

        // Suggestions
        item {
            Text(
                "À suivre",
                style = MaterialTheme.typography.titleSmall,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            )
        }
        items(suggestions, key = { "s-${it.id}" }) { s ->
            VideoCard(
                video = s,
                onClick = { navController.navigate("watch/${s.id}") },
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
    }
}

@Composable
private fun ActionsRow(v: VideoDto, app: AubeVideoApplication, onUpdate: (VideoDto) -> Unit) {
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current
    var reaction by remember { mutableStateOf(v.userReaction) }
    var likes by remember { mutableStateOf(v.likes) }
    var saved by remember { mutableStateOf(v.inWatchLater) }

    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp)
            .padding(bottom = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Pill(
            icon = if (reaction == "like") Icons.Filled.ThumbUp else Icons.Outlined.ThumbUp,
            text = formatCount(likes),
            highlighted = reaction == "like",
        ) {
            scope.launch {
                val next = if (reaction == "like") null else "like"
                runCatching {
                    val r = app.network.api.react(v.id, ReactionRequest(next))
                    reaction = r.reaction
                    likes = r.likes
                }
            }
        }
        Pill(
            icon = if (reaction == "dislike") Icons.Filled.ThumbDown else Icons.Outlined.ThumbDown,
            text = "",
            highlighted = reaction == "dislike",
        ) {
            scope.launch {
                val next = if (reaction == "dislike") null else "dislike"
                runCatching {
                    val r = app.network.api.react(v.id, ReactionRequest(next))
                    reaction = r.reaction
                    likes = r.likes
                }
            }
        }
        Pill(icon = Icons.Filled.Share, text = "Partager") {
            val intent = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(android.content.Intent.EXTRA_SUBJECT, v.title)
                putExtra(
                    android.content.Intent.EXTRA_TEXT,
                    com.aubeetoilee.aubevideo.BuildConfig.BASE_URL.trimEnd('/') + "/watch/${v.id}"
                )
            }
            ctx.startActivity(android.content.Intent.createChooser(intent, "Partager"))
        }
        Pill(
            icon = if (saved) Icons.Filled.AddBox else Icons.Filled.PlaylistAdd,
            text = if (saved) "Enregistré" else "Plus tard",
            highlighted = saved,
        ) {
            scope.launch {
                runCatching {
                    if (saved) app.network.api.removeWatchLater(v.id)
                    else app.network.api.addWatchLater(v.id)
                    saved = !saved
                    onUpdate(v.copy(inWatchLater = saved))
                }
            }
        }
    }
}

@Composable
private fun Pill(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    text: String,
    highlighted: Boolean = false,
    onClick: () -> Unit,
) {
    Row(
        Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(
                if (highlighted) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.surfaceVariant
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Icon(
            icon, contentDescription = null,
            tint = if (highlighted) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
        )
        if (text.isNotEmpty()) {
            Text(
                text, style = MaterialTheme.typography.labelLarge,
                color = if (highlighted) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

@Composable
private fun ChannelHeader(
    v: VideoDto,
    app: AubeVideoApplication,
    onUpdate: (VideoDto) -> Unit,
    navController: NavController,
) {
    val scope = rememberCoroutineScope()
    val ch = v.channel ?: return
    var subscribed by remember { mutableStateOf(v.isSubscribed) }
    var subs by remember { mutableStateOf(ch.subscribers) }

    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        AsyncImage(
            model = absoluteUrl(ch.avatar),
            contentDescription = null,
            contentScale = androidx.compose.ui.layout.ContentScale.Crop,
            modifier = Modifier
                .size(40.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.surfaceVariant)
                .clickable { navController.navigate("channel/${ch.username}") },
        )
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(ch.displayName, fontWeight = FontWeight.SemiBold)
            Text(
                "${formatCount(subs)} abonné${if (subs > 1) "s" else ""}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Button(
            onClick = {
                scope.launch {
                    runCatching {
                        val r = app.network.api.subscribe(ch.id)
                        subscribed = r.subscribed
                        subs = r.count
                        onUpdate(v.copy(isSubscribed = r.subscribed))
                    }
                }
            },
            colors = if (subscribed) ButtonDefaults.outlinedButtonColors() else ButtonDefaults.buttonColors(),
        ) {
            Text(if (subscribed) "Abonné" else "S'abonner")
        }
    }
}

@Composable
private fun CommentItem(c: CommentDto) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        AsyncImage(
            model = absoluteUrl(c.author.avatar),
            contentDescription = null,
            contentScale = androidx.compose.ui.layout.ContentScale.Crop,
            modifier = Modifier
                .size(32.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.surfaceVariant),
        )
        Spacer(Modifier.width(10.dp))
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(c.author.displayName, style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.width(8.dp))
                Text(
                    timeAgo(c.createdAt),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(c.content, style = MaterialTheme.typography.bodyMedium)
        }
    }
}
