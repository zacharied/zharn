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
