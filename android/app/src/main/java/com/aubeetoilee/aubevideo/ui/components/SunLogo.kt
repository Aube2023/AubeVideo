package com.aubeetoilee.aubevideo.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlin.math.cos
import kotlin.math.sin

/**
 * Logo AubeVideo : soleil rayonnant (12 rayons) + play central,
 * repris du logo.svg du site.
 */
@Composable
fun SunLogo(size: Dp, modifier: Modifier = Modifier, withHalo: Boolean = false) {
    Box(modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val r = this.size.minDimension / 2f
            if (withHalo) {
                drawCircle(
                    brush = Brush.radialGradient(
                        listOf(Color(0x55F7B545), Color(0x00F7B545)),
                        center = center, radius = r,
                    ),
                    radius = r,
                )
            }
            // 12 rayons triangulaires
            val ray = Color(0xFFF7B545)
            for (i in 0 until 12) {
                val a = Math.toRadians((i * 30).toDouble())
                val dirX = cos(a).toFloat()
                val dirY = sin(a).toFloat()
                val perpX = -dirY
                val perpY = dirX
                val tip = Offset(center.x + r * 0.95f * dirX, center.y + r * 0.95f * dirY)
                val baseC = Offset(center.x + r * 0.66f * dirX, center.y + r * 0.66f * dirY)
                val half = r * 0.07f
                val path = Path().apply {
                    moveTo(tip.x, tip.y)
                    lineTo(baseC.x + perpX * half, baseC.y + perpY * half)
                    lineTo(baseC.x - perpX * half, baseC.y - perpY * half)
                    close()
                }
                drawPath(path, ray)
            }
            // Disque solaire en dégradé radial (comme le logo web)
            drawCircle(
                brush = Brush.radialGradient(
                    listOf(Color(0xFFFFE39A), Color(0xFFF7B545), Color(0xFFE8851C)),
                    center = Offset(center.x - r * 0.12f, center.y - r * 0.16f),
                    radius = r * 0.72f,
                ),
                radius = r * 0.5f,
            )
        }
        Icon(
            Icons.Filled.PlayArrow,
            contentDescription = null,
            tint = Color.White,
            modifier = Modifier.size(size * 0.4f),
        )
    }
}
