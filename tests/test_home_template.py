from __future__ import annotations

import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from tests._support import make_blueprint_app

APP_JS = (
    Path(__file__).parent.parent
    / "smart_display"
    / "web"
    / "static"
    / "js"
    / "app.js"
)

# app.js resolves every node up front and writes to most of them without a null
# guard, so an id it wants but the template lacks throws on the first poll and
# silently kills the render loop. Derive the list instead of copying it — a
# hand-kept list still passes when someone adds a node.
_GET_BY_ID = re.compile(r'getElementById\("([^"]+)"\)')


class _ElementFinder(HTMLParser):
    """Collects tag name and attributes for the element carrying ``target_id``."""

    def __init__(self, target_id: str) -> None:
        super().__init__()
        self.target_id = target_id
        self.tag: str | None = None
        self.attrs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        mapping = {key: (value or "") for key, value in attrs}
        if mapping.get("id") == self.target_id:
            self.tag = tag
            self.attrs = mapping


class HomeTemplateContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        app = make_blueprint_app(Path(self._tmp.name))
        self.html = app.test_client().get("/").get_data(as_text=True)

    def _element(self, element_id: str) -> _ElementFinder:
        finder = _ElementFinder(element_id)
        finder.feed(self.html)
        return finder

    def test_every_id_app_js_looks_up_exists_in_the_template(self) -> None:
        wanted = sorted(set(_GET_BY_ID.findall(APP_JS.read_text(encoding="utf-8"))))
        self.assertGreater(len(wanted), 20, "id extraction found suspiciously few ids")
        missing = [
            element_id for element_id in wanted if self._element(element_id).tag is None
        ]
        self.assertEqual(missing, [], f"app.js reads ids the template does not render: {missing}")

    def test_spotify_tile_is_a_labelled_button(self) -> None:
        # A real <button> is what gives the tile focus, Enter/Space and
        # :focus-visible for free — see the click handler in bindEvents.
        tile = self._element("spotify-card")
        self.assertEqual(tile.tag, "button")
        self.assertIn("spotify-tile", tile.attrs.get("class", "").split())
        self.assertTrue(tile.attrs.get("aria-label", "").strip())

    def test_home_tile_carries_no_controls(self) -> None:
        # Screen 2 owns every Spotify control; the home tile is display-only.
        # Guards the decision, not the markup: any interactive descendant fails.
        tile_markup = self.html.split('id="spotify-card"', 1)[1].split("</button>", 1)[0]
        for control in ("<button", "<input", "<select", "<textarea"):
            with self.subTest(control=control):
                self.assertNotIn(control, tile_markup)


if __name__ == "__main__":
    unittest.main()
