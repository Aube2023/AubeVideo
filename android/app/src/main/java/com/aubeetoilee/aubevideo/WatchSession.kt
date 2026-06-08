package com.aubeetoilee.aubevideo

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.media3.exoplayer.ExoPlayer

/**
 * État global du lecteur vidéo : overlay plein écran, mini-lecteur,
 * et Picture-in-Picture quand on quitte l'app.
 */
object WatchSession {
    var videoId by mutableStateOf<Int?>(null)
    var minimized by mutableStateOf(false)
    var inPip by mutableStateOf(false)
    var player: ExoPlayer? = null

    fun open(id: Int) {
        videoId = id
        minimized = false
    }

    fun close() {
        player?.pause()
        videoId = null
        minimized = false
    }
}
