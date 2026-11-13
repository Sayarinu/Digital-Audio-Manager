import json

import pytest

from PySide6.QtCore import QCoreApplication, QSettings

from dam.theme import CLASSIC_LIGHT_COLORS, DEFAULT_COLORS, DEFAULT_THEME_ID, PRESETS, ThemeState


def _app():
    return QCoreApplication.instance() or QCoreApplication([])


def test_builtin_themes_and_role_palette(tmp_path):
    _app()
    theme = ThemeState(tmp_path / "theme.ini")
    assert len([entry for entry in theme.themes if entry["builtin"]]) == 14
    assert sum(entry["light"] for entry in theme.themes) == 4
    assert theme.activeThemeId == DEFAULT_THEME_ID
    assert theme.activeThemeName == "Classic"
    assert {entry["name"] for entry in theme.themes if entry["id"] in ("classic-dark", "classic-light")} == {"Classic", "Classic Light"}
    assert {entry["key"] for entry in theme.palette} == set(DEFAULT_COLORS)


def test_select_custom_palette_is_reactive_and_persists(tmp_path):
    _app()
    path = tmp_path / "theme.ini"
    theme = ThemeState(path)
    changed = []
    theme.paletteChanged.connect(lambda: changed.append(theme.accent))
    assert theme.createCustomTheme("Night Mix")
    theme.setColor("accent", "#12abef")
    assert theme.accent == "#12ABEF"
    assert changed[-1] == "#12ABEF"

    restored = ThemeState(path)
    assert restored.activeThemeName == "Night Mix"
    assert restored.accent == "#12ABEF"
    assert restored.activeThemeIsCustom


@pytest.mark.parametrize("preset", PRESETS, ids=lambda preset: preset["id"])
def test_error_color_is_readable_on_every_builtin_theme(preset):
    colors = preset["colors"]
    assert ThemeState._contrast(colors["error"], colors["background"]) >= 4.5
    assert ThemeState._contrast(colors["error"], colors["surface"]) >= 4.5


@pytest.mark.parametrize("theme_id", ["mint", "mint-light"])
def test_mint_themes_keep_their_green_accent_readable(theme_id):
    colors = next(preset for preset in PRESETS if preset["id"] == theme_id)["colors"]
    for role in ("background", "surface"):
        assert ThemeState._contrast(colors["accent"], colors[role]) >= 4.5
    assert ThemeState._contrast(colors["onAccent"], colors["accent"]) >= 4.5


def test_saved_theme_missing_a_newer_role_is_kept_and_filled(tmp_path):
    _app()
    path = tmp_path / "theme.ini"
    dark = {role: color for role, color in DEFAULT_COLORS.items() if role != "error"}
    light = dict(dark, background="#FAFAFA")
    saved = [{"id": "custom-dark", "name": "Old Dark", "colors": dict(dark, accent="#123456")},
             {"id": "custom-light", "name": "Old Light", "colors": light}]
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    settings.setValue("theme/custom", json.dumps(saved))
    settings.setValue("theme/active", "custom-dark")
    settings.sync()
    theme = ThemeState(path)
    assert theme.activeThemeName == "Old Dark"
    assert theme.accent == "#123456"
    assert theme.error == DEFAULT_COLORS["error"]
    theme.selectTheme("custom-light")
    assert theme.error == CLASSIC_LIGHT_COLORS["error"]


def test_theme_selection_no_longer_writes_legacy_color_keys(tmp_path):
    _app()
    path = tmp_path / "theme.ini"
    theme = ThemeState(path)
    theme.selectTheme("dracula")
    assert theme.createCustomTheme("Mine")
    theme.setColor("accent", "#abcdef")
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    assert "colors" not in settings.childGroups()
    assert ThemeState(path).accent == "#ABCDEF"


def test_complete_import_without_inspection_fails_cleanly(tmp_path):
    _app()
    theme = ThemeState(tmp_path / "theme.ini")
    before = theme.activeThemeId
    assert not theme.completeImport("Anything", False)
    assert theme.message == "Choose a theme file to import."
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    assert not theme.inspectImport(str(invalid))["ok"]
    assert not theme.completeImport("Anything", False)
    assert theme.activeThemeId == before


def test_custom_theme_crud_and_active_delete_falls_back(tmp_path):
    _app()
    theme = ThemeState(tmp_path / "theme.ini")
    assert theme.createCustomTheme("My colors")
    theme_id = theme.activeThemeId
    assert theme.renameCustomTheme(theme_id, "Evening")
    assert theme.activeThemeName == "Evening"
    assert not theme.renameCustomTheme(theme_id, "Dracula")
    assert theme.deleteCustomTheme(theme_id)
    assert theme.activeThemeId == DEFAULT_THEME_ID
    assert not theme.deleteCustomTheme(DEFAULT_THEME_ID)


def test_legacy_non_default_colors_migrate_to_custom_theme(tmp_path):
    _app()
    path = tmp_path / "theme.ini"
    path.write_text("[colors]\naccent=#ff0000\n", encoding="utf-8")
    theme = ThemeState(path)
    assert theme.activeThemeIsCustom
    assert theme.activeThemeName == "My Custom Theme"
    assert theme.accent == "#FF0000"
    assert "colors" not in QSettings(str(path), QSettings.Format.IniFormat).childGroups()
    restored = ThemeState(path)
    assert restored.activeThemeName == "My Custom Theme"
    assert restored.accent == "#FF0000"


def test_import_export_and_conflict_rules(tmp_path):
    _app()
    path = tmp_path / "theme.ini"
    theme = ThemeState(path)
    assert theme.createCustomTheme("Export me")
    theme.setColor("accent", "#abcdef")
    exported = tmp_path / "shared-theme.json"
    assert theme.exportTheme(str(exported))
    document = json.loads(exported.read_text(encoding="utf-8"))
    assert document["version"] == 1
    assert document["appearance"] == "dark"
    assert set(document["colors"]) == set(DEFAULT_COLORS)

    imported = ThemeState(tmp_path / "other.ini")
    result = imported.inspectImport(str(exported))
    assert result["ok"] and not result["conflict"]
    assert imported.completeImport(result["name"], False)
    assert imported.accent == "#ABCDEF"

    conflict = imported.inspectImport(str(exported))
    assert conflict["conflict"] and not conflict["builtIn"]
    assert not imported.completeImport(result["name"], False)
    assert imported.completeImport(result["name"], True)

    built_in = dict(document, name="Dracula")
    built_in_path = tmp_path / "built-in.json"
    built_in_path.write_text(json.dumps(built_in), encoding="utf-8")
    result = imported.inspectImport(str(built_in_path))
    assert result["builtIn"]
    assert not imported.completeImport("Dracula", True)
    assert imported.completeImport("Dracula Personal", False)

    light_document = dict(document, name="Imported Light", colors=dict(document["colors"], background="#FFFFFF"))
    light_path = tmp_path / "light-theme.json"
    light_path.write_text(json.dumps(light_document), encoding="utf-8")
    result = imported.inspectImport(str(light_path))
    assert result["ok"] and imported.completeImport(result["name"], False)
    assert next(theme for theme in imported.themes if theme["id"] == imported.activeThemeId)["light"]


def test_invalid_import_does_not_change_active_theme(tmp_path):
    _app()
    theme = ThemeState(tmp_path / "theme.ini")
    before = theme.activeThemeId, theme.accent
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"version": 99, "name": "Broken", "colors": {}}', encoding="utf-8")
    assert not theme.inspectImport(str(invalid))["ok"]
    assert theme.message == "Invalid theme format."
    assert (theme.activeThemeId, theme.accent) == before


@pytest.mark.parametrize("theme_id,expected", [
    ("classic-dark", "#6F6F6F"), ("classic-light", "#909090"),
    ("youtube-music-purple", "#6C6B74"), ("catppuccin-mocha", "#777C93"),
    ("dracula", "#808289"), ("nord", "#898E99"),
    ("gruvbox-dark", "#8B816E"), ("solarized-dark", "#647F7F"),
    ("tokyo-night", "#6A718F"), ("rose-pine", "#706E84"),
    ("solarized-light", "#718886"), ("catppuccin-latte", "#808397"),
])
def test_progress_track_has_contrast_without_changing_palette(theme_id, expected, tmp_path):
    _app()
    theme = ThemeState(tmp_path / "theme.ini")
    theme.selectTheme(theme_id)
    track = theme.progressTrack
    assert ThemeState._contrast(track, theme.surface) >= 3
    assert track == expected
    assert {role["key"] for role in theme.palette} == set(DEFAULT_COLORS)


@pytest.mark.parametrize("surface,expected", [("#FFFFFF", "#000000"), ("#000000", "#FFFFFF"), ("#777777", "#000000")])
def test_progress_track_handles_low_contrast_custom_themes_and_import(surface, expected, tmp_path):
    _app()
    theme = ThemeState(tmp_path / "theme.ini")
    assert theme.createCustomTheme("Low contrast")
    updates = []
    theme.paletteChanged.connect(lambda: updates.append(theme.progressTrack))
    theme.setColor("surface", surface)
    theme.setColor("foreground", surface)
    assert updates[-1] == expected
    assert ThemeState._contrast(theme.progressTrack, surface) >= 3
    assert ThemeState._contrast("#FFFFFF", "#000000") == 21
    exported = tmp_path / "custom.json"
    assert theme.exportTheme(str(exported))
    assert set(json.loads(exported.read_text())["colors"]) == set(DEFAULT_COLORS)
    imported = ThemeState(tmp_path / "imported.ini")
    assert imported.inspectImport(str(exported))["ok"]
    assert imported.completeImport("Imported", False)
    assert imported.progressTrack == expected
