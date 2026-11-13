"""User-editable application themes stored in the standard config directory."""

import json
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, Property, QSettings, Signal, Slot, QUrl
from PySide6.QtGui import QColor, QDesktopServices


DEFAULT_COLORS = {
    "background": "#0F0F0F", "surface": "#212121", "hover": "#303030",
    "foreground": "#FFFFFF", "secondary": "#AAAAAA", "border": "#3F3F3F",
    "accent": "#FF0033", "accentHover": "#FF335C", "onAccent": "#FFFFFF",
    "selected": "#292929", "muted": "#717171", "error": "#FF6B6B",
}

MIDNIGHT_VIOLET_COLORS = {
    "background": "#14131B", "surface": "#22212B", "hover": "#302D3E",
    "foreground": "#F6F4FB", "secondary": "#AAA6B8", "border": "#36323F",
    "accent": "#A78BFA", "accentHover": "#C4B5FD", "onAccent": "#201630",
    "selected": "#332B49", "muted": "#716B80", "error": "#FF8FA3",
}

ROLE_LABELS = {
    "background": "App Background", "surface": "Raised Surfaces", "hover": "Hover State",
    "foreground": "Primary Text", "secondary": "Secondary Text", "border": "Borders",
    "accent": "Accent", "accentHover": "Accent Hover", "onAccent": "Text on Accent",
    "selected": "Selected State", "muted": "Disabled Controls", "error": "Error Text",
}


def _palette(background, surface, hover, foreground, secondary, border,
             accent, accent_hover, on_accent, selected, muted, error):
    return dict(zip(DEFAULT_COLORS, (background, surface, hover, foreground, secondary,
                                    border, accent, accent_hover, on_accent, selected, muted, error)))


CLASSIC_LIGHT_COLORS = _palette("#FFFFFF", "#F9F9F9", "#F2F2F2", "#0F0F0F", "#606060", "#E5E5E5",
                                "#FF0033", "#D9002B", "#FFFFFF", "#F2F2F2", "#909090", "#C5221F")

PRESETS = [
    {"id": "classic-dark", "name": "Classic", "light": False,
     "colors": DEFAULT_COLORS},
    {"id": "classic-light", "name": "Classic Light", "light": True,
     "colors": CLASSIC_LIGHT_COLORS},
    {"id": "youtube-music-purple", "name": "Midnight Violet", "light": False,
     "colors": MIDNIGHT_VIOLET_COLORS},
    # Spotify-inspired: near-black with neutral greys and a bright green accent carrying black text.
    {"id": "mint", "name": "Mint", "light": False,
     "colors": _palette("#121212", "#1F1F1F", "#2A2A2A", "#FFFFFF", "#B3B3B3", "#333333", "#1ED760", "#3BE477", "#000000", "#2A2A2A", "#727272", "#F3727F")},
    # White with a deeper green, dark enough to read as text on white and on its surfaces.
    {"id": "mint-light", "name": "Mint Light", "light": True,
     "colors": _palette("#FFFFFF", "#F3F7F4", "#E6EFE8", "#0B1F12", "#52625A", "#D5E2D9", "#127A37", "#0E6A2F", "#FFFFFF", "#E1F2E6", "#8E9A93", "#C5221F")},
    {"id": "catppuccin-mocha", "name": "Catppuccin Mocha", "light": False,
     "colors": _palette("#1e1e2e", "#313244", "#45475a", "#cdd6f4", "#a6adc8", "#585b70", "#cba6f7", "#d7bafa", "#1e1e2e", "#45405a", "#7f849c", "#F38BA8")},
    {"id": "dracula", "name": "Dracula", "light": False,
     "colors": _palette("#282a36", "#343746", "#44475a", "#f8f8f2", "#bdc0cc", "#6272a4", "#bd93f9", "#d2b4ff", "#282a36", "#44475a", "#858899", "#FF8080")},
    {"id": "nord", "name": "Nord", "light": False,
     "colors": _palette("#2e3440", "#3b4252", "#434c5e", "#eceff4", "#d8dee9", "#4c566a", "#88c0d0", "#8fcedd", "#2e3440", "#434c5e", "#7b879b", "#F0A3AA")},
    {"id": "gruvbox-dark", "name": "Gruvbox Dark", "light": False,
     "colors": _palette("#282828", "#3c3836", "#504945", "#ebdbb2", "#d5c4a1", "#665c54", "#fabd2f", "#fdd663", "#282828", "#504945", "#928374", "#FC8B79")},
    {"id": "solarized-dark", "name": "Solarized Dark", "light": False,
     "colors": _palette("#002b36", "#073642", "#164b57", "#fdf6e3", "#93a1a1", "#586e75", "#268bd2", "#54a5df", "#fdf6e3", "#164b57", "#657b83", "#FF6E64")},
    {"id": "tokyo-night", "name": "Tokyo Night", "light": False,
     "colors": _palette("#1a1b26", "#24283b", "#343a52", "#c0caf5", "#a9b1d6", "#414868", "#7aa2f7", "#9ab8ff", "#1a1b26", "#343a52", "#565f89", "#F7768E")},
    {"id": "rose-pine", "name": "Rosé Pine", "light": False,
     "colors": _palette("#191724", "#26233a", "#393552", "#e0def4", "#908caa", "#524f67", "#c4a7e7", "#d3b8ef", "#191724", "#393552", "#6e6a86", "#EB6F92")},
    {"id": "solarized-light", "name": "Solarized Light", "light": True,
     "colors": _palette("#fdf6e3", "#eee8d5", "#e5dec9", "#073642", "#586e75", "#c8c0ad", "#268bd2", "#1576bd", "#ffffff", "#dce6e6", "#93a1a1", "#B02624")},
    {"id": "catppuccin-latte", "name": "Catppuccin Latte", "light": True,
     "colors": _palette("#eff1f5", "#e6e9ef", "#dce0e8", "#4c4f69", "#6c6f85", "#bcc0cc", "#8839ef", "#7628d8", "#ffffff", "#dce0e8", "#9ca0b0", "#B50D31")},
]
for _preset in PRESETS:
    _preset["colors"] = {role: color.upper() for role, color in _preset["colors"].items()}

DEFAULT_THEME_ID = "classic-dark"
THEME_FORMAT_VERSION = 1


class ThemeState(QObject):
    paletteChanged = Signal()
    messageChanged = Signal()

    def __init__(self, config_path, parent=None):
        super().__init__(parent)
        self._settings = QSettings(str(config_path), QSettings.Format.IniFormat)
        self._message = ""
        self._import_name = ""
        self._import_conflict = ""
        self._import_colors = None
        self._custom_themes = self._read_custom_themes()

        # Older installs stored the selected colors under colors/<role>. Read them
        # once: a changed legacy palette becomes an editable custom theme.
        legacy = {role: self._normalize(self._settings.value(f"colors/{role}", default)) or default
                  for role, default in DEFAULT_COLORS.items()}
        stored_id = str(self._settings.value("theme/active", ""))
        if not self._theme_by_id(stored_id) and legacy != DEFAULT_COLORS:
            theme_id = self._new_id()
            self._custom_themes.append({"id": theme_id, "name": "My Custom Theme", "colors": legacy})
            stored_id = theme_id
            self._save_custom_themes()
        self._settings.remove("colors")
        self._active_id = stored_id if self._theme_by_id(stored_id) else DEFAULT_THEME_ID
        self._apply_theme(self._theme_by_id(self._active_id))

    @staticmethod
    def _normalize(value):
        color = QColor(str(value))
        return color.name(QColor.NameFormat.HexRgb).upper() if color.isValid() else ""

    @staticmethod
    def _new_id():
        return "custom-" + uuid.uuid4().hex

    def _read_custom_themes(self):
        raw = self._settings.value("theme/custom", "[]")
        try:
            entries = json.loads(str(raw))
        except (TypeError, ValueError):
            return []
        if not isinstance(entries, list):
            return []
        result = []
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                continue
            name = entry["name"].strip()[:60]
            colors = self._validate_colors(entry.get("colors"))
            theme_id = str(entry.get("id", ""))
            if name and colors and theme_id.startswith("custom-") and theme_id not in seen:
                result.append({"id": theme_id, "name": name, "colors": colors})
                seen.add(theme_id)
        return result

    @staticmethod
    def _validate_colors(colors):
        """Normalize a saved or imported palette; roles it predates come from the matching Classic theme."""
        if not isinstance(colors, dict):
            return None
        normalized = {role: ThemeState._normalize(value) for role, value in colors.items() if role in DEFAULT_COLORS}
        if not normalized or not all(normalized.values()):
            return None
        light = "background" in normalized and ThemeState._is_light(normalized)
        defaults = CLASSIC_LIGHT_COLORS if light else DEFAULT_COLORS
        return {role: normalized.get(role, defaults[role]) for role in DEFAULT_COLORS}

    @staticmethod
    def _is_light(colors):
        return QColor(colors["background"]).lightnessF() >= 0.5

    @staticmethod
    def _blend(background, accent, amount=0.18):
        base, tint = QColor(background), QColor(accent)
        return QColor(*(
            round(base_channel * (1 - amount) + tint_channel * amount)
            for base_channel, tint_channel in zip(
                (base.red(), base.green(), base.blue()),
                (tint.red(), tint.green(), tint.blue()),
            )
        )).name(QColor.NameFormat.HexRgb).upper()

    @staticmethod
    def _contrast(first, second):
        def luminance(value):
            color = QColor(value)
            channels = (color.redF(), color.greenF(), color.blueF())
            linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                      for channel in channels]
            return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

        light, dark = sorted((luminance(first), luminance(second)), reverse=True)
        return (light + 0.05) / (dark + 0.05)

    def _all_themes(self):
        return PRESETS + self._custom_themes

    def _theme_by_id(self, theme_id):
        return next((theme for theme in self._all_themes() if theme["id"] == theme_id), None)

    def _apply_theme(self, theme):
        theme = theme or PRESETS[0]
        self._active_id = theme["id"]
        self._colors = dict(theme["colors"])
        self._settings.setValue("theme/active", self._active_id)
        self._settings.sync()

    def _save_custom_themes(self):
        self._settings.setValue("theme/custom", json.dumps(self._custom_themes, separators=(",", ":")))
        self._settings.sync()

    @Property(str, notify=paletteChanged)
    def background(self): return self._colors["background"]
    @Property(str, notify=paletteChanged)
    def surface(self): return self._colors["surface"]
    @Property(str, notify=paletteChanged)
    def hover(self): return self._colors["hover"]
    @Property(str, notify=paletteChanged)
    def foreground(self): return self._colors["foreground"]
    @Property(str, notify=paletteChanged)
    def secondary(self): return self._colors["secondary"]
    @Property(str, notify=paletteChanged)
    def border(self): return self._colors["border"]
    @Property(str, notify=paletteChanged)
    def accent(self): return self._colors["accent"]
    @Property(str, notify=paletteChanged)
    def accentHover(self): return self._colors["accentHover"]
    @Property(str, notify=paletteChanged)
    def onAccent(self): return self._colors["onAccent"]
    @Property(str, notify=paletteChanged)
    def selected(self): return self._colors["selected"]
    @Property(str, notify=paletteChanged)
    def muted(self): return self._colors["muted"]
    @Property(str, notify=paletteChanged)
    def error(self): return self._colors["error"]

    @Property(str, notify=paletteChanged)
    def progressTrack(self):
        for percent in range(35, 101):
            color = self._blend(self.surface, self.foreground, percent / 100)
            if self._contrast(self.surface, color) >= 3:
                return color
        # Custom themes can give surface and foreground the same luminance.
        return max(("#000000", "#FFFFFF"), key=lambda color: self._contrast(self.surface, color))

    @Property("QVariantList", notify=paletteChanged)
    def themes(self):
        result = []
        for theme in self._all_themes():
            colors = theme["colors"]
            result.append({"id": theme["id"], "name": theme["name"], "builtin": theme in PRESETS,
                           "light": theme.get("light", self._is_light(colors)), "active": theme["id"] == self._active_id,
                           "colors": colors, "swatches": [colors[key] for key in ("background", "surface", "accent", "foreground")]})
        return result

    @Property("QVariantList", notify=paletteChanged)
    def darkThemes(self):
        return [theme for theme in self.themes if not theme["light"]]

    @Property("QVariantList", notify=paletteChanged)
    def lightThemes(self):
        return [theme for theme in self.themes if theme["light"]]

    @Property("QVariantList", notify=paletteChanged)
    def palette(self):
        return [{"key": key, "label": ROLE_LABELS[key], "value": value}
                for key, value in self._colors.items()]

    @Property(str, notify=paletteChanged)
    def activeThemeId(self):
        return self._active_id

    @Property(str, notify=paletteChanged)
    def activeThemeName(self):
        theme = self._theme_by_id(self._active_id)
        return theme["name"] if theme else PRESETS[0]["name"]

    @Property(bool, notify=paletteChanged)
    def activeThemeIsCustom(self):
        return self._active_id.startswith("custom-")

    @Property(str, notify=messageChanged)
    def message(self):
        return self._message

    @Slot(str)
    def selectTheme(self, theme_id):
        theme = self._theme_by_id(theme_id)
        if not theme:
            return
        self._apply_theme(theme)
        self._message = ""
        self.paletteChanged.emit()
        self.messageChanged.emit()

    @Slot(str, result=bool)
    def createCustomTheme(self, name):
        name = name.strip()[:60]
        if not name:
            return self._fail("Enter a name for the custom theme.")
        if self._name_exists(name):
            return self._fail("A theme with that name already exists.")
        theme = {"id": self._new_id(), "name": name, "colors": dict(self._colors)}
        self._custom_themes.append(theme)
        self._save_custom_themes()
        self._apply_theme(theme)
        self._success()
        self.paletteChanged.emit()
        return True

    @Slot(str, str, result=bool)
    def renameCustomTheme(self, theme_id, name):
        theme = self._custom_by_id(theme_id)
        name = name.strip()[:60]
        if not theme:
            return self._fail("Built-in themes cannot be renamed.")
        if not name:
            return self._fail("Enter a theme name.")
        if self._name_exists(name, except_id=theme_id):
            return self._fail("A theme with that name already exists.")
        theme["name"] = name
        self._save_custom_themes()
        self.paletteChanged.emit()
        self._success()
        return True

    @Slot(str, result=bool)
    def deleteCustomTheme(self, theme_id):
        theme = self._custom_by_id(theme_id)
        if not theme:
            return self._fail("Built-in themes cannot be deleted.")
        self._custom_themes.remove(theme)
        self._save_custom_themes()
        if self._active_id == theme_id:
            self._apply_theme(PRESETS[0])
        self.paletteChanged.emit()
        self._success()
        return True

    @Slot(str, str)
    def setColor(self, role, value):
        if role not in DEFAULT_COLORS:
            return
        color = self._normalize(value)
        if not color:
            self._fail(f"Enter a valid color for {role}, such as #A78BFA.")
            return
        theme = self._custom_by_id(self._active_id)
        if not theme:
            self._fail("Create a custom theme before editing colors.")
            return
        if color == self._colors[role]:
            self._success()
            return
        self._colors[role] = color
        theme["colors"] = dict(self._colors)
        self._save_custom_themes()
        self._success()
        self.paletteChanged.emit()

    @Slot()
    def reset(self):
        self.selectTheme(DEFAULT_THEME_ID)

    @Slot()
    def openConfigFile(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self._settings.fileName()).parent)))

    @Slot(str, result=bool)
    def exportTheme(self, file_path):
        theme = self._custom_by_id(self._active_id)
        if not theme:
            return self._fail("Select a custom theme to export.")
        path = self._local_path(file_path)
        if not path:
            return self._fail("Choose a file to export the theme.")
        try:
            path.write_text(json.dumps({"version": THEME_FORMAT_VERSION, "name": theme["name"],
                                        "appearance": "light" if self._is_light(theme["colors"]) else "dark",
                                        "colors": theme["colors"]}, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            return self._fail(f"Could not export theme: {exc}")
        self._success("Theme exported.")
        return True

    @Slot(str, result="QVariantMap")
    def inspectImport(self, file_path):
        path = self._local_path(file_path)
        self._import_name = ""
        self._import_conflict = ""
        self._import_colors = None
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path else None
        except (OSError, ValueError, UnicodeError):
            data = None
        if not isinstance(data, dict) or data.get("version") != THEME_FORMAT_VERSION:
            self._fail("Invalid theme format.")
            return {"ok": False}
        colors = self._validate_colors(data.get("colors"))
        name = data.get("name")
        if not colors or not isinstance(name, str) or not name.strip():
            self._fail("Invalid theme format.")
            return {"ok": False}
        self._import_colors = colors
        self._import_name = name.strip()[:60]
        self._import_conflict = self._existing_name(self._import_name)
        self._message = ""
        self.messageChanged.emit()
        return {"ok": True, "name": self._import_name, "conflict": self._import_conflict,
                "builtIn": bool(self._import_conflict and not self._custom_by_id(self._import_conflict))}

    @Slot(str, bool, result=bool)
    def completeImport(self, name, replace_existing):
        if not self._import_colors:
            return self._fail("Choose a theme file to import.")
        name = name.strip()[:60]
        if not name:
            return self._fail("Enter a name for the imported theme.")
        conflict = self._existing_name(name)
        if conflict and (not self._custom_by_id(conflict) or not replace_existing):
            return self._fail("Choose a new name, or confirm replacing the custom theme.")
        if self._import_conflict and not self._custom_by_id(self._import_conflict) and name.casefold() == self._import_name.casefold():
            return self._fail("Built-in themes cannot be replaced. Choose a different name.")
        if conflict:
            theme = self._custom_by_id(conflict)
            theme["name"], theme["colors"] = name, dict(self._import_colors)
        else:
            theme = {"id": self._new_id(), "name": name, "colors": dict(self._import_colors)}
            self._custom_themes.append(theme)
        self._save_custom_themes()
        self._apply_theme(theme)
        self.paletteChanged.emit()
        self._success("Theme imported.")
        return True

    def _custom_by_id(self, theme_id):
        return next((theme for theme in self._custom_themes if theme["id"] == theme_id), None)

    def _name_exists(self, name, except_id=""):
        return bool(self._existing_name(name, except_id))

    def _existing_name(self, name, except_id=""):
        folded = name.casefold()
        return next((theme["id"] for theme in self._all_themes()
                     if theme["id"] != except_id and theme["name"].casefold() == folded), "")

    @staticmethod
    def _local_path(value):
        url = QUrl(str(value))
        return Path(url.toLocalFile()) if url.isLocalFile() else Path(str(value)) if str(value) else None

    def _fail(self, message):
        self._message = message
        self.messageChanged.emit()
        return False

    def _success(self, message=""):
        self._message = message
        self.messageChanged.emit()
