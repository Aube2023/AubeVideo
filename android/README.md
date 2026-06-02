# AubeVideo Android

Application Android native pour AubeVideo, écrite en **Kotlin + Jetpack Compose**.

## Stack
- Kotlin 2.0.21, JDK 17
- Jetpack Compose Material 3 (BOM 2024.11)
- Navigation Compose, Lifecycle, DataStore
- Media3 / ExoPlayer 1.5.0 (HLS, PiP, background playback)
- Retrofit 2 + OkHttp 4 + kotlinx.serialization
- Coil 3 pour les images
- Splash Screen API

## Architecture

```
app/src/main/java/com/aubeetoilee/aubevideo/
├── AubeVideoApplication.kt    # Application + injection légère
├── MainActivity.kt            # Activity unique (Compose)
├── data/SessionManager.kt     # DataStore : token, prefs, thème
├── net/                       # Retrofit + modèles API
│   ├── AubeVideoApi.kt
│   ├── Models.kt
│   └── NetworkModule.kt
├── player/                    # ExoPlayer
│   ├── PlaybackService.kt     # Background + notifications média
│   └── PlayerView.kt
├── ui/
│   ├── nav/AppNavigation.kt   # NavHost + tabs
│   ├── theme/                 # Theme.kt, Type.kt
│   ├── components/VideoCard.kt
│   └── screens/               # HomeScreen, WatchScreen, ShortsScreen,
│                              # SearchScreen, LibraryScreen,
│                              # ChannelScreen, SettingsScreen, LoginScreen
└── util/Formatters.kt         # views, durée, "il y a..."
```

## Build

### Prérequis
- Android Studio Ladybug | 2024.2.1+
- Android SDK 35 (compileSdk), 24+ (minSdk)
- JDK 17

### Configuration backend
Par défaut, l'app pointe sur `https://video.aubeetoilee.com/`. Pour
basculer sur un backend local :

```properties
# android/local.properties (gitignored)
aubevideo.baseUrl=http://10.0.2.2:5017/
```

`10.0.2.2` est l'IP de l'hôte vu depuis l'émulateur Android.
Le `network_security_config.xml` autorise déjà le clair sur cette adresse.

### Lancement
```bash
cd android
./gradlew :app:installDebug   # installe sur appareil/émulateur
./gradlew :app:assembleRelease  # APK signé (à configurer)
```

## Features livrées (v1)

- ✅ Auth PAM via API Bearer (avec support 2FA TOTP)
- ✅ Feed (toutes / catégorie / recommandé / tendances)
- ✅ Lecteur ExoPlayer avec chapitres, sous-titres, qualités
- ✅ Background playback + Picture-in-Picture
- ✅ Shorts en `VerticalPager` (auto-loop)
- ✅ Recherche + suggestions auto-complétion
- ✅ Détail vidéo : likes/dislikes, partage, watch later, abonnement
- ✅ Commentaires (lecture + publication)
- ✅ Chaînes, abonnements, mes abonnements
- ✅ Bibliothèque : historique, à regarder plus tard
- ✅ Thème sombre / clair / système avec couleurs L'Aube Étoilée
- ✅ Deep linking `/watch/{id}` et `/c/{username}`
- ✅ Sauvegarde automatique de la position de lecture
- ✅ Splash screen API 31+

## Endpoints API utilisés
Tous sous `/api/v1/` du backend Flask AubeVideo. Authentification par
`Authorization: Bearer av_xxx` obtenue via `POST /api/v1/auth/login`.

Voir `app.py` côté serveur pour la liste complète.
