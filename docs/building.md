# Building the native app

Digital Audio Manager uses Python, PySide6 Essentials and Qt Quick/QML, matching Tubify's native stack. Python 3.12 or later is required for source installs; CI uses Python 3.14. Packaged apps include Python and Qt.

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

Output is under `dist/`: a macOS `.app` and a portable application directory on Windows/Linux. Keep the entire directory together. Linux builds require the target system's Qt platform libraries; build on the oldest supported distribution rather than copying a build from a newer libc system. macOS builds target the architecture of the machine running the build. Windows builds include an executable and its supporting files. These are unsigned native packages, with no updater.

Qt's [PyInstaller deployment guide](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html) describes platform packaging. Folder defaults use [QStandardPaths](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QStandardPaths.html), including localized Music folders.

## Releases

PR and main CI build and check native packages on Windows, macOS and Linux. Tag releases archive those native builds as ZIPs; they do not produce the old web-wrapper installers. A maintainer updates `pyproject.toml`, completes real-account/platform checks and pushes a `v*` tag. Publication waits for all platform package jobs to succeed. No release is created by ordinary branch work.
