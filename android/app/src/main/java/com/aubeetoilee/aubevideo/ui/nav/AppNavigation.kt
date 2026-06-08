package com.aubeetoilee.aubevideo.ui.nav

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.PlaylistPlay
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Subscriptions
import androidx.compose.material.icons.filled.VideoLibrary
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.ui.graphics.Color
import androidx.compose.material3.Text
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.aubeetoilee.aubevideo.AubeVideoApplication
import com.aubeetoilee.aubevideo.ui.screens.ChannelScreen
import com.aubeetoilee.aubevideo.ui.screens.HomeScreen
import com.aubeetoilee.aubevideo.ui.screens.LibraryScreen
import com.aubeetoilee.aubevideo.ui.screens.LoginScreen
import com.aubeetoilee.aubevideo.ui.screens.SearchScreen
import com.aubeetoilee.aubevideo.ui.screens.ShortsScreen
import com.aubeetoilee.aubevideo.ui.screens.SubscriptionsScreen
import com.aubeetoilee.aubevideo.ui.screens.WatchScreen
import com.aubeetoilee.aubevideo.ui.screens.SettingsScreen

sealed class TabRoute(val route: String, val label: String, val icon: ImageVector) {
    data object Home : TabRoute("home", "Accueil", Icons.Filled.Home)
    data object Shorts : TabRoute("shorts", "Shorts", Icons.Filled.PlayArrow)
    data object Subs : TabRoute("subs", "Abos", Icons.Filled.Subscriptions)
    data object Library : TabRoute("library", "Biblio", Icons.Filled.VideoLibrary)
    data object Search : TabRoute("search", "Recherche", Icons.Filled.Search)
}

// La recherche n'est pas dans la barre du bas (accessible via la loupe en haut),
// pour laisser respirer les 4 onglets principaux.
private val tabs = listOf(TabRoute.Home, TabRoute.Shorts, TabRoute.Subs, TabRoute.Library)

@Composable
fun AppNavigation(app: AubeVideoApplication) {
    val navController = rememberNavController()
    val token by app.session.token.collectAsState(initial = null)
    val authenticated = !token.isNullOrBlank()

    val backStack by navController.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route
    val showTabs = currentRoute in tabs.map { it.route } || currentRoute == "library"

    // Lecteur vidéo en overlay (façon YouTube) : il survit à la navigation,
    // réduit en mini-lecteur au-dessus de la barre d'onglets.
    // État porté par WatchSession pour que MainActivity (PiP) y accède.
    val watchId = com.aubeetoilee.aubevideo.WatchSession.videoId
    val watchMinimized = com.aubeetoilee.aubevideo.WatchSession.minimized

    Box(Modifier.fillMaxSize()) {
    Scaffold(
        bottomBar = {
            if (showTabs && authenticated) {
                NavigationBar {
                    tabs.forEach { tab ->
                        val selected = currentRoute == tab.route
                        NavigationBarItem(
                            selected = selected,
                            onClick = {
                                navController.navigate(tab.route) {
                                    popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(tab.icon, contentDescription = tab.label) },
                            label = {
                                Text(
                                    tab.label,
                                    style = MaterialTheme.typography.labelSmall,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            },
                            colors = NavigationBarItemDefaults.colors(
                                // Pastille dorée (identité Aube) au lieu du violet par défaut
                                indicatorColor = Color(0x33F7B545),
                                selectedIconColor = Color(0xFFF7B545),
                                selectedTextColor = Color(0xFFF7B545),
                            ),
                        )
                    }
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            NavHost(
                navController = navController,
                startDestination = if (authenticated) TabRoute.Home.route else "login",
            ) {
                composable("login") { LoginScreen(app, navController) }
                composable(TabRoute.Home.route) { HomeScreen(app, navController) }
                composable(TabRoute.Shorts.route) { ShortsScreen(app, navController) }
                composable(TabRoute.Subs.route) { SubscriptionsScreen(app, navController) }
                composable(TabRoute.Library.route) { LibraryScreen(app, navController) }
                composable(TabRoute.Search.route) { SearchScreen(app, navController) }
                composable("watch/{id}") { entry ->
                    // Redirige vers l'overlay : la vidéo s'ouvre par-dessus la navigation
                    val id = entry.arguments?.getString("id")?.toIntOrNull() ?: 0
                    LaunchedEffect(id) {
                        com.aubeetoilee.aubevideo.WatchSession.open(id)
                        navController.popBackStack()
                    }
                }
                composable("channel/{username}") { entry ->
                    val u = entry.arguments?.getString("username").orEmpty()
                    ChannelScreen(app = app, navController = navController, username = u)
                }
                composable("settings") { SettingsScreen(app, navController) }
            }
        }
    }

    // Overlay vidéo : reste composé même réduit pour que la lecture continue.
    // Un seul point de composition (le lecteur survit au passage plein ↔ mini).
    watchId?.let { id ->
        val inPip = com.aubeetoilee.aubevideo.WatchSession.inPip
        val overlayModifier = if (watchMinimized && !inPip) {
            Modifier
                .align(Alignment.BottomCenter)
                .navigationBarsPadding()
                .padding(bottom = if (showTabs) 80.dp else 0.dp)
        } else {
            Modifier.fillMaxSize()
        }
        Box(overlayModifier) {
            WatchScreen(
                app = app, navController = navController, videoId = id,
                minimized = watchMinimized,
                onMinimize = { com.aubeetoilee.aubevideo.WatchSession.minimized = true },
                onExpand = { com.aubeetoilee.aubevideo.WatchSession.minimized = false },
                onClose = { com.aubeetoilee.aubevideo.WatchSession.close() },
                onOpenVideo = { newId -> com.aubeetoilee.aubevideo.WatchSession.open(newId) },
            )
        }
    }
    }
}
