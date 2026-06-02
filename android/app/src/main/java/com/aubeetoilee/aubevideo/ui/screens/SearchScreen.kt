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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import coil3.compose.AsyncImage
import com.aubeetoilee.aubevideo.AubeVideoApplication
import com.aubeetoilee.aubevideo.net.ChannelDto
import com.aubeetoilee.aubevideo.net.VideoDto
import com.aubeetoilee.aubevideo.ui.components.VideoCard
import com.aubeetoilee.aubevideo.ui.components.absoluteUrl
import com.aubeetoilee.aubevideo.util.formatCount
import kotlinx.coroutines.delay

@Composable
fun SearchScreen(app: AubeVideoApplication, navController: NavController) {
    var q by remember { mutableStateOf("") }
    var suggestions by remember { mutableStateOf<List<String>>(emptyList()) }
    var videos by remember { mutableStateOf<List<VideoDto>>(emptyList()) }
    var channels by remember { mutableStateOf<List<ChannelDto>>(emptyList()) }
    var submitted by remember { mutableStateOf(false) }

    // Debounced suggestions
    LaunchedEffect(q) {
        delay(220)
        if (q.length >= 2 && !submitted) {
            runCatching { suggestions = app.network.api.suggest(q) }
        } else if (q.isBlank()) {
            suggestions = emptyList()
        }
    }

    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = q,
            onValueChange = { q = it; submitted = false },
            placeholder = { Text("Rechercher une vidéo, une chaîne…") },
            leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text, imeAction = ImeAction.Search),
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
        )

        LaunchedEffect(submitted, q) {
            if (submitted && q.isNotBlank()) {
                runCatching {
                    val r = app.network.api.search(q.trim(), sort = "relevance")
                    videos = r.videos; channels = r.channels
                }
            }
        }

        if (!submitted && suggestions.isNotEmpty()) {
            LazyColumn {
                items(suggestions) { s ->
                    Text(
                        s,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { q = s; submitted = true }
                            .padding(horizontal = 16.dp, vertical = 10.dp),
                    )
                }
            }
        } else if (submitted) {
            LazyColumn(Modifier.fillMaxSize()) {
                if (channels.isNotEmpty()) {
                    item {
                        Text(
                            "Chaînes",
                            style = MaterialTheme.typography.titleSmall,
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                        )
                    }
                    items(channels) { ch ->
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .clickable { navController.navigate("channel/${ch.username}") }
                                .padding(horizontal = 16.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            AsyncImage(
                                model = absoluteUrl(ch.avatar),
                                contentDescription = null,
                                modifier = Modifier
                                    .size(48.dp)
                                    .clip(CircleShape)
                                    .background(MaterialTheme.colorScheme.surfaceVariant),
                            )
                            Spacer(Modifier.width(12.dp))
                            Column {
                                Text(ch.displayName, fontWeight = FontWeight.SemiBold)
                                Text(
                                    "${formatCount(ch.subscribers)} abonnés",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
                if (videos.isNotEmpty()) {
                    item {
                        Text(
                            "Vidéos",
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
                }
                if (videos.isEmpty() && channels.isEmpty()) {
                    item {
                        Box(Modifier.fillMaxSize().padding(32.dp),
                            contentAlignment = Alignment.Center) {
                            Text("Aucun résultat pour « $q »")
                        }
                    }
                }
            }
        }
    }
}
