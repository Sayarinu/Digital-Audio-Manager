# Building the native app

Digital Audio Manager uses Python, PySide6 Essentials/Addons and Qt Quick/QML, matching Tubify's native stack. Python 3.12 or later is required for source installs; CI uses Python 3.14. Packaged apps include Python and Qt.

## Development

```sh
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[test,build]'
digital-audio-manager
```

For the exact CI environment, install `uv==0.12.5` and run `uv sync --locked --extra test --extra build`; `uv.lock` pins dependencies for every supported platform.

Install FFmpeg and ffprobe through your platform's package manager. Node.js is used by the downloader; Settings → Set up tools installs a managed Node runtime if none is available. yt-dlp and its JavaScript support are bundled Python dependencies. This app does not run a development server.

For isolated development, set `MP3_MAKER_APP_DATA` and `MP3_MAKER_LIBRARY` to temporary folders. The explicit library override disables the folder chooser. Existing installations keep their previous catalog and downloads automatically.

## Checks and previews

```sh
python -m ruff check native/src tests scripts
python -m pytest -q
python scripts/check_native.py
python -m dam --fixture
python -m dam --smoke-test --view settings --width 920 --height 620 --screenshot /tmp/settings.png
```

`--fixture` and `--smoke-test` use synthetic data and temporary paths, without loading credentials or reading browser sessions. `--theme youtube-music-purple` selects Tubify's Midnight Violet theme for a synthetic preview; `--empty` renders empty states. `check_native.py` exercises every page at all three supported test sizes and fails on QML runtime errors.

The test suite checks the retained worker, account/keyring lifecycle, provider transport, path compatibility, download destination selection and failure recovery. It does not replace real-browser sign-in, authenticated download or mounted-device checks. Test those on Windows, macOS and Linux before release, keeping credentials and private account screenshots outside the repository.

## Desktop packages

Build on each target platform:

```sh
python -m PyInstaller --noconfirm packaging/desktop.spec
```

Output is under `dist/`: a macOS `.app` and a portable application directory on Windows/Linux. Keep the entire directory together. Linux builds require the target system's Qt platform libraries and PulseAudio client library (`libpulse0` on Ubuntu); build on the oldest supported distribution rather than copying a build from a newer libc system. macOS builds target the architecture of the machine running the build. Windows builds include an executable and its supporting files. The app includes Qt Multimedia’s decoder backend. Native audio checks decode generated silence without using speakers. Release archives are signed with an app-specific Ed25519 key; OS signing/notarization is not configured.

Qt's [PyInstaller deployment guide](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html) describes platform packaging. Folder defaults use [QStandardPaths](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QStandardPaths.html), including localized Music folders.

## Releases

PR checks build and verify packages on Windows, macOS and Linux. Feature PRs target experimental; a reviewed promotion PR brings experimental to main. Merging publishes automatically: experimental creates prereleases, while main creates Stable releases. Release tags use Digital-Audio-Manager-X.Y.Z and Digital-Audio-Manager-Experimental-X.Y.ZbN. The largest merged PR label selects Major Release, Feature, or a patch bump, using Tubify's version rules.

The release workflow stamps assets/build-version.txt, preserves executable modes and macOS framework links in platform ZIPs, and signs each archive using the DAM_UPDATE_PRIVATE_KEY repository secret. Its public key is embedded in assets/update-public-key. Publication waits for all platform checks and signatures. Private keys must never enter source, build artifacts or logs.

Settings → Updates selects Stable/Experimental and automatic checks. Downloads require fresh GitHub metadata, exact platform/architecture matching, SHA-256 integrity and the embedded Ed25519 signature. A verified archive is staged beside the installed app. A detached OS helper waits for shutdown, swaps only the app folder, rolls back a failed swap and restarts. Source installs or non-writable locations use Release Details for manual upgrades. Settings, media and device exports remain outside the app folder; updates refuse installations containing referenced user data. No release is published from a feature branch or PR check.
