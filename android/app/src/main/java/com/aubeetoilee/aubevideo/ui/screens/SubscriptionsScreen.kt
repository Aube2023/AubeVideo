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
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import coil3.compose.AsyncImage
import com.aubeetoilee.aubevideo.AubeVideoApplication
import com.aubeetoilee.aubevideo.net.ChannelDto
import com.aubeetoilee.aubevideo.net.VideoDto
import com.aubeetoilee.aubevideo.ui.components.VideoCard
import com.aubeetoilee.aubevideo.ui.components.absoluteUrl

@Composable
fun SubscriptionsScreen(app: AubeVideoApplication, navController: NavController) {
    var videos by remember { mutableStateOf<List<VideoDto>>(emptyList()) }
    var channels by remember { mutableStateOf<List<ChannelDto>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        runCatching {
            videos = app.network.api.subscriptionsFeed(page = 1).items
            channels = app.network.api.mySubscriptions()
        }
        loading = false
    }

    if (loading && videos.isEmpty() && channels.isEmpty()) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }

    LazyColumn(Modifier.fillMaxSize()) {
        if (channels.isNotEmpty()) {
            item {
                Column(Modifier.padding(top = 12.dp)) {
                    Text(
                        "Mes chaînes",
                        style = MaterialTheme.typography.titleSmall,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    )
                    LazyRow(
                        contentPadding = PaddingValues(horizontal = 16.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        items(channels) { ch ->
                            Column(
                                Modifier.clickable {
                                    navController.navigate("channel/${ch.username}")
                                }.width(80.dp),
                                horizontalAlignment = Alignment.CenterHorizontally,
                            ) {
                                AsyncImage(
                                    model = absoluteUrl(ch.avatar),
                                    contentDescription = ch.displayName,
                                    modifier = Modifier
                                        .size(64.dp)
                                        .clip(CircleShape)
                                        .background(MaterialTheme.colorScheme.surfaceVariant),
                                )
                                Spacer(Modifier.height(6.dp))
                                Text(
                                    ch.displayName,
                                    style = MaterialTheme.typography.bodySmall,
                                    maxLines = 1,
                                )
                            }
                        }
                    }
                    Spacer(Modifier.height(12.dp))
                }
            }
        }
        item {
            Text(
                "Dernières vidéos",
                style = MaterialTheme.typography.titleSmall,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            )
        }
        items(videos, key = { it.id }) { v ->
            VideoCard(
                video = v,
                onClick = { navController.navigate("watch/${v.id}") },
                onChannelClick = { navController.navigate("channel/$it") },
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
        if (videos.isEmpty()) {
            item {
                Box(
                    Modifier.fillMaxWidth().padding(32.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("Aucune vidéo récente. Abonne-toi à des chaînes pour voir leurs publications ici.")
                }
            }
        }
    }
}
