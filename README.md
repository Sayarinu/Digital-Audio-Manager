# Digital Audio Manager

Local music-library management and physical-playlist export for portable players.

Digital Audio Manager imports public YouTube Music playlists, queues exact video IDs, keeps a local library, and exports copied playlist folders to mounted devices. It has no telemetry, cloud database, browser-cookie import, or account write access.

## Install and run

```sh
pnpm install
python3 -m pip install --target python/vendor -r python/requirements.txt
pnpm tauri dev
```

The profile field starts empty. Configure a public YouTube Music profile in Settings when you want to import a catalog.

## Build desktop packages

```sh
pnpm build:desktop
```

Tauri builds native packages for the host platform. GitHub Actions builds release assets for each desktop platform when a `v*` tag is pushed:

- macOS: separately signed and notarized `.app` and `.dmg` installers for Apple Silicon and Intel
- Windows: `.msi` and `.exe` (NSIS)
- Linux: `.AppImage` and `.deb`

Local builds are unsigned and may trigger platform security warnings. Tagged releases require Apple Developer ID signing and notarization, so distributed macOS installers open normally through Gatekeeper.

## First-launch setup and manual updates

On a clean desktop install, the app automatically uses existing `yt-dlp` and Node installations when present. Otherwise, at first launch it installs managed copies into its Application Support directory: the official yt-dlp release binary and the latest Node LTS runtime, verified against Node's official checksum manifest. No Homebrew or manual PATH setup is required.

The app does not check for or install updates automatically. To update, download the newest installer from GitHub Releases and install it over the existing app. Releases contain only normal platform installers; no updater `.sig` assets are published.

Before publishing a tag, set these GitHub Actions secrets:

- `APPLE_CERTIFICATE`: base64-encoded `.p12` export of a **Developer ID Application** certificate.
- `APPLE_CERTIFICATE_PASSWORD`: password used to export that `.p12` file.
- `APPLE_SIGNING_IDENTITY`: the complete Developer ID Application identity, including the team ID.
- `APPLE_ID`, `APPLE_PASSWORD`, and `APPLE_TEAM_ID`: Apple ID, its app-specific password, and Apple Developer team ID used for notarization.

The macOS release job stops before building when any of these secrets are unavailable, so an unsigned macOS release cannot be published by accident.

## Verify

```sh
PYTHONPYCACHEPREFIX=/tmp/dam-pycache python3 -m unittest discover -s tests -v
pnpm run build
cargo check --manifest-path src-tauri/Cargo.toml
```

## Legal and source quality

YouTube Premium offline downloads are encrypted and app-only. This project uses public metadata and an experimental anonymous downloader; use it only for media you are authorized to keep. Source media from YouTube Music is lossy, so an MP3 conversion is not lossless.

The project is available under the [MIT License](LICENSE).
