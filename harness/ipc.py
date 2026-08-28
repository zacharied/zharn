"""Local IPC so agents (child processes) can drive the harness: spawn sibling threads on their
task, wait on them, list presets. One JSON request per connection, newline-terminated."""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class IpcServer(QObject):
    def __init__(self, name: str, handler, parent=None):
        super().__init__(parent)
        self.handler = handler
        self.server = QLocalServer(self)
        QLocalServer.removeServer(name)
        if not self.server.listen(name):
            raise RuntimeError(f"IPC listen failed: {self.server.errorString()}")
        self.server.newConnection.connect(self._accept)
        self._bufs: dict[int, bytes] = {}

    @property
    def path(self) -> str:
        return self.server.fullServerName()

    def _accept(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            self._bufs[id(sock)] = b""
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(lambda s=sock: self._drop(s))

    def _drop(self, sock):
        self._bufs.pop(id(sock), None)
        try:
            sock.deleteLater()
        except RuntimeError:  # already deleted by the server
            pass

    def _read(self, sock: QLocalSocket):
        buf = self._bufs.get(id(sock), b"") + bytes(sock.readAll())
        if b"\n" not in buf:
            self._bufs[id(sock)] = buf
            return
        line, rest = buf.split(b"\n", 1)
        self._bufs[id(sock)] = rest
        try:
            req = json.loads(line)
            result = self.handler(req.get("cmd", ""), req.get("args") or {})
            resp = {"ok": True, "result": result}
        except Exception as e:  # report to the caller, never crash the app
            resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        sock.write((json.dumps(resp) + "\n").encode())
        sock.flush()
        sock.disconnectFromServer()


def make_handler(app_store):
    """Command table. Names mirror the CLI: <noun>.<verb>."""
    def h(cmd: str, a: dict):
        threads, tasks, presets, layout = app_store.threads, app_store.tasks, app_store.presets, app_store.layout
        if cmd == "ping":
            return {"pid": os.getpid()}
        if cmd == "preset.list":
            return presets.presets
        if cmd == "thread.list":
            return [s for s in threads.summaries() if not a.get("task") or s["taskKey"] == a["task"]]
        if cmd == "thread.show":
            t = threads.get(a["id"])
            if t is None:
                raise KeyError(a["id"])
            s = t.summary()
            if a.get("transcript"):
                s["transcript"] = [dict(r) for r in t.transcript.rows()]
            return s
        if cmd == "thread.spawn":
            task = a.get("task") or ""
            if task:
                tid = tasks.dispatch(task, a["preset"], a["prompt"], a.get("parent", ""))
            else:
                tid = threads.spawn("", a["preset"], a["prompt"], a.get("parent", ""), a.get("title", ""))
            if a.get("open"):
                layout.openContent("thread", tid, threads.get(tid).title)
            return threads.get(tid).summary()
        if cmd == "thread.send":
            threads.send(a["id"], a["text"])
            return threads.get(a["id"]).summary()
        if cmd == "thread.stop":
            threads.stop(a["id"])
            return threads.get(a["id"]).summary()
        if cmd == "task.list":
            return tasks.list()
        if cmd == "task.show":
            t = tasks.get(a["key"])
            if not t:
                raise KeyError(a["key"])
            t["threads"] = tasks.threadsFor(a["key"])
            return t
        if cmd == "task.status":
            tasks.setStatus(a["key"], a["status"])
            return tasks.get(a["key"])
        if cmd == "task.create":
            return tasks.get(tasks.create(a["title"], a.get("description", "")))
        if cmd == "layout.open":
            layout.openContent(a["kind"], a.get("key", ""), a.get("title", ""))
            return True
        raise ValueError(f"unknown command {cmd!r}")
    return h
