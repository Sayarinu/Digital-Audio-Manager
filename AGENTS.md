# Repository guide

## Stack

- **UI:** React 18 and TypeScript, built with Vite (`src/`)
- **Shell:** Tauri 2 in Rust (`src-tauri/`)
- **Worker:** Python 3 standard library plus vendored [ytmusicapi](https://github.com/sigma67/ytmusicapi) (`python/`), driving `yt-dlp`, Node.js and FFmpeg, with state in SQLite
- **Package manager:** pnpm 10

## Layout

- `src/App.tsx`: the whole interface (Library, Queue, Device and Settings views)
- `src/api.ts`, `src/types.ts`: typed calls into the shell and the worker's response shapes
- `src-tauri/src/lib.rs`: Tauri commands; finds and launches the worker, runs the download queue on a background thread, opens the library folder
- `src-tauri/tauri.conf.json`: app metadata, window and bundled resources (`python/worker.py`, `python/vendor`)
- `python/worker.py`: every operation (imports, queue, downloads, metadata repair, device sync, tool setup)
- `tests/test_worker.py`: worker unit tests
- `docs/building.md`: development setup, installers and releases
- `.github/workflows/`: `ci.yml` (push to main) and `release.yml` (`v*` tags)

## Commands

```sh
pnpm install --frozen-lockfile
python3 -m pip install --target python/vendor -r python/requirements.txt   # required before any Rust build
pnpm tauri dev                                                              # run the app
pnpm run build                                                              # type-check and build the UI
PYTHONPYCACHEPREFIX=/tmp/dam-pycache python3 -m unittest discover -s tests -v
cargo check --manifest-path src-tauri/Cargo.toml
pnpm tauri build --bundles appimage,deb                                     # installers; see docs/building.md per platform
```

Run the Python tests, the UI build and `cargo check` before opening a PR. CI only runs on pushes to `main`, not on pull requests.

## Architecture rules

- All work happens in the Python worker. The UI calls the `worker_command` Tauri command with a method name and payload; the shell runs `worker.py` once per call, passing the request as JSON in `MP3_MAKER_REQUEST`, and returns `{"ok": true, "data": ...}` or `{"ok": false, "error": ...}`. Add new operations to `OPERATIONS` in `worker.py` and a matching wrapper in `src/api.ts`.
- Operations that change state return `dashboard()` so the UI can replace its state in one step. Raise `WorkerError` with a sentence a user can act on; anything else is reported as an unexpected error.
- Keep the Rust shell thin: process launching, the background queue thread and OS integration only. No business logic in Rust.
- The worker opens no network listener, never signs in and never reads browser cookies. It reads public data only and downloads the exact video ID for each track, never a search substitute.
- Device syncs only write inside `<volume>/Digital Audio Manager`. Keep the stage, verify and swap flow, the manifest and the 8,000-file guard.
- Keep the legacy "MP3 Maker" names (`MP3_MAKER_*` variables, `mp3-maker.sqlite3`, the legacy folders) unless you add a migration; existing libraries depend on them.
- Schema changes go in `connect()` and must upgrade existing databases in place (see the `kind` column).
- The worker stays standard-library only apart from `python/requirements.txt`, which is vendored and bundled. Pin new dependencies there.
- The app is unsigned and has no auto-updater; don't reintroduce either without an issue that asks for it.
- Tests use temporary folders through `MP3_MAKER_APP_DATA` and `MP3_MAKER_LIBRARY` and must not touch the network; patch `YTMusic`, `ytdlp_public_json` and similar calls.

## Branches, commits and pull requests

- Maintainers track work in Linear. Every change needs its issue first, and the branch name is exactly the issue ID (for example `LUNE-574`).
- Contributors without Linear access open a GitHub issue first and use `GH-<issue number>` (for example `GH-12`) wherever a LUNE ID appears below.
- Branch from `main`, one issue per branch and one PR per issue, targeting `main`.
- Commit subjects are `LUNE-XXX - Change-specific message`: imperative, describing that commit's change rather than repeating the issue title.
- Commit with your GitHub noreply email address, never a personal one. Check `git config user.email` in each new clone.
- Do not add AI tool attribution anywhere: no `Co-Authored-By` trailers, "Generated with" lines or tool mentions in commits, PR descriptions, code, comments or docs.
- PRs are merged with a merge commit (not squash or rebase) once the checks above pass and review is resolved.
- Pushing a `v*` tag runs the release workflow and publishes a public GitHub release, so only maintainers tag, after bumping the version in `package.json`, `src-tauri/Cargo.toml`, `src-tauri/Cargo.lock` and `src-tauri/tauri.conf.json`.
- Keep downloaded media, local databases, cookies and personal profile URLs out of commits, logs and issues.
