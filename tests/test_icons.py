"""Icon image provider: qml/icons/<name>.svg rendered in a color at a size (image://icon/<name>/<rrggbb>)."""
from PySide6.QtCore import QSize

from harness.icons import ICON_DIR, IconProvider, icon_names


def _request(provider, id_, px):
    return provider.requestImage(id_, QSize(), QSize(px, px))


def _close(a: str, b: str, tol=2) -> bool:  # anti-aliased edges round channels by ±1
    return all(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) <= tol for i in (1, 3, 5))


def test_every_icon_renders_with_the_requested_color_and_size():
    p = IconProvider()
    names = icon_names()
    assert "stories" in names and "cast" in names
    for name in names:
        img = _request(p, f"{name}/dfe1e5", 16)
        assert not img.isNull() and img.width() == 16 and img.height() == 16, name
        colored = {img.pixelColor(x, y).name() for x in range(16) for y in range(16) if img.pixelColor(x, y).alpha() > 150}
        assert colored and all(_close(c, "#dfe1e5") for c in colored), (name, colored)


def test_size_and_color_vary_per_request():
    p = IconProvider()
    big = _request(p, "stories/3574f0", 40)
    assert big.width() == 40
    opaque = [(x, y) for x in range(40) for y in range(40) if big.pixelColor(x, y).alpha() > 200]
    assert opaque and all(_close(big.pixelColor(x, y).name(), "#3574f0") for x, y in opaque)


def test_unknown_icon_is_a_visible_placeholder_not_a_crash():
    img = _request(IconProvider(), "no-such-icon/ffffff", 16)
    assert not img.isNull() and img.width() == 16
    assert any(img.pixelColor(x, y).alpha() > 0 for x in range(16) for y in range(16))


def test_icon_dir_is_the_checkout_icons_folder():
    assert ICON_DIR.name == "icons" and (ICON_DIR / "stories.svg").exists()


def test_the_app_icon_carries_every_taskbar_and_display_size():
    from harness.icons import APP_ICON_SIZES, app_icon
    icon = app_icon()
    assert not icon.isNull()
    for px in APP_ICON_SIZES:
        img = icon.pixmap(px, px).toImage()
        assert img.width() == px and img.height() == px, px
        assert any(img.pixelColor(x, y).alpha() > 200 for x in range(px) for y in range(px)), px


def test_the_brand_icon_stays_out_of_the_recolored_icon_set():
    # qml/icons/ is monochrome by contract (every SVG is repainted in a requested color);
    # a full-color mark in there would be silently flattened and break test_every_icon_renders.
    from harness.icons import BRAND_DIR
    assert BRAND_DIR.name == "brand" and (BRAND_DIR / "zharn.svg").exists()
    assert BRAND_DIR.parent == ICON_DIR.parent and BRAND_DIR != ICON_DIR
    assert "zharn" not in icon_names()
