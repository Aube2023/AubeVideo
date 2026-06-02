package com.aubeetoilee.aubevideo

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import com.aubeetoilee.aubevideo.ui.nav.AppNavigation
import com.aubeetoilee.aubevideo.ui.theme.AubeVideoTheme

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val app = application as AubeVideoApplication
        setContent {
            val themePref by app.session.theme.collectAsState(initial = "system")
            val forceDark = when (themePref) {
                "dark" -> true
                "light" -> false
                else -> null
            }
            AubeVideoTheme(forceDark = forceDark) {
                AppNavigation(app = app)
            }
        }
    }
}
