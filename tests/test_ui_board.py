"""The Stories board with nothing in it: the message stands alone, and the tree comes back with the first story."""
import pytest
from PySide6.QtTest import QTest

from ui import start


@pytest.fixture(scope="module")
def ui():
    h = start("ui-board")
    yield h
    h.shutdown()


def test_empty_board_shows_the_message_and_no_phase_sections(ui):
    """The phase sections are not data-driven, so an empty board used to draw five headers
    under an absolutely-positioned message. Nothing to group, nothing to show."""
    assert ui.store.stories.model.count() == 0
    assert ui.visible(ui.find("emptyStories"))
    assert [g.name for g in ui.find_all("treeGroup_.*") if ui.visible(g)] == []


def test_the_first_story_replaces_the_message_with_the_tree(ui):
    key = ui.store.stories.create("First", "")
    QTest.qWait(120)
    assert not ui.visible(ui.find("emptyStories"))
    assert ui.visible(ui.find("treeGroup_todo")) and ui.visible(ui.find(f"card_{key}"))
    assert ui.visible(ui.find("treeGroup_planning"))  # an empty phase still shows once the board has stories
