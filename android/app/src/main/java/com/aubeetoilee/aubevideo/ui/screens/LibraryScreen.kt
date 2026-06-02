package com.aubeetoilee.aubevideo.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.PlaylistPlay
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.VideoLibrary
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import coil3.compose.AsyncImage
import com.aubeetoilee.aubevideo.AubeVideoApplication
import com.aubeetoilee.aubevideo.net.VideoDto
import com.aubeetoilee.aubevideo.ui.components.absoluteUrl
import com.aubeetoilee.aubevideo.util.formatCount
import com.aubeetoilee.aubevideo.util.formatDuration

@Composable
fun LibraryScreen(app: AubeVideoApplication, navController: NavController) {
    val username by app.session.username.collectAsState(initial = null)
    val display by app.session.displayName.collectAsState(initial = null)
    var history by remember { mutableStateOf<List<VideoDto>>(emptyList()) }
    var watchLater by remember { mutableStateOf<List<VideoDto>>(emptyList()) }

    LaunchedEffect(Unit) {
        runCatching { history = app.network.api.history().items }
        runCatching { watchLater = app.network.api.watchLater() }
    }

    LazyColumn(Modifier.fillMaxSize()) {
        item {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(16.dp)
                    .clickable { username?.let { navController.navigate("channel/$it") } },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                AsyncImage(
                    model = username?.let { com.aubeetoilee.aubevideo.BuildConfig.BASE_URL.trimEnd('/') + "/avatar/$it" },
                    contentDescription = null,
                    modifier = Modifier
                        .size(48.dp)
                        .clip(CircleShape)
                        .background(MaterialTheme.colorScheme.surfaceVariant),
                )
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(display ?: username.orEmpty(),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold)
                    Text("Voir ma chaîne",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Icon(
                    Icons.Filled.Settings, null,
                    modifier = Modifier
                        .clickable { navController.navigate("settings") }
                        .padding(8.dp),
                )
            }
        }

        item {
            ShortcutsRow(
                items = listOf(
                    Triple("Historique", Icons.Filled.History) { navController.navigate("library") },
                    Triple("Plus tard", Icons.Filled.Schedule) { navController.navigate("library") },
                    Triple("Playlists", Icons.AutoMirrored.Filled.PlaylistPlay) { navController.navigate("library") },
                    Triple("Téléch.", Icons.Filled.Download) { navController.navigate("library") },
                    Triple("Vidéos", Icons.Filled.VideoLibrary) { username?.let { navController.navigate("channel/$it") } },
                )
            )
        }

        if (history.isNotEmpty()) {
            item { SectionTitle("Historique") }
            items(history.take(5), key = { "h-${it.id}" }) { v ->
                ListVideoItem(v) { navController.navigate("watch/${v.id}") }
            }
        }
        if (watchLater.isNotEmpty()) {
            item { SectionTitle("À regarder plus tard") }
            items(watchLater.take(5), key = { "w-${it.id}" }) { v ->
                ListVideoItem(v) { navController.navigate("watch/${v.id}") }
            }
        }
        if (history.isEmpty() && watchLater.isEmpty()) {
            item {
                Box(Modifier.fillMaxSize().padding(32.dp), contentAlignment = Alignment.Center) {
                    Text("Ta bibliothèque est encore vide. Regarde quelques vidéos !")
                }
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleSmall,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
    )
}

@Composable
private fun ShortcutsRow(items: List<Triple<String, ImageVector, () -> Unit>>) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 4.dp),
    ) {
        items.forEach { (label, icon, action) ->
            Column(
                modifier = Modifier
                    .weight(1f)
                    .clip(androidx.compose.foundation.shape.RoundedCornerShape(12.dp))
                    .clickable(onClick = action)
                    .padding(vertical = 12.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Icon(icon, contentDescription = label,
                    tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.height(6.dp))
                Text(label, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun ListVideoItem(v: VideoDto, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.width(140.dp).height(80.dp).clip(androidx.compose.foundation.shape.RoundedCornerShape(8.dp))) {
            AsyncImage(
                model = absoluteUrl(v.thumbnail),
                contentDescription = v.title,
                modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surfaceVariant),
            )
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(v.title, style = MaterialTheme.typography.titleSmall, maxLines = 2)
            Text(
                v.channel?.displayName.orEmpty(),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                "${formatCount(v.views)} vues • ${formatDuration(v.duration)}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
