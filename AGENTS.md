# Repository workflow

- Read the [native migration issue in Linear](https://linear.app/nouvelle-lune-atelier/issue/LUNE-625/replace-the-web-wrapper-with-a-tubify-style-native-desktop-app) for this app's scope and acceptance gates. [Tubify's native specification and QoL roadmap](https://linear.app/nouvelle-lune-atelier/issue/LUNE-367/publish-native-qol-roadmap-and-revised-player-specification) is the source for shared design and session behavior.
- Every implementation task needs its actual assigned LUNE issue before code work starts.
- Fetch origin and branch from origin/main. Branch names are exactly the issue identifier, for example `LUNE-625`; no descriptive suffixes or `agent/*` branches. One issue gets one branch and one PR targeting main.
- Commit subjects are `LUNE-XXX - Change-specific message`, describing the individual change in the imperative. Commit with the GitHub noreply email address; check `git config user.email` in each clone.
- Do not add AI tool attribution: no `Co-Authored-By` trailers, "Generated with" lines or tool mentions in commits, PR descriptions, code, comments or docs.
- Merge PRs with a merge commit only after the issue is complete, review concerns are resolved and required checks pass for the current head. Stop at a reviewable, green PR unless the owner asks to merge. Do not push directly to main.
- This app retains maintainer-created `v*` releases. Tubify's automatic experimental/stable publishing, signing and updater infrastructure are not installed here. Do not add them without an issue requesting them. Only maintainers tag, after updating the version in `pyproject.toml`.

## Native architecture

- Native-only Python/PySide6 and Qt Quick/QML. Do not reintroduce a web wrapper, React, Rust shell or web build toolchain.
- `native/src/dam/app.py` launches the native shell; `state.py` exposes view state and dispatches jobs. QML lives under `native/src/dam/qml/`.
- `engine.py` owns SQLite, public imports, exact-video downloads and device sync. `provider.py` dispatches the private process protocol; `jobs.py` handles asynchronous process transport. Keep network, extraction and database work off the GUI thread. No network listener.
- `account/` carries Tubify's session parsing, browser import, OS keyring, account validation and reconnect lifecycle. `theme.py`, QML theme tokens and shared controls carry its design language. Keep ports compatible and retain upstream license notices in `assets/`.
- Keep small interfaces between account, catalog/download work and views. QML receives normalized application data, never cookies, request headers, raw provider responses or signed media URLs.
- Session storage uses `studio.nouvellelune.digitalaudiomanager`; never read, overwrite or delete Tubify's vault entries. Browser reading happens only for explicit connection or renewal of a remembered connection. Sign-out must forget that browser and stop silent reconnection. A rejected replacement must preserve the working session.
- Keep shared code portable across Windows, macOS and Linux. Use Qt standard paths; isolate OS integrations and packaging. Local browsing and downloaded files must remain available without a network connection or unlocked keyring.
- New libraries use the system Music folder inside `Digital Audio Manager/Library`. Selecting another Music folder affects future downloads; preserve existing absolute file references. Device exports write only inside `<selected folder>/Digital Audio Manager`, retaining staged verification, the manifest and the 8,000-file guard.
- Preserve `MP3_MAKER_*`, `mp3-maker.sqlite3` and existing legacy folders. Schema changes belong in `connect()` and upgrade existing databases in place. Never silently move, reset or delete existing libraries.
- Download the exact track video ID, never a search substitute. Credentials stay in the worker and secure OS vault, never in download arguments or temporary cookie files.
- Declare runtime dependencies in `pyproject.toml` and keep `uv.lock` current; CI installs it with `uv sync --locked`. Use standard-library tools where they suffice. Keep changes focused; avoid placeholder integrations, speculative abstractions and duplicate state.

## Design and verification

- Match Tubify's semantic theme roles, bundled Roboto, pill actions, consistent spacing/radii, artwork-led headers and virtualized lists. Do not hardcode page-specific palettes. Keep visible keyboard focus, useful empty/error states, reduced-motion support and a 920×620 minimum.
- Tests use temporary folders through `MP3_MAKER_APP_DATA` and `MP3_MAKER_LIBRARY`. Patch provider calls, browser readers and keyrings; tests must not contact accounts or networks.
- Run before a PR:

```sh
python -m pip install -e '.[test,build]'
python -m ruff check native/src tests scripts
python -m pytest -q
python scripts/check_native.py
python -m PyInstaller --noconfirm packaging/desktop.spec
```

- CI runs those checks on pull requests and main for Windows, macOS and Linux, including packaged launch/render checks. Inspect synthetic renders at 920×620, 1280×820 and 1600×900; include loading, empty and error cases for UI changes.
- Keep real-account and real-device verification separate from fixtures. A passing fixture suite is not evidence of browser/keyring interoperability, authenticated downloads or device behavior on another OS. Record those gates honestly before release.
- Keep browser sessions, cookies, private screenshots, account data, downloaded media, local databases and personal profile URLs out of commits, logs and Linear tickets.
