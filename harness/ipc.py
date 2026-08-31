"""Local IPC so agents (child processes) can drive the harness: spawn new contexts, wait on
them, list roles. One JSON request per connection, newline-terminated."""
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
    def story_cmd(cmd: str, a: dict):
        stories, contexts = app_store.stories, app_store.contexts
        verb = cmd.split(".", 1)[1]
        if verb == "list":
            return stories.list()
        if verb == "show":
            row = stories.get(a["key"])
            if not row:
                raise KeyError(a["key"])
            key = row["key"]
            return {**row, "comments": stories.comments(key), "cast": stories.cast(key),
                    "contexts": [c for c in contexts.summaries() if c["storyKey"] == key]}
        if verb == "create":
            return stories.get(stories.create(a["title"], a.get("description", "")))
        if verb == "start":
            chr_id = stories.start(a["key"], a.get("note", ""), a.get("role", ""))
            return {**stories.get(a["key"]), "character": chr_id}
        ch = a.get("character", "")
        if verb == "yield":
            return stories.cast_yield(ch, a["kind"], a["body"], a.get("options") or [], a.get("thread", ""))
        if verb == "recap":
            return stories.cast_recap(ch, a["body"])
        if verb == "comment":
            if ch:
                return stories.cast_comment(ch, a["body"], a.get("thread", ""))
            return stories.comment(a["key"], a["body"], a.get("thread", ""))
        if verb == "proceed":
            if ch:
                return stories.cast_proceed(ch, a.get("note", ""))
            stories.proceed(a["key"], a.get("note", ""))
            return stories.get(a["key"])
        if verb == "resolve":
            if ch:
                return stories.cast_resolve(ch, a.get("thread", ""), a.get("note", ""))
            return stories.resolve(a["key"], a.get("thread", ""), a.get("note", ""))
        author = {"approve": stories.approve, "back": stories.backToPlanning, "cancel": stories.cancel, "reopen": stories.reopen}.get(verb)
        if author is not None:
            author(a["key"], a.get("note", ""))
            return stories.get(a["key"])
        raise ValueError(f"unknown command {cmd!r}")

    def h(cmd: str, a: dict):
        contexts, roles, layout = app_store.contexts, app_store.roles, app_store.layout
        if cmd == "ping":
            return {"pid": os.getpid()}
        if cmd == "role.list":
            return roles.roles
        if cmd.startswith("story."):
            ch = a.get("character", "")
            if not ch:
                return story_cmd(cmd, a)
            logged = {k: v for k, v in a.items() if k != "character"}
            try:
                result = story_cmd(cmd, a)
            except Exception as e:
                app_store.stories.log_verb(ch, cmd.split(".", 1)[1], logged, False, f"{type(e).__name__}: {e}")
                raise
            app_store.stories.log_verb(ch, cmd.split(".", 1)[1], logged, True)
            return result
        if cmd == "context.list":
            return [s for s in contexts.summaries() if not a.get("story") or s["storyKey"] == a["story"]]
        if cmd == "context.show":
            c = contexts.get(a["id"])
            if c is None:
                raise KeyError(a["id"])
            s = c.summary()
            if a.get("transcript"):
                s["transcript"] = [dict(r) for r in c.transcript.rows()]
            return s
        if cmd == "context.new":
            if a.get("prompt"):
                cid = contexts.spawn(a["role"], a["prompt"], title=a.get("title", ""))
            else:
                cid = contexts.create(a["role"], title=a.get("title") or "New context")
            if a.get("open"):
                layout.openContent("context", cid, contexts.get(cid).title)
            return contexts.get(cid).summary()
        if cmd == "context.send":
            contexts.send(a["id"], a["text"])
            return contexts.get(a["id"]).summary()
        if cmd == "context.stop":
            contexts.stop(a["id"])
            return contexts.get(a["id"]).summary()
        if cmd == "layout.open":
            layout.openContent(a["kind"], a.get("key", ""), a.get("title", ""))
            return True
        raise ValueError(f"unknown command {cmd!r}")
    return h
