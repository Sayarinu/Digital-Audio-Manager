# Native design contract

Digital Audio Manager shares Tubify's native Python/PySide6 and QML foundation. The reference is [Tubify's native specification](https://linear.app/nouvelle-lune-atelier/issue/LUNE-367/publish-native-qol-roadmap-and-revised-player-specification); the app-specific migration is [LUNE-625](https://linear.app/nouvelle-lune-atelier/issue/LUNE-625/replace-the-web-wrapper-with-a-tubify-style-native-desktop-app).

Use Classic by default and offer Tubify's theme presets, including Midnight Violet. All controls use semantic colors from `theme.py`, Roboto typography and `qml/Theme.js` spacing and corner radii. Navigation and collection shortcuts sit on the left, search and account actions at the top, and a persistent download-status bar at the bottom. A queue dock appears when there is enough room; smaller windows retain a full Queue page. Lists are virtualized, artwork loads asynchronously, and controls expose keyboard focus and readable labels.

The app manages files and device exports. It opens downloaded audio in the system player and has no hidden playback service. Library, Downloads, Queue, Devices and Settings remain useful without signing in. Account connection uses the same browser/keyring/renewal lifecycle as Tubify, in an independent credential namespace. Direct cross-app integration is deferred; there is no shared database, credential access or local HTTP API.

New downloads live inside a dedicated folder in the platform Music directory. The user may choose another Music folder; completed files retain their original absolute references. An unavailable drive must produce an actionable error, not a reset. Device sync stays bounded to its managed folder, stages and verifies files, and keeps the physical-file guard.

Verify the five pages at 920×620, 1280×820 and 1600×900. Keep synthetic previews separate from real account and device checks. Do not expose promised future integrations as disabled controls.
