package com.aubeetoilee.aubevideo.net

import com.aubeetoilee.aubevideo.BuildConfig
import com.aubeetoilee.aubevideo.data.SessionManager
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit

class NetworkModule(private val session: SessionManager) {

    val json = Json {
        ignoreUnknownKeys = true
        coerceInputValues = true
        encodeDefaults = false
    }

    private val tokenInterceptor = Interceptor { chain ->
        val token = runBlocking { session.currentToken() }
        val req: Request = if (token.isNullOrBlank()) chain.request() else
            chain.request().newBuilder()
                .header("Authorization", "Bearer $token")
                .build()
        chain.proceed(req)
    }

    private val loggingInterceptor = HttpLoggingInterceptor().apply {
        level = if (BuildConfig.DEBUG)
            HttpLoggingInterceptor.Level.BASIC
        else HttpLoggingInterceptor.Level.NONE
    }

    private val httpClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(120, TimeUnit.SECONDS)
        .addInterceptor(tokenInterceptor)
        .addInterceptor(loggingInterceptor)
        .build()

    /** Client séparé pour Coil — pas de log, pas d'auth requise (URLs publiques). */
    val imageHttpClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    val api: AubeVideoApi = Retrofit.Builder()
        .baseUrl(BuildConfig.BASE_URL)
        .client(httpClient)
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()
        .create(AubeVideoApi::class.java)

    val mediaHttpClient: OkHttpClient get() = httpClient
}
