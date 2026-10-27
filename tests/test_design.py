import json
import re

import pytest

from app.config import BASE_DIR

STATIC = BASE_DIR / "static"


def blocks():
    css = (STATIC / "css/tokens.css").read_text(encoding="utf-8")
    light = re.search(r"^:root \{(.*?)^\}", css, re.S | re.M).group(1)
    dark_attr = re.search(r':root\[data-theme="dark"\] \{(.*?)^\}', css, re.S | re.M).group(1)
    dark_media = re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)^  \}', css, re.S | re.M).group(1)
    return light, dark_attr, dark_media


def tokens(block):
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", block))


def luminance(color):
    def channel(value):
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast(first, second):
    a, b = sorted((luminance(first), luminance(second)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def themes():
    light, dark_attr, dark_media = blocks()
    base = tokens(light)
    return {"light": base, "dark": {**base, **tokens(dark_attr)}}


TEXT_PAIRS = [
    ("text", "bg"), ("text", "surface"), ("text", "surface-2"),
    ("muted", "bg"), ("muted", "surface"), ("muted", "surface-2"),
    ("primary-text", "primary"), ("link", "bg"), ("link", "surface"), ("link", "primary-soft"),
    ("ok", "ok-soft"), ("ok", "surface"), ("ok", "bg"), ("bad", "bad-soft"), ("bad", "surface"), ("bad", "bg"),
    ("warn", "warn-soft"), ("warn", "surface"),
    ("err-form", "err-form-soft"), ("err-meaning", "err-meaning-soft"),
    ("err-usage", "err-usage-soft"), ("err-collocation", "err-collocation-soft"),
]

NON_TEXT_PAIRS = [("control-border", "surface"), ("control-border", "bg"), ("focus", "bg"), ("focus", "surface"), ("primary", "surface")]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("foreground, background", TEXT_PAIRS)
def test_text_contrast_is_at_least_aa(theme, foreground, background):
    colors = themes()[theme]
    assert contrast(colors[foreground], colors[background]) >= 4.5, (theme, foreground, background)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("foreground, background", NON_TEXT_PAIRS)
def test_interface_boundaries_have_3_to_1_contrast(theme, foreground, background):
    colors = themes()[theme]
    assert contrast(colors[foreground], colors[background]) >= 3.0, (theme, foreground, background)


def test_system_dark_theme_matches_the_manual_one():
    _, dark_attr, dark_media = blocks()
    assert tokens(dark_attr) == tokens(dark_media)


def test_both_themes_define_every_color():
    colors = themes()
    light_only = set(tokens(blocks()[0]))
    assert light_only <= set(colors["dark"])
    for name in ("bg", "surface", "text", "muted", "primary", "bad", "ok", "control-border", "link"):
        assert name in light_only


def test_css_has_no_external_resources_and_uses_only_local_fonts():
    for path in (STATIC / "css").glob("*.css"):
        css = path.read_text(encoding="utf-8")
        assert not re.search(r"url\(\s*[\"']?(https?:)?//", css), path
        assert "@import" not in css, path


def test_fonts_are_local_woff2_with_license():
    css = (STATIC / "css/fonts.css").read_text(encoding="utf-8")
    files = re.findall(r'url\("(/fonts/[^"]+)"\)', css)
    assert files
    for name in files:
        data = (STATIC / name.lstrip("/")).read_bytes()
        assert data[:4] == b"wOF2", name
    assert "unicode-range: U+0301, U+0400-045F" in css
    assert "SIL OPEN FONT LICENSE" in (STATIC / "fonts/OFL.txt").read_text(encoding="utf-8").upper()


def test_icon_library_license_is_shipped():
    assert "ISC License" in (STATIC / "icons/LICENSE-lucide.txt").read_text(encoding="utf-8")


def test_manifest_uses_theme_colors_and_existing_icons():
    manifest = json.loads((STATIC / "manifest.json").read_text(encoding="utf-8"))
    light = themes()["light"]
    assert manifest["background_color"].lower() == light["bg"].lower()
    assert manifest["theme_color"].lower() == light["primary"].lower()
    for icon in manifest["icons"]:
        assert (STATIC / icon["src"].lstrip("/")).is_file(), icon["src"]


def test_pages_load_the_design_system_and_follow_the_system_theme_color():
    for page in ("index.html", "teacher.html"):
        html = (STATIC / page).read_text(encoding="utf-8")
        for sheet in ("fonts.css", "tokens.css", "app.css"):
            assert f"/css/{sheet}" in html, (page, sheet)
        assert "/js/theme-init.js" in html
        assert html.count('name="theme-color"') == 2


def test_motion_respects_reduced_motion_preference():
    css = (STATIC / "css/app.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in css
    assert re.search(r"prefers-reduced-motion: reduce\)\s*\{\s*\*,[^}]*animation: none !important", css, re.S)


def test_headings_focused_by_script_have_no_focus_ring():
    css = (STATIC / "css/app.css").read_text(encoding="utf-8")
    assert re.search(r'\[tabindex="-1"\]:focus-visible\s*\{\s*outline: none;', css)
    assert css.index(':focus-visible {') < css.index('[tabindex="-1"]:focus-visible')
