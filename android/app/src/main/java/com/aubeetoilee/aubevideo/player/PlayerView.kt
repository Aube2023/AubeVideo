package com.aubeetoilee.aubevideo.player

import android.app.PictureInPictureParams
import android.app.PictureInPictureUiState
import android.content.pm.PackageManager
import android.os.Build
import android.util.Rational
import android.view.ViewGroup
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView

/**
 * Surface ExoPlayer dans Compose. Le cycle de vie du Player est géré par l'appelant.
 * Si [onToggleFullscreen] est fourni, le bouton plein écran apparaît dans les contrôles.
 */
@Composable
fun VideoPlayer(
    player: ExoPlayer,
    modifier: Modifier = Modifier,
    fullscreen: Boolean = false,
    onToggleFullscreen: (() -> Unit)? = null,
) {
    Box(
        modifier
            .then(
                if (fullscreen) Modifier.fillMaxSize()
                else Modifier.fillMaxWidth().aspectRatio(16f / 9f)
            )
            .background(Color.Black)
    ) {
        AndroidView(
            factory = { ctx ->
                PlayerView(ctx).apply {
                    this.player = player
                    useController = true
                    setShowSubtitleButton(true)
                    setShowNextButton(false)
                    setShowPreviousButton(false)
                    layoutParams = ViewGroup.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.MATCH_PARENT,
                    )
                }
            },
            update = { view ->
                view.player = player
                if (onToggleFullscreen != null) {
                    view.setFullscreenButtonClickListener(
                        PlayerView.FullscreenButtonClickListener { onToggleFullscreen() }
                    )
                    view.setFullscreenButtonState(fullscreen)
                }
            },
        )
    }
    DisposableEffect(Unit) { onDispose { /* le player vit ailleurs */ } }
}

/** Construit les paramètres PiP en fonction du ratio courant. */
fun pipParams(player: Player): PictureInPictureParams? {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return null
    val w = player.videoSize.width.takeIf { it > 0 } ?: 16
    val h = player.videoSize.height.takeIf { it > 0 } ?: 9
    val ratio = Rational(w, h).coerceWithin()
    val b = PictureInPictureParams.Builder().setAspectRatio(ratio)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) b.setAutoEnterEnabled(true)
    return b.build()
}

private fun Rational.coerceWithin(): Rational {
    // Android exige des ratios entre 1:2.39 et 2.39:1
    val v = numerator.toDouble() / denominator.toDouble()
    return when {
        v < 0.418 -> Rational(100, 239)
        v > 2.39 -> Rational(239, 100)
        else -> this
    }
}

/** True si l'appareil supporte PiP. */
fun hasPip(ctx: android.content.Context): Boolean =
    Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
        ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE)

/** Helper non utilisé mais évite warning unused — l'API peut être étendue plus tard. */
@Suppress("unused")
fun PictureInPictureUiState.hi() = Unit
