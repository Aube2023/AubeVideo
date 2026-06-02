package com.aubeetoilee.aubevideo.ui.screens

import android.os.Build
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.aubeetoilee.aubevideo.AubeVideoApplication
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(app: AubeVideoApplication, navController: NavController) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var otp by remember { mutableStateOf("") }
    var needOtp by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        if (!app.session.currentToken().isNullOrBlank()) {
            navController.navigate("home") { popUpTo("login") { inclusive = true } }
        }
    }

    Box(Modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("AubeVideo", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary)
            Text("L'Aube Étoilée", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(32.dp))

            OutlinedTextField(
                value = username, onValueChange = { username = it },
                label = { Text("Identifiant") }, singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = password, onValueChange = { password = it },
                label = { Text("Mot de passe") }, singleLine = true,
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
                modifier = Modifier.fillMaxWidth().height(48.dp),
            ) {
                if (loading) CircularProgressIndicator(strokeWidth = 2.dp)
                else Text("Se connecter")
            }
        }
    }
}
