"""Agent drivers: run a provider CLI as a child process and turn its event stream into a
transcript model. Provider = claude-code (`claude -p --output-format stream-json`).

Everything here is hot-reloadable; live processes are QProcess objects owned by Context objects.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QByteArray, QModelIndex, QObject, QProcess,
                            QProcessEnvironment, Qt, QTimer, Signal, Slot)

from harness import config as cfg

# --------------------------------------------------------------------------- transcript model
ROLES = ("role", "kind", "text", "name", "input", "toolId", "isError", "streaming", "ts", "meta")
_ROLE_IDS = {Qt.ItemDataRole.UserRole + i: r for i, r in enumerate(ROLES)}


class TranscriptModel(QAbstractListModel):
    """Flat list of blocks: user text, assistant text, tool_use, tool_result, system notes, errors."""

    countChanged = Signal()

    def __init__(self):
        super().__init__()
        self._rows: list[dict] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def roleNames(self):
        return {k: QByteArray(v.encode()) for k, v in _ROLE_IDS.items()}

    def data(self, index, role):
        if not index.isValid():
            return None
        return self._rows[index.row()].get(_ROLE_IDS.get(role, ""))

    def rows(self) -> list[dict]:
        return self._rows

    def append(self, **row) -> int:
        row = {"role": "", "kind": "text", "text": "", "name": "", "input": "", "toolId": "",
               "isError": False, "streaming": False, "ts": time.time(), "meta": "", **row}
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append(row)
        self.endInsertRows()
        self.countChanged.emit()
        return len(self._rows) - 1

    def update(self, i: int, **changes):
        if 0 <= i < len(self._rows):
            self._rows[i].update(changes)
            idx = self.index(i)
            self.dataChanged.emit(idx, idx)

    def last_index(self, **match):
        for i in range(len(self._rows) - 1, -1, -1):
            if all(self._rows[i].get(k) == v for k, v in match.items()):
                return i
        return -1

    @Slot(result=int)
    def count(self):
        return len(self._rows)

    @Slot(int, result="QVariantMap")
    def get(self, i):
        return dict(self._rows[i]) if 0 <= i < len(self._rows) else {}


# --------------------------------------------------------------------------- claude-code process
def split_command(text: str, nt: bool) -> list[str]:
    """A command line into argv. POSIX quoting on POSIX. On Windows a backslash is a path separator, not an escape,
    and a double-quoted token is one argument with the quotes removed (shlex's non-POSIX mode leaves them on)."""
    if not nt:
        return shlex.split(text)
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] == '"' else t for t in shlex.split(text, posix=False)]


def claude_command() -> list[str]:
    """The CLI to run. HARNESS_CLAUDE_CMD overrides (tests point it at a fake)."""
    override = os.environ.get("HARNESS_CLAUDE_CMD")
    if override:
        return split_command(override, nt=os.name == "nt")
    return list(getattr(cfg, "CLAUDE_CMD", ["claude"]))


def _block_text(content) -> str:
    """tool_result / message content can be a string or a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return "" if content is None else str(content)


class ClaudeCodeProcess(QObject):
    """One `claude -p` process speaking stream-json on both stdin and stdout."""

    event = Signal(object)          # parsed JSON event
    stderrText = Signal(str)
    finished = Signal(int, str)     # exit code, QProcess exit status name
    started = Signal()

    def __init__(self, *, cwd: str, env: dict, model: str = "", permission: str = "auto",
                 resume: str = "", system_prompt: str = "", extra_args=()):
        super().__init__()
        self.proc = QProcess()
        self.proc.setWorkingDirectory(cwd)
        penv = QProcessEnvironment.systemEnvironment()
        for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):  # allow nesting inside another claude
            penv.remove(k)
        for k, v in env.items():
            penv.insert(k, str(v))
        self.proc.setProcessEnvironment(penv)
        cmd = claude_command()
        args = cmd[1:] + ["-p", "--output-format", "stream-json", "--input-format", "stream-json",
                          "--verbose", "--include-partial-messages", "--replay-user-messages"]
        if model:
            args += ["--model", model]
        args += list(getattr(cfg, "PERMISSION_FLAGS", {}).get(permission, ["--permission-mode", "acceptEdits"]))
        if resume:
            args += ["--resume", resume]
        if system_prompt:
            args += ["--append-system-prompt", system_prompt]
        args += list(extra_args)
        # Resolve on PATH ourselves: QProcess on Windows only finds .exe, not .cmd shims, and a
        # program that fails to start never emits finished() — the thread would hang in "starting".
        self.program, self.args = shutil.which(cmd[0]) or cmd[0], args
        self._buf = b""
        self._done = False
        self.proc.readyReadStandardOutput.connect(self._read_stdout)
        self.proc.readyReadStandardError.connect(lambda: self.stderrText.emit(bytes(self.proc.readAllStandardError()).decode(errors="replace")))
        self.proc.finished.connect(self._on_finished)
        self.proc.errorOccurred.connect(self._on_error)
        self.proc.started.connect(self.started)

    def _finish(self, code: int, status: str):
        if self._done:
            return
        self._done = True
        try:
            self.finished.emit(code, status)
        except RuntimeError:  # we are being torn down
            pass

    def _on_finished(self, code, status):
        self._finish(code, status.name)

    def _on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.stderrText.emit(f"failed to start {self.program!r}: {self.proc.errorString()} "
                                 f"(is the CLI installed and on PATH? see CLAUDE_CMD / HARNESS_CLAUDE_CMD)")
            self._finish(-1, "FailedToStart")

    def start(self):
        self.proc.start(self.program, self.args)

    def running(self) -> bool:
        return self.proc.state() != QProcess.ProcessState.NotRunning

    def send_user(self, text: str):
        msg = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
        self.proc.write((json.dumps(msg) + "\n").encode())

    def close_stdin(self):
        self.proc.closeWriteChannel()

    def stop(self):
        if not self.running():
            return
        self.proc.terminate()
        QTimer.singleShot(3000, lambda: self.proc.kill() if self.running() else None)

    def release(self):
        """Asynchronous: close stdin (claude exits on EOF), then terminate/kill on timers. For recycling a context
        mid-session; never blocks the GUI thread."""
        if not self.running():
            return
        self.proc.closeWriteChannel()
        QTimer.singleShot(2000, lambda: self.proc.terminate() if self.running() else None)
        QTimer.singleShot(3000, lambda: self.proc.kill() if self.running() else None)

    def shutdown(self, wait_ms: int = 2000):
        """Synchronous, for app exit: close stdin (claude exits on EOF), then terminate/kill."""
        if not self.running():
            return
        self.proc.closeWriteChannel()
        if not self.proc.waitForFinished(wait_ms):
            self.proc.terminate()
            if not self.proc.waitForFinished(1000):
                self.proc.kill()
                self.proc.waitForFinished(500)

    def _read_stdout(self):
        self._buf += bytes(self.proc.readAllStandardOutput())
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                self.event.emit(json.loads(line))
            except ValueError:
                self.stderrText.emit(line.decode(errors="replace"))


# --------------------------------------------------------------------------- event → transcript
class StreamInterpreter:
    """Applies claude-code stream-json events to a TranscriptModel. Also used for replay."""

    def __init__(self, model: TranscriptModel):
        self.model = model
        self.session_id = ""
        self.model_name = ""
        self.cost_usd = 0.0
        self.turns = 0
        self.context_tokens = 0   # the input side of the latest API call: what the context holds (lifecycle spec §2.3)
        self.context_window = 0   # the model's window, from the latest result's modelUsage; 0 until the first
        self._current = -1        # index of the block currently streaming
        self._tool_json = ""

    def apply(self, ev: dict) -> str | None:
        """Returns a status hint ('working' | 'idle' | 'failed') or None."""
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            self.session_id = ev.get("session_id", self.session_id)
            self.model_name = ev.get("model", self.model_name)
            return "working"
        if t == "system" and ev.get("subtype") == "compact_boundary":
            # Never expected: every spawn sets DISABLE_AUTO_COMPACT=1. Visible rather than silent if it happens.
            self.model.append(role="system", kind="error", isError=True,
                              text="the CLI compacted this context on its own; the reading below is no longer the whole conversation")
            return None
        if t == "stream_event":
            self._stream(ev.get("event") or {})
            return None
        if t == "assistant":
            msg = ev.get("message") or {}
            usage = msg.get("usage") or {}
            if usage:
                self.context_tokens = sum(int(usage.get(k) or 0) for k in
                                          ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            for block in msg.get("content", []):
                self._finalize_block(block)
            return None
        if t == "user":
            for block in (ev.get("message") or {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    self.model.append(role="tool", kind="tool_result", toolId=block.get("tool_use_id", ""),
                                      text=_block_text(block.get("content")), isError=bool(block.get("is_error")))
            return None
        if t == "result":
            self.turns += int(ev.get("num_turns") or 0)
            self.cost_usd += float(ev.get("total_cost_usd") or 0.0)
            self.session_id = ev.get("session_id", self.session_id)
            per_model = ev.get("modelUsage") or {}
            mu = per_model.get(self.model_name) or next(iter(per_model.values()), {})
            if mu.get("contextWindow"):
                self.context_window = int(mu["contextWindow"])
            self._current = -1
            if ev.get("is_error"):
                self.model.append(role="system", kind="error", text=_block_text(ev.get("result")) or ev.get("subtype", "error"), isError=True)
                return "failed"
            return "idle"
        return None

    def _stream(self, e: dict):
        et = e.get("type")
        if et == "content_block_start":
            cb = e.get("content_block") or {}
            if cb.get("type") == "text":
                self._current = self.model.append(role="assistant", kind="text", text=cb.get("text", ""), streaming=True)
            elif cb.get("type") == "tool_use":
                self._tool_json = ""
                self._current = self.model.append(role="assistant", kind="tool_use", name=cb.get("name", ""),
                                                  toolId=cb.get("id", ""), input="", streaming=True)
            elif cb.get("type") == "thinking":
                self._current = self.model.append(role="assistant", kind="thinking", text="", streaming=True)
            else:
                self._current = -1
        elif et == "content_block_delta" and self._current >= 0:
            d = e.get("delta") or {}
            row = self.model.rows()[self._current]
            if d.get("type") == "text_delta":
                self.model.update(self._current, text=row["text"] + d.get("text", ""))
            elif d.get("type") == "input_json_delta":
                self._tool_json += d.get("partial_json", "")
                self.model.update(self._current, input=self._tool_json)
            elif d.get("type") == "thinking_delta":
                self.model.update(self._current, text=row["text"] + d.get("thinking", ""))
        elif et == "content_block_stop" and self._current >= 0:
            self.model.update(self._current, streaming=False)
            self._current = -1

    def _finalize_block(self, block: dict):
        """Complete assistant blocks: reconcile with a streamed block, or append if none streamed."""
        bt = block.get("type")
        if bt == "text":
            i = self.model.last_index(role="assistant", kind="text")
            if i >= 0 and (self.model.rows()[i]["streaming"] or self.model.rows()[i]["text"] == block.get("text")):
                self.model.update(i, text=block.get("text", ""), streaming=False)
            else:
                self.model.append(role="assistant", kind="text", text=block.get("text", ""))
        elif bt == "tool_use":
            inp = json.dumps(block.get("input", {}), indent=1)
            i = self.model.last_index(role="assistant", kind="tool_use", toolId=block.get("id", ""))
            if i >= 0:
                self.model.update(i, input=inp, streaming=False)
            else:
                self.model.append(role="assistant", kind="tool_use", name=block.get("name", ""), toolId=block.get("id", ""), input=inp)
        elif bt == "thinking":
            i = self.model.last_index(role="assistant", kind="thinking")
            if i >= 0:
                self.model.update(i, text=block.get("thinking", "") or self.model.rows()[i]["text"], streaming=False)
