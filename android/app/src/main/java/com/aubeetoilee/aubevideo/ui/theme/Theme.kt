package com.aubeetoilee.aubevideo.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

val AubeGold = Color(0xFFE8B84A)
val AubeGoldDark = Color(0xFFC4973A)
val AubeNavy = Color(0xFF3A5F9E)
val AubeBgDark = Color(0xFF0F0F0F)
val AubeElevDark = Color(0xFF181818)
val AubeBgLight = Color(0xFFFFFFFF)
val AubeElevLight = Color(0xFFF4F4F4)
val AubeRed = Color(0xFFE54444)

private val DarkScheme = darkColorScheme(
    primary = AubeGold,
    onPrimary = Color(0xFF1A1A1A),
    secondary = AubeNavy,
    onSecondary = Color.White,
    tertiary = AubeGoldDark,
    background = AubeBgDark,
    onBackground = Color(0xFFF1F1F1),
    surface = AubeBgDark,
    onSurface = Color(0xFFF1F1F1),
    surfaceVariant = AubeElevDark,
    onSurfaceVariant = Color(0xFFAAAAAA),
    error = AubeRed,
)

private val LightScheme = lightColorScheme(
    primary = AubeGoldDark,
    onPrimary = Color.White,
    secondary = AubeNavy,
    onSecondary = Color.White,
    tertiary = AubeGold,
    background = AubeBgLight,
    onBackground = Color(0xFF111111),
    surface = AubeBgLight,
    onSurface = Color(0xFF111111),
    surfaceVariant = AubeElevLight,
    onSurfaceVariant = Color(0xFF555555),
    error = AubeRed,
)

@Composable
fun AubeVideoTheme(
    forceDark: Boolean? = null,
    dynamicColor: Boolean = false,
    content: @Composable () -> Unit,
) {
    val systemDark = isSystemInDarkTheme()
    val dark = forceDark ?: systemDark
    val scheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val ctx = LocalContext.current
            if (dark) dynamicDarkColorScheme(ctx) else dynamicLightColorScheme(ctx)
        }
        dark -> DarkScheme
        else -> LightScheme
    }
    MaterialTheme(colorScheme = scheme, typography = AubeTypography, content = content)
}
