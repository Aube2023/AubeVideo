package com.aubeetoilee.aubevideo.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.aubeetoilee.aubevideo.AubeVideoApplication
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(app: AubeVideoApplication, navController: NavController) {
    val themePref by app.session.theme.collectAsState(initial = "system")
    val username by app.session.username.collectAsState(initial = null)
    val scope = rememberCoroutineScope()

    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = { navController.popBackStack() }) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, "Retour")
            }
            Text("Paramètres", style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold)
        }
        HorizontalDivider()

        SectionLabel("Compte")
        Text(
            username?.let { "Connecté en tant que @$it" } ?: "Non connecté",
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
        )
        TextButton(onClick = {
            scope.launch {
                runCatching { app.network.api.logout() }
                app.session.clear()
                navController.navigate("login") {
                    popUpTo("home") { inclusive = true }
                }
            }
        }) {
            Text("Se déconnecter", color = MaterialTheme.colorScheme.error)
        }

        SectionLabel("Apparence")
        listOf("system" to "Système", "dark" to "Sombre", "light" to "Clair").forEach { (key, label) ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .clickable { scope.launch { app.session.setTheme(key) } }
                    .padding(horizontal = 16.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RadioButton(selected = themePref == key, onClick = {
                    scope.launch { app.session.setTheme(key) }
                })
                Spacer(Modifier.padding(start = 8.dp))
                Text(label)
            }
        }

        Spacer(Modifier.height(16.dp))
        SectionLabel("À propos")
        Text(
            "AubeVideo — L'Aube Étoilée",
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            style = MaterialTheme.typography.bodyMedium,
        )
        Text(
            "Plateforme vidéo souveraine, sans pub, sans tracking.",
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.primary,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
    )
}
