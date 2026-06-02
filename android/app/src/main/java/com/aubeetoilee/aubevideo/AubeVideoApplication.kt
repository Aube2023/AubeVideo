package com.aubeetoilee.aubevideo

import android.app.Application
import coil3.ImageLoader
import coil3.PlatformContext
import coil3.SingletonImageLoader
import coil3.network.okhttp.OkHttpNetworkFetcherFactory
import com.aubeetoilee.aubevideo.data.SessionManager
import com.aubeetoilee.aubevideo.net.NetworkModule

class AubeVideoApplication : Application(), SingletonImageLoader.Factory {

    val session: SessionManager by lazy { SessionManager(applicationContext) }
    val network: NetworkModule by lazy { NetworkModule(session) }

    override fun newImageLoader(context: PlatformContext): ImageLoader =
        ImageLoader.Builder(context)
            .components {
                add(OkHttpNetworkFetcherFactory(callFactory = { network.imageHttpClient }))
            }
            .build()
}
