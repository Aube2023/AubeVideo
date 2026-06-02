package com.aubeetoilee.aubevideo.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "auth_prefs")

class SessionManager(private val context: Context) {

    private val tokenKey = stringPreferencesKey("auth_token")
    private val usernameKey = stringPreferencesKey("username")
    private val displayNameKey = stringPreferencesKey("display_name")
    private val themeKey = stringPreferencesKey("theme")

    val token: Flow<String?> = context.dataStore.data.map { it[tokenKey] }
    val username: Flow<String?> = context.dataStore.data.map { it[usernameKey] }
    val displayName: Flow<String?> = context.dataStore.data.map { it[displayNameKey] }
    val theme: Flow<String> = context.dataStore.data.map { it[themeKey] ?: "system" }

    suspend fun currentToken(): String? = token.first()

    suspend fun setSession(token: String, username: String, displayName: String) {
        context.dataStore.edit {
            it[tokenKey] = token
            it[usernameKey] = username
            it[displayNameKey] = displayName
        }
    }

    suspend fun clear() {
        context.dataStore.edit {
            it.remove(tokenKey)
            it.remove(usernameKey)
            it.remove(displayNameKey)
        }
    }

    suspend fun setTheme(theme: String) {
        context.dataStore.edit { it[themeKey] = theme }
    }
}
