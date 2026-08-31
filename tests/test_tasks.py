"""TaskStore unit tests against an in-file threads stub (no processes, no fake CLI)."""
import json

import pytest
from PySide6.QtCore import QObject, Signal

from harness.tasks import DEMO, STATUSES, TaskStore


class StubThread:
    def __init__(self, status):
        self.status = status

    def summary(self):
        return {"status": self.status}


class StubThreads(QObject):
    """The slice of ThreadStore that TaskStore touches: threads_for, spawn, threadsChanged."""
    threadsChanged = Signal()

    def __init__(self):
        super().__init__()
        self.by_key: dict[str, list[StubThread]] = {}
        self.spawned: list[dict] = []

    def threads_for(self, key):
        return self.by_key.get(key, [])

    def spawn(self, task_key, role_name, prompt, parent_id, title):
        tid = f"thread-{len(self.spawned) + 1}"
        self.spawned.append({"id": tid, "task_key": task_key, "role_name": role_name,
                             "prompt": prompt, "parent_id": parent_id, "title": title})
        return tid


@pytest.fixture
def threads():
    return StubThreads()


@pytest.fixture
def store(tmp_path, threads):
    return TaskStore(tmp_path, threads)


def read_json(tmp_path):
    return json.loads((tmp_path / "tasks.json").read_text())


# --- seeding & persistence -------------------------------------------------

def test_first_run_seeds_demo_tasks_with_sequential_keys(store):
    keys = [t["key"] for t in store.list()]
    assert keys == [f"ABC-{i}" for i in range(1, len(DEMO) + 1)]
    assert [t["title"] for t in store.list()] == [d["title"] for d in DEMO]


def test_first_run_persists_seeded_tasks_to_json(tmp_path, store):
    data = read_json(tmp_path)
    assert len(data["tasks"]) == len(DEMO)
    assert data["next"] == len(DEMO) + 1
    assert data["tasks"][0]["key"] == "ABC-1"


def test_second_store_over_same_dir_loads_without_reseeding(tmp_path, threads):
    first = TaskStore(tmp_path, threads)
    new_key = first.create("Persisted task")
    second = TaskStore(tmp_path, threads)
    assert [t["key"] for t in second.list()] == [t["key"] for t in first.list()]
    assert second.get(new_key)["title"] == "Persisted task"
    # `next` was restored, so the counter continues rather than restarting at 1
    assert second.create("Another") == f"ABC-{len(DEMO) + 2}"


def test_custom_prefix_is_used_for_keys(tmp_path, threads):
    s = TaskStore(tmp_path, threads, prefix="XYZ")
    assert [t["key"] for t in s.list()][0] == "XYZ-1"
    assert s.create("t") == f"XYZ-{len(DEMO) + 1}"


# --- create / get ----------------------------------------------------------

def test_create_assigns_next_key_and_todo_status(store):
    key = store.create("New thing", "some description")
    assert key == f"ABC-{len(DEMO) + 1}"
    row = store.get(key)
    assert row["title"] == "New thing"
    assert row["description"] == "some description"
    assert row["status"] == "todo"


def test_create_keys_are_sequential(store):
    a, b = store.create("a"), store.create("b")
    assert int(b.split("-")[1]) == int(a.split("-")[1]) + 1


def test_create_persists_to_json(tmp_path, store):
    key = store.create("Persist me")
    data = read_json(tmp_path)
    assert any(t["key"] == key and t["title"] == "Persist me" for t in data["tasks"])
    assert data["next"] == len(DEMO) + 2


def test_get_is_case_insensitive(store):
    assert store.get("abc-1")["key"] == "ABC-1"
    assert store.get("Abc-1") == store.get("ABC-1")


def test_get_unknown_key_returns_empty_dict(store):
    assert store.get("ABC-999") == {}
    assert store.get("") == {}


# --- list rows & thread counts --------------------------------------------

def test_list_rows_include_thread_counts_from_threads(store, threads):
    threads.by_key["ABC-1"] = [StubThread("working"), StubThread("starting"), StubThread("idle")]
    row = next(r for r in store.list() if r["key"] == "ABC-1")
    assert row["threadCount"] == 3
    assert row["workingCount"] == 2


def test_list_rows_without_threads_have_zero_counts(store):
    assert all(r["threadCount"] == 0 and r["workingCount"] == 0 for r in store.list())


def test_model_refreshes_when_threads_change(store, threads):
    emitted = []
    store.tasksChanged.connect(lambda: emitted.append(True))
    threads.by_key["ABC-2"] = [StubThread("working")]
    assert store.model.rows()[1]["threadCount"] == 0, "stale until threads notify"
    threads.threadsChanged.emit()
    assert emitted
    assert store.model.rows()[1]["threadCount"] == 1


# --- setStatus -------------------------------------------------------------

def test_set_status_valid_updates_and_persists(tmp_path, store):
    store.setStatus("ABC-3", "done")
    assert store.get("ABC-3")["status"] == "done"
    persisted = next(t for t in read_json(tmp_path)["tasks"] if t["key"] == "ABC-3")
    assert persisted["status"] == "done"


def test_set_status_invalid_status_is_ignored(tmp_path, store):
    before = (tmp_path / "tasks.json").read_text()
    store.setStatus("ABC-3", "bogus")
    assert store.get("ABC-3")["status"] == "todo"
    assert (tmp_path / "tasks.json").read_text() == before


def test_set_status_unknown_key_is_ignored(tmp_path, store):
    before = (tmp_path / "tasks.json").read_text()
    store.setStatus("ABC-999", "done")
    assert (tmp_path / "tasks.json").read_text() == before


def test_statuses_property_exposes_all_statuses(store):
    assert list(store.statuses) == STATUSES


# --- dispatch --------------------------------------------------------------

def test_dispatch_spawns_thread_and_returns_its_id(store, threads):
    tid = store.dispatch("ABC-3", "claude-fast", "do the thing")
    assert tid == "thread-1"
    call = threads.spawned[0]
    assert call["task_key"] == "ABC-3"
    assert call["role_name"] == "claude-fast"
    assert call["parent_id"] == ""


def test_dispatch_prompt_contains_task_header_description_contract_and_instructions(store, threads):
    store.dispatch("ABC-1", "claude-fast", "please refactor the loader")
    prompt = threads.spawned[0]["prompt"]
    task = store.get("ABC-1")
    assert prompt.startswith(f"# Task ABC-1: {task['title']}")
    assert task["description"] in prompt
    assert "## Report-back contract" in prompt
    assert prompt.rstrip().endswith("## Instructions\nplease refactor the loader")


def test_dispatch_title_is_first_prompt_line_truncated_to_60(store, threads):
    long_line = "x" * 80
    store.dispatch("ABC-1", "claude-fast", f"  {long_line}\nsecond line\n")
    assert threads.spawned[0]["title"] == long_line[:60]


def test_dispatch_title_falls_back_to_role_name_for_blank_prompt(store, threads):
    store.dispatch("ABC-1", "claude-fast", "   \n")
    assert threads.spawned[0]["title"] == "claude-fast"


def test_dispatch_passes_parent_id(store, threads):
    store.dispatch("ABC-1", "claude-fast", "child work", "parent-thread")
    assert threads.spawned[0]["parent_id"] == "parent-thread"


@pytest.mark.parametrize("key", ["ABC-3", "ABC-5"])  # todo, backlog
def test_dispatch_moves_todo_and_backlog_to_in_progress(tmp_path, store, key):
    assert store.get(key)["status"] in ("todo", "backlog")
    store.dispatch(key, "claude-fast", "go")
    assert store.get(key)["status"] == "in_progress"
    persisted = next(t for t in read_json(tmp_path)["tasks"] if t["key"] == key)
    assert persisted["status"] == "in_progress"


@pytest.mark.parametrize("key,status", [("ABC-1", "in_review"), ("ABC-2", "in_progress")])
def test_dispatch_leaves_other_statuses_untouched(store, key, status):
    assert store.get(key)["status"] == status
    store.dispatch(key, "claude-fast", "go")
    assert store.get(key)["status"] == status


def test_dispatch_leaves_done_untouched(store):
    store.setStatus("ABC-4", "done")
    store.dispatch("ABC-4", "claude-fast", "go")
    assert store.get("ABC-4")["status"] == "done"


def test_dispatch_unknown_task_raises_and_spawns_nothing(store, threads):
    with pytest.raises(ValueError):
        store.dispatch("ABC-999", "claude-fast", "go")
    assert threads.spawned == []


def test_dispatch_is_case_insensitive_and_uses_canonical_key(store, threads):
    store.dispatch("abc-3", "claude-fast", "go")
    assert threads.spawned[0]["prompt"].startswith("# Task ABC-3:")
    assert store.get("ABC-3")["status"] == "in_progress"


def test_threads_for_returns_thread_summaries(store, threads):
    threads.by_key["ABC-1"] = [StubThread("idle")]
    assert store.threadsFor("ABC-1") == [{"status": "idle"}]
