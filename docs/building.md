# Building from source

Digital Audio Manager is a [Tauri 2](https://tauri.app) app: a React and TypeScript interface, a thin Rust shell, and a Python worker that does the importing, downloading and device syncing.

## Prerequisites

- **Node.js 22** and **pnpm 10** (CI uses these versions; pnpm 11 stops on the lockfile's ignored build scripts)
- **Rust** stable, via [rustup](https://rustup.rs)
- **Python 3** (CI uses 3.12) with `pip`
- **FFmpeg** on your PATH, for MP3 conversion, cover art and device syncs
- The [Tauri system dependencies](https://tauri.app/start/prerequisites/) for your platform. On Debian or Ubuntu:

  ```sh
  sudo apt-get install -y libwebkit2gtk-4.1-dev build-essential libssl-dev libgtk-3-dev \
    libayatana-appindicator3-dev librsvg2-dev patchelf libfuse2 file
  ```

## Set up

```sh
pnpm install --frozen-lockfile
python3 -m pip install --target python/vendor -r python/requirements.txt
```

`python/vendor` holds the worker's Python dependencies. It is git-ignored and bundled into the app, and the Rust build fails until it exists.

Optionally copy `.env.example` to `.env` and set `VITE_DEFAULT_PROFILE_URL` to prefill the profile field in Settings.

## Run in development

```sh
pnpm tauri dev
```

This starts Vite on `http://localhost:1420` and opens the app. In development the Rust shell runs `python/worker.py` straight from the repository, so worker changes apply on the next action without a rebuild.

To keep test data away from your real library, point the worker at other folders:

```sh
MP3_MAKER_APP_DATA=/tmp/dam-data MP3_MAKER_LIBRARY=/tmp/dam-library pnpm tauri dev
```

## Verify

These are the checks CI runs:

```sh
PYTHONPYCACHEPREFIX=/tmp/dam-pycache python3 -m unittest discover -s tests -v
pnpm run build
cargo check --manifest-path src-tauri/Cargo.toml
```

## Build installers

Tauri builds installers for the platform you build on. Pass the bundle types the release workflow uses:

```sh
pnpm tauri build --bundles app,dmg        # macOS
pnpm tauri build --bundles msi,nsis       # Windows
pnpm tauri build --bundles appimage,deb   # Linux
```

On macOS, add `--target aarch64-apple-darwin` or `--target x86_64-apple-darwin` (after `rustup target add` for it) to build for a specific architecture. Output goes to `src-tauri/target/release/bundle/` (or `src-tauri/target/<target>/release/bundle/`).

`pnpm build:desktop` runs `tauri build` with the default bundle setting from `tauri.conf.json`, which only produces the macOS `.app`.

## Releasing

1. Bump the version in `package.json`, `src-tauri/Cargo.toml`, `src-tauri/Cargo.lock` and `src-tauri/tauri.conf.json`.
2. Merge the change into `main`.
3. Push a tag such as `v1.0.2`. The **Release desktop builds** workflow builds every platform and publishes a GitHub release with the installers.

Releases are unsigned, and there is no in-app updater, so no signing or updater secrets are needed.
