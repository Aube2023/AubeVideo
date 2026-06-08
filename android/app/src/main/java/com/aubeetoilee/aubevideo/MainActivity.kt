package com.aubeetoilee.aubevideo

import android.app.PictureInPictureParams
import android.content.res.Configuration
import android.os.Build
import android.os.Bundle
import android.util.Rational
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

    /** Une vidéo joue-t-elle actuellement ? (sert à déclencher le PiP) */
    private fun isPlayingVideo(): Boolean {
        val p = WatchSession.player ?: return false
        return WatchSession.videoId != null && p.isPlaying
    }

    private fun enterPipIfPlaying() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        if (!isPlayingVideo()) return
        runCatching {
            val params = PictureInPictureParams.Builder()
                .setAspectRatio(Rational(16, 9))
                .build()
            enterPictureInPictureMode(params)
        }
    }

    // L'utilisateur quitte l'app (Home, aperçu des apps…) pendant la lecture → PiP
    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        enterPipIfPlaying()
    }

    override fun onPictureInPictureModeChanged(
        isInPictureInPictureMode: Boolean,
        newConfig: Configuration,
    ) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        WatchSession.inPip = isInPictureInPictureMode
        // Fenêtre PiP fermée par l'utilisateur (✕) alors que l'app reste en arrière-plan
        if (!isInPictureInPictureMode && lifecycle.currentState
                == androidx.lifecycle.Lifecycle.State.CREATED) {
            WatchSession.close()
        }
    }
}
