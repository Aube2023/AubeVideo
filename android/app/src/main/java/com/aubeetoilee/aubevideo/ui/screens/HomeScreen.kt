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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.aubeetoilee.aubevideo.AubeVideoApplication
import com.aubeetoilee.aubevideo.net.VideoDto
import com.aubeetoilee.aubevideo.ui.components.VideoCard

@Composable
fun HomeScreen(app: AubeVideoApplication, navController: NavController) {
    var category by remember { mutableStateOf("Toutes") }
    val categories = remember {
        listOf("Toutes", "Pour vous", "Tendances", "Musique", "Gaming", "Actualités",
            "Sport", "Éducation", "Science", "Humour", "Film", "Voyage",
            "Cuisine", "Technologie", "Art", "Mode")
    }
    var page by remember(category) { mutableStateOf(1) }
    var loading by remember { mutableStateOf(true) }
    var hasMore by remember { mutableStateOf(true) }
    var items by remember(category) { mutableStateOf<List<VideoDto>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    val listState = rememberLazyListState()

    LaunchedEffect(category) {
        loading = true
        error = null
        page = 1
        try {
            val pageData = when (category) {
                "Toutes" -> app.network.api.feed(page = 1)
                "Pour vous" -> app.network.api.recommended(page = 1)
                "Tendances" -> app.network.api.trending(page = 1)
                else -> app.network.api.feed(category = category, page = 1)
            }
            items = pageData.items
            hasMore = pageData.hasMore
        } catch (e: Exception) {
            error = e.message
        }
        loading = false
    }

    // Pagination infinie
    val shouldLoadMore by remember {
        derivedStateOf {
            val last = listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0
            last >= items.size - 4 && hasMore && !loading
        }
    }
    LaunchedEffect(shouldLoadMore) {
        if (!shouldLoadMore || !hasMore || loading) return@LaunchedEffect
        loading = true
        try {
            page += 1
            val pageData = when (category) {
                "Toutes" -> app.network.api.feed(page = page)
                "Pour vous" -> app.network.api.recommended(page = page)
                "Tendances" -> app.network.api.trending(page = page)
                else -> app.network.api.feed(category = category, page = page)
            }
            items = items + pageData.items
            hasMore = pageData.hasMore
        } catch (_: Exception) { }
        loading = false
    }

    Column(Modifier.fillMaxSize()) {
        // Top bar
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
                Box(
                    Modifier
                        .size(28.dp)
                        .clip(RoundedCornerShape(6.dp))
                        .background(MaterialTheme.colorScheme.primary),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("A", color = MaterialTheme.colorScheme.onPrimary,
                        fontWeight = FontWeight.Bold)
                }
                Spacer(Modifier.width(8.dp))
                Text("AubeVideo", style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold)
            }
            IconButton(onClick = { navController.navigate("search") }) {
                Icon(Icons.Filled.Search, contentDescription = "Rechercher")
            }
            IconButton(onClick = { navController.navigate("settings") }) {
                Icon(Icons.Filled.Settings, contentDescription = "Paramètres")
            }
        }

        // Chips catégories
        LazyRow(
            contentPadding = PaddingValues(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(categories) { cat ->
                val selected = cat == category
                Box(
                    Modifier
                        .clip(RoundedCornerShape(10.dp))
                        .background(
                            if (selected) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.surfaceVariant
                        )
                        .clickable { category = cat }
                        .padding(horizontal = 14.dp, vertical = 8.dp),
                ) {
                    Text(
                        cat,
                        color = if (selected) MaterialTheme.colorScheme.onPrimary
                        else MaterialTheme.colorScheme.onSurface,
                        style = MaterialTheme.typography.labelLarge,
                    )
                }
            }
        }

        Spacer(Modifier.height(8.dp))

        if (loading && items.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (error != null && items.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(error ?: "Erreur", color = MaterialTheme.colorScheme.error)
            }
        } else {
            LazyColumn(
                state = listState,
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
            ) {
                items(items, key = { it.id }) { v ->
                    VideoCard(
                        video = v,
                        onClick = { navController.navigate("watch/${v.id}") },
                        onChannelClick = { navController.navigate("channel/$it") },
                    )
                }
                if (loading) {
                    item {
                        Box(Modifier.fillMaxWidth().height(60.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    }
                }
            }
        }
    }
}
