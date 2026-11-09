<div align="center">

<img src="src-tauri/icons/icon.png" alt="Digital Audio Manager" width="96" height="96">

# Digital Audio Manager

**Your YouTube Music playlists, on a music player that has no internet.**

Digital Audio Manager imports your public YouTube Music playlists, downloads the tracks into a local library on your computer, and copies the playlists you choose onto a portable music player as plain folders. No account sign-in, no browser cookies, no telemetry.

[![Latest release](https://img.shields.io/github/v/release/Sayarinu/Digital-Audio-Manager?label=release&sort=semver)](https://github.com/Sayarinu/Digital-Audio-Manager/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Sayarinu/Digital-Audio-Manager/total)](https://github.com/Sayarinu/Digital-Audio-Manager/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

[**Download**](#download) · [Features](#features) · [Getting started](#getting-started) · [FAQ](#faq)

</div>

---

## Features

### Import
- **Sync a whole profile.** Paste a public YouTube Music channel or `@handle` and every playlist on its public Playlists tab is imported. Playlists that can't be read are skipped and reported.
- **Quick import** a single public playlist or album URL into the **Unsorted** collection and queue its tracks in one step.
- Removed or unavailable videos keep their place in the playlist and are marked **Unavailable** instead of silently disappearing.

### Download
- **A download queue** that runs in the background, one track at a time, with retry and cancel for each job.
- **Exact videos only.** Each track is downloaded from its own video ID; nothing is swapped for a search result.
- **Keeps the original audio** as M4A when YouTube offers it, and falls back to a 320 kbps MP3 otherwise.
- **Cover art and tags.** Album art is embedded, title and artist tags are written, and files are organized by artist.
- **Plays it safe.** The queue pauses when YouTube rate-limits or asks for a bot check, and downloads stop when free disk space drops below a safety reserve.
- **Repair metadata** looks up tracks saved as "Unknown artist" again and renames them.

### Copy to your player
- **Pick the playlists** that belong on the device, then **preview** what will be added, removed and how much space it takes.
- **Safe syncs.** Files are staged and checked first, then swapped in, and only the app's own folder on the device is ever touched.
- Each playlist becomes a numbered folder, with tags that keep it grouped and in order on players that sort by album.
- An 8,000-file limit protects smaller players. The device page is set up for the Echo Nano, but any player that mounts as a drive works.

### Setup
- On first launch the app uses your existing `yt-dlp` and Node.js, or installs its own copies: the official yt-dlp release and the current Node.js LTS, checked against Node's published checksums.

## Download

Get the latest version from the **[Releases page](https://github.com/Sayarinu/Digital-Audio-Manager/releases/latest)**.

| Platform | File | Notes |
|---|---|---|
| **Windows** | `Digital.Audio.Manager_1.0.1_x64-setup.exe` | Installer for Windows 10 or 11, 64-bit |
| | `Digital.Audio.Manager_1.0.1_x64_en-US.msi` | Same app as an MSI package |
| **macOS** | `Digital.Audio.Manager_1.0.1_aarch64.dmg` | Apple silicon (M1 and later) |
| | `Digital.Audio.Manager_1.0.1_x64.dmg` | Intel Macs |
| **Linux** | `Digital.Audio.Manager_1.0.1_amd64.AppImage` | Runs on most x86_64 distributions |
| | `Digital.Audio.Manager_1.0.1_amd64.deb` | Debian, Ubuntu and derivatives |

The releases also include `.app.tar.gz` archives of the macOS app bundle. Most people want the `.dmg` instead.

All platforms need **Python 3** installed, because downloads and device syncs run in a small Python helper. **FFmpeg** is needed for MP3 conversion, cover art and device syncs; the app shows whether it was found in **Settings → Tools**.

<details>
<summary><b>Windows</b></summary>

Run the `.exe` installer (or the `.msi`). If Windows SmartScreen warns about an unrecognized app, choose **More info → Run anyway**.

Install Python 3 from [python.org](https://www.python.org/downloads/) with **Add python.exe to PATH** checked, and install FFmpeg (for example `winget install Gyan.FFmpeg`).

</details>

<details>
<summary><b>macOS</b></summary>

Open the disk image that matches your Mac and drag **Digital Audio Manager** to **Applications**. The app isn't signed or notarized by Apple, so the first time you open it, Control-click the app, choose **Open**, then confirm. Alternatively, open it from **System Settings → Privacy & Security → Open Anyway**.

Python 3 comes with Apple's Command Line Tools (`xcode-select --install`) or from Homebrew. Install FFmpeg with `brew install ffmpeg`.

</details>

<details>
<summary><b>Linux</b></summary>

AppImage:

```sh
chmod +x Digital.Audio.Manager_1.0.1_amd64.AppImage
./Digital.Audio.Manager_1.0.1_amd64.AppImage
```

Debian or Ubuntu:

```sh
sudo apt install ./Digital.Audio.Manager_1.0.1_amd64.deb
```

Install `python3` and `ffmpeg` from your distribution's packages.

</details>

### Updating

The app doesn't check for updates. To update, download the newest installer from the [Releases page](https://github.com/Sayarinu/Digital-Audio-Manager/releases) and install it over the existing app. Your library and settings are kept.

## Getting started

1. Open the app. On first launch it sets up `yt-dlp` and Node.js; check **Settings → Tools** to see that everything shows **Ready**.
2. In **Settings → Profile URL**, paste your public YouTube Music profile (for example `https://music.youtube.com/@your-handle`) and choose **Sync**. To grab a single playlist or album instead, paste its link under **Quick import**.
3. In **Library**, pick a playlist and choose **Download missing**. Progress shows in **Queue**.
4. Connect your player, open **Device**, enter the drive's path (for example `/Volumes/ECHO_NANO` on macOS), turn on the playlists you want, then choose **Preview** and **Sync**.

> **Tip:** Your playlists must be public, and so must the Playlists tab on your profile. Private and unlisted playlists can't be read without signing in, and the app never signs in.

## FAQ

**Do I need a Google account or YouTube Music Premium?**
No. The app only reads public playlists and never signs in or reads browser cookies.

**What audio quality do I get?**
The best audio stream YouTube offers for that video. It's saved as M4A without re-encoding when possible, otherwise converted to a 320 kbps MP3. YouTube's audio is already lossy, so neither format is lossless.

**Downloads stopped with a rate-limit or bot-check error.**
The queue pauses on purpose when YouTube pushes back. Wait a while, then choose **Run queue**, or retry the failed tracks from **Queue**.

**Where are my files?**
Downloaded music is in `Music/Digital Audio Manager/Library` in your home folder, sorted into one folder per artist. **Device → Open library** opens it. The app's database and helper tools are in `Library/Application Support/Digital Audio Manager` in your home folder, on every platform.

**What does a sync change on my player?**
Only the `Digital Audio Manager` folder at the root of the drive. Anything else on the player is left alone, and **Preview** shows the changes before you sync.

**Can I build it myself?**
Yes. See [Building from source](docs/building.md).

## Contributing

Bug reports, ideas and pull requests are welcome. Please open an [issue](https://github.com/Sayarinu/Digital-Audio-Manager/issues) first for larger changes. Development setup is in [docs/building.md](docs/building.md), and the project conventions are in [AGENTS.md](AGENTS.md).

## License

Digital Audio Manager is free and open-source software under the [MIT License](LICENSE).

It downloads and runs third-party tools, including [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [Node.js](https://nodejs.org), and bundles [ytmusicapi](https://github.com/sigma67/ytmusicapi); each is under its own license.

## Disclaimer

Digital Audio Manager is an independent, unofficial project. It is not affiliated with, endorsed by or sponsored by Google LLC or YouTube. YouTube and YouTube Music are trademarks of Google LLC. You are responsible for following YouTube's Terms of Service and the copyright law where you live; only download media you have the right to keep.
