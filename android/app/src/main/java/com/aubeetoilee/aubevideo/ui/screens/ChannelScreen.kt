package com.aubeetoilee.aubevideo.ui.screens

import androidx.compose.foundation.background
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
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import coil3.compose.AsyncImage
import com.aubeetoilee.aubevideo.AubeVideoApplication
import com.aubeetoilee.aubevideo.net.ChannelDto
import com.aubeetoilee.aubevideo.ui.components.VideoCard
import com.aubeetoilee.aubevideo.ui.components.absoluteUrl
import com.aubeetoilee.aubevideo.util.formatCount
import kotlinx.coroutines.launch

@Composable
fun ChannelScreen(app: AubeVideoApplication, navController: NavController, username: String) {
    var data by remember(username) { mutableStateOf<ChannelDto?>(null) }
    var loading by remember(username) { mutableStateOf(true) }
    var subscribed by remember(username) { mutableStateOf(false) }
    var subs by remember(username) { mutableStateOf(0L) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(username) {
        loading = true
        runCatching {
            val c = app.network.api.channel(username)
            data = c
            subscribed = c.isSubscribed == true
            subs = c.subscribers
        }
        loading = false
    }

    val c = data
    if (loading && c == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }
    if (c == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("Chaîne introuvable")
        }
        return
    }

    LazyColumn(Modifier.fillMaxSize()) {
        item {
            // Banner
            if (c.banner != null) {
                AsyncImage(
                    model = absoluteUrl(c.banner),
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(120.dp)
                        .background(MaterialTheme.colorScheme.surfaceVariant),
                )
            }
            Row(
                Modifier.padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                AsyncImage(
                    model = absoluteUrl(c.avatar),
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .size(72.dp)
                        .clip(CircleShape)
                        .background(MaterialTheme.colorScheme.surfaceVariant),
                )
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(c.displayName, fontWeight = FontWeight.SemiBold,
                            style = MaterialTheme.typography.titleMedium)
                        if (c.isVerified) {
                            Spacer(Modifier.width(6.dp))
                            Text("✓", color = MaterialTheme.colorScheme.primary,
                                fontWeight = FontWeight.Bold)
                        }
                    }
                    Text(
                        "@${c.username} • ${formatCount(subs)} abonnés",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Button(
                    onClick = {
                        scope.launch {
                            runCatching {
                                val r = app.network.api.subscribe(c.id)
                                subscribed = r.subscribed
                                subs = r.count
                            }
                        }
                    },
                    colors = if (subscribed) ButtonDefaults.outlinedButtonColors() else ButtonDefaults.buttonColors(),
                ) {
                    Text(if (subscribed) "Abonné" else "S'abonner")
                }
            }
            if (c.bio.isNotBlank()) {
                Text(
                    c.bio,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }
            Text(
                "Vidéos",
                style = MaterialTheme.typography.titleSmall,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            )
        }
        items(c.videos.orEmpty(), key = { it.id }) { v ->
            VideoCard(
                video = v,
                onClick = { navController.navigate("watch/${v.id}") },
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
    }
}
