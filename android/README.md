# Mise for Android

A Trusted Web Activity (TWA) wrapper, generated with [Bubblewrap](https://github.com/GoogleChromeLabs/bubblewrap).
The app opens the live site, `https://billmiky.github.io/mise/`, full screen, so site changes need no app update.
Rebuild only to change the app itself: name, icon, shortcuts, or package settings.

- Package: `io.github.billmiky.mise`
- Settings: `twa-manifest.json`
- Address-bar verification: `https://billmiky.github.io/.well-known/assetlinks.json`, served from the
  `billmiky.github.io` repo. It must list this package and the signing key's SHA-256 fingerprint.

## Signing key

`mise.keystore` (alias `mise`) and its password are **not** in this repo. Keep them private.
Every update must be signed with the same key, or Android will refuse to install it over the existing app.

## Rebuild

Needs JDK 17+ and the Android SDK (`platforms;android-35`, `build-tools;35.0.0`).

1. Bump `appVersionCode` (and `appVersionName`) in `twa-manifest.json` and `app/build.gradle`.
2. Build:
   ```bash
   cd android
   echo "sdk.dir=$ANDROID_HOME" > local.properties
   ./gradlew assembleRelease
   ```
3. Align and sign:
   ```bash
   $ANDROID_HOME/build-tools/35.0.0/zipalign -f -p 4 app/build/outputs/apk/release/app-release-unsigned.apk aligned.apk
   $ANDROID_HOME/build-tools/35.0.0/apksigner sign --ks mise.keystore --ks-key-alias mise --out Mise.apk aligned.apk
   ```

Alternatively, with the Bubblewrap CLI (`npm i -g @bubblewrap/cli`), put the keystore here and run `bubblewrap update`
then `bubblewrap build`.
