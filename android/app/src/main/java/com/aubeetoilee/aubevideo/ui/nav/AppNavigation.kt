package com.aubeetoilee.aubevideo.ui.nav

import androidx.compose.foundation.layout.Box
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
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
    data object Subs : TabRoute("subs", "Abonnements", Icons.Filled.Subscriptions)
    data object Library : TabRoute("library", "Bibliothèque", Icons.Filled.VideoLibrary)
    data object Search : TabRoute("search", "Recherche", Icons.Filled.Search)
}

private val tabs = listOf(TabRoute.Home, TabRoute.Shorts, TabRoute.Subs, TabRoute.Library, TabRoute.Search)

@Composable
fun AppNavigation(app: AubeVideoApplication) {
    val navController = rememberNavController()
    val token by app.session.token.collectAsState(initial = null)
    val authenticated = !token.isNullOrBlank()

    val backStack by navController.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route
    val showTabs = currentRoute in tabs.map { it.route } || currentRoute == "library"

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
                            label = { Text(tab.label) },
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
                    val id = entry.arguments?.getString("id")?.toIntOrNull() ?: 0
                    WatchScreen(app = app, navController = navController, videoId = id)
                }
                composable("channel/{username}") { entry ->
                    val u = entry.arguments?.getString("username").orEmpty()
                    ChannelScreen(app = app, navController = navController, username = u)
                }
                composable("settings") { SettingsScreen(app, navController) }
            }
        }
    }
}
