package com.aubeetoilee.aubevideo.ui.screens

import android.content.Intent
import android.os.Build
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.foundation.background
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import androidx.navigation.NavController
import com.aubeetoilee.aubevideo.AubeVideoApplication
import com.aubeetoilee.aubevideo.BuildConfig
import kotlinx.coroutines.launch
import kotlin.math.cos
import kotlin.math.sin

@Composable
fun LoginScreen(app: AubeVideoApplication, navController: NavController) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var otp by remember { mutableStateOf("") }
    var needOtp by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current

    LaunchedEffect(Unit) {
        if (!app.session.currentToken().isNullOrBlank()) {
            navController.navigate("home") { popUpTo("login") { inclusive = true } }
        }
    }

    val fieldShape = RoundedCornerShape(14.dp)
    // Champs lisibles sur le fond sombre quel que soit le thème système
    val fieldColors = OutlinedTextFieldDefaults.colors(
        focusedTextColor = Color.White,
        unfocusedTextColor = Color.White,
        cursorColor = Color(0xFFF7B545),
        focusedBorderColor = Color(0xFFF7B545),
        unfocusedBorderColor = Color(0xFF3C5070),
        focusedLabelColor = Color(0xFFF7B545),
        unfocusedLabelColor = Color(0xFF9FB0CC),
    )
    // Fond façon landing page : ciel d'aube (nuit étoilée → bleu)
    val dawnBrush = Brush.verticalGradient(
        listOf(Color(0xFF0D1626), Color(0xFF16243F), Color(0xFF1E3458)),
    )
    Box(Modifier.fillMaxSize().background(dawnBrush)) {
        Column(
            Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            // Logo soleil rayonnant + play central (identité Aube, repris du logo.svg)
            com.aubeetoilee.aubevideo.ui.components.SunLogo(size = 88.dp, withHalo = true)
            Spacer(Modifier.height(18.dp))
            Text(
                buildAnnotatedString {
                    withStyle(SpanStyle(color = Color.White)) { append("Aube") }
                    withStyle(SpanStyle(color = Color(0xFFF7B545))) { append("Video") }
                },
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                "La plateforme vidéo de L'Aube Étoilée",
                style = MaterialTheme.typography.bodyMedium,
                color = Color(0xFF9FB0CC),
            )
            Spacer(Modifier.height(36.dp))

            OutlinedTextField(
                value = username, onValueChange = { username = it },
                label = { Text("Identifiant") }, singleLine = true,
                shape = fieldShape, colors = fieldColors,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = password, onValueChange = { password = it },
                label = { Text("Mot de passe") }, singleLine = true,
                shape = fieldShape, colors = fieldColors,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Password,
                    imeAction = if (needOtp) ImeAction.Next else ImeAction.Done,
                ),
                modifier = Modifier.fillMaxWidth(),
            )
            if (needOtp) {
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = otp, onValueChange = { otp = it.filter(Char::isDigit).take(6) },
                    label = { Text("Code 2FA") }, singleLine = true,
                    shape = fieldShape, colors = fieldColors,
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.NumberPassword,
                        imeAction = ImeAction.Done,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                )
            }

            error?.let {
                Spacer(Modifier.height(16.dp))
                Text(it, color = MaterialTheme.colorScheme.error)
            }

            Spacer(Modifier.height(24.dp))
            Button(
                onClick = {
                    error = null
                    loading = true
                    scope.launch {
                        try {
                            val device = "${Build.MANUFACTURER} ${Build.MODEL}"
                            val resp = app.network.api.login(
                                com.aubeetoilee.aubevideo.net.LoginRequest(
                                    username.trim().lowercase(),
                                    password,
                                    device = device,
                                    platform = "android",
                                    otp = otp.ifBlank { null },
                                )
                            )
                            app.session.setSession(
                                token = resp.token,
                                username = resp.user.username,
                                displayName = resp.user.displayName,
                            )
                            navController.navigate("home") { popUpTo("login") { inclusive = true } }
                        } catch (e: retrofit2.HttpException) {
                            val body = try {
                                val raw = e.response()?.errorBody()?.string().orEmpty()
                                app.network.json.decodeFromString(
                                    com.aubeetoilee.aubevideo.net.ErrorBody.serializer(), raw
                                )
                            } catch (_: Exception) { null }
                            val msg = body?.error ?: "Erreur ${e.code()}"
                            if (msg.contains("2FA", ignoreCase = true)) {
                                needOtp = true
                                if (!otp.isBlank()) error = msg
                            } else error = msg
                        } catch (e: Exception) {
                            error = "Connexion impossible : ${e.message}"
                        } finally {
                            loading = false
                        }
                    }
                },
                enabled = !loading && username.isNotBlank() && password.isNotBlank(),
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth().height(50.dp),
            ) {
                if (loading) CircularProgressIndicator(strokeWidth = 2.dp)
                else Text("Se connecter", fontWeight = FontWeight.SemiBold)
            }

            Spacer(Modifier.height(12.dp))
            TextButton(onClick = {
                val url = BuildConfig.BASE_URL.trimEnd('/') + "/register"
                ctx.startActivity(Intent(Intent.ACTION_VIEW, url.toUri()))
            }) {
                Text(
                    "Pas encore de compte ? Créez-le sur le site",
                    color = Color(0xFF9FB0CC),
                )
            }
        }
    }
}
