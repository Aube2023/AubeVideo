package com.aubeetoilee.aubevideo.util

import java.time.Duration
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

fun formatCount(n: Long): String {
    val abs = kotlin.math.abs(n)
    return when {
        abs < 1_000 -> n.toString()
        abs < 1_000_000 -> "${"%.1f".format(n / 1_000.0).trimEnd('0').trimEnd('.')} k"
        abs < 1_000_000_000 -> "${"%.1f".format(n / 1_000_000.0).trimEnd('0').trimEnd('.')} M"
        else -> "${"%.1f".format(n / 1_000_000_000.0).trimEnd('0').trimEnd('.')} Md"
    }
}

fun formatCount(n: Int): String = formatCount(n.toLong())

fun formatDuration(seconds: Int): String {
    if (seconds <= 0) return "0:00"
    val h = seconds / 3600
    val m = (seconds % 3600) / 60
    val s = seconds % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, s)
    else "%d:%02d".format(m, s)
}

fun timeAgo(iso: String?): String {
    if (iso.isNullOrBlank()) return ""
    val dt = try {
        // Server returns ISO without zone. Treat as UTC.
        OffsetDateTime.parse(iso, DateTimeFormatter.ISO_DATE_TIME)
    } catch (_: DateTimeParseException) {
        try {
            OffsetDateTime.of(
                java.time.LocalDateTime.parse(iso),
                ZoneOffset.UTC
            )
        } catch (_: Exception) {
            return iso
        }
    }
    val d = Duration.between(dt.toInstant(), OffsetDateTime.now().toInstant())
    val s = d.seconds
    return when {
        s < 60 -> "à l'instant"
        s < 3600 -> "il y a ${s / 60} min"
        s < 86_400 -> "il y a ${s / 3600} h"
        s < 2_592_000 -> "il y a ${s / 86_400} j"
        s < 31_536_000 -> "il y a ${s / 2_592_000} mois"
        else -> "il y a ${s / 31_536_000} an${if (s / 31_536_000 > 1) "s" else ""}"
    }
}
