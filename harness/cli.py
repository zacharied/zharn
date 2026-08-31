"""`python -m harness.cli` — the CLI agents use from inside a thread (like bb's BB_CLI).
Pure stdlib; talks to the running app over HARNESS_IPC."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time

sys.dont_write_bytecode = True  # never dirty the watched tree (would trigger a reload)


def request(cmd: str, args: dict) -> dict:
    path = os.environ.get("HARNESS_IPC")
    if not path:
        sys.exit("HARNESS_IPC is not set (run this from inside a harness thread)")
    payload = (json.dumps({"cmd": cmd, "args": args}) + "\n").encode()
    if os.name == "nt":
        with open(path, "r+b", buffering=0) as pipe:
            pipe.write(payload)
            data = b""
            while not data.endswith(b"\n"):
                chunk = pipe.read(65536)
                if not chunk:
                    break
                data += chunk
    else:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(30)
            s.connect(path)
            s.sendall(payload)
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
    resp = json.loads(data or b"{}")
    if not resp.get("ok"):
        sys.exit(f"error: {resp.get('error', 'no response')}")
    return resp["result"]


def out(value, as_json: bool):
    if as_json:
        print(json.dumps(value, indent=1))
    elif isinstance(value, list):
        for row in value:
            if isinstance(row, dict):
                print("  ".join(f"{k}={row[k]}" for k in ("id", "key", "name", "status", "title", "taskKey", "model") if k in row))
            else:
                print(row)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k != "transcript":
                print(f"{k}: {v}")
        for row in value.get("transcript", []):
            print(f"[{row['role']}/{row['kind']}] {row.get('name', '')} {row.get('text') or row.get('input', '')}")
    else:
        print(value)


def main(argv=None):
    p = argparse.ArgumentParser(prog="zharn", description="Drive the running zharn app.")
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="noun", required=True)

    th = sub.add_parser("thread").add_subparsers(dest="verb", required=True)
    sp = th.add_parser("spawn", help="Spawn a new thread (child of this one when run inside a thread)")
    sp.add_argument("--role", required=True)
    sp.add_argument("--prompt", required=True)
    sp.add_argument("--task", default=os.environ.get("HARNESS_TASK_KEY", ""))
    sp.add_argument("--no-parent", action="store_true", help="Do not parent to the current thread")
    sp.add_argument("--open", action="store_true", help="Open the thread as a tab in the UI")
    sp.add_argument("--wait", action="store_true", help="Block until the thread settles and print its last reply")
    th.add_parser("list").add_argument("--task", default="")
    sh = th.add_parser("show"); sh.add_argument("id"); sh.add_argument("--transcript", action="store_true")
    wt = th.add_parser("wait"); wt.add_argument("id"); wt.add_argument("--timeout", type=float, default=1200)
    sd = th.add_parser("send"); sd.add_argument("id"); sd.add_argument("--message", required=True)
    th.add_parser("stop").add_argument("id")

    rl = sub.add_parser("role").add_subparsers(dest="verb", required=True)
    rl.add_parser("list")

    tk = sub.add_parser("task").add_subparsers(dest="verb", required=True)
    tk.add_parser("list")
    tk.add_parser("show").add_argument("key")
    st = tk.add_parser("status"); st.add_argument("key"); st.add_argument("status")
    cr = tk.add_parser("create"); cr.add_argument("--title", required=True); cr.add_argument("--description", default="")

    sub.add_parser("ping")
    a = p.parse_args(argv)

    def wait(tid, timeout):
        t0 = time.time()
        while time.time() - t0 < timeout:
            s = request("thread.show", {"id": tid})
            if s["status"] in ("idle", "failed", "stopped"):
                return s
            time.sleep(0.5)
        sys.exit(f"timeout waiting for {tid}")

    if a.noun == "ping":
        out(request("ping", {}), a.json)
    elif a.noun == "role":
        out(request("role.list", {}), a.json)
    elif a.noun == "task":
        if a.verb == "list": out(request("task.list", {}), a.json)
        elif a.verb == "show": out(request("task.show", {"key": a.key}), a.json)
        elif a.verb == "status": out(request("task.status", {"key": a.key, "status": a.status}), a.json)
        elif a.verb == "create": out(request("task.create", {"title": a.title, "description": a.description}), a.json)
    elif a.noun == "thread":
        if a.verb == "spawn":
            parent = "" if a.no_parent else os.environ.get("HARNESS_THREAD_ID", "")
            s = request("thread.spawn", {"task": a.task, "role": a.role, "prompt": a.prompt, "parent": parent, "open": a.open})
            if a.wait:
                s = wait(s["id"], 1200)
                out(s if a.json else (s.get("lastText") or s["status"]), a.json)
            else:
                out(s if a.json else s["id"], a.json)
        elif a.verb == "list": out(request("thread.list", {"task": a.task}), a.json)
        elif a.verb == "show": out(request("thread.show", {"id": a.id, "transcript": a.transcript}), a.json)
        elif a.verb == "wait":
            s = wait(a.id, a.timeout)
            out(s if a.json else (s.get("lastText") or s["status"]), a.json)
        elif a.verb == "send": out(request("thread.send", {"id": a.id, "text": a.message}), a.json)
        elif a.verb == "stop": out(request("thread.stop", {"id": a.id}), a.json)


if __name__ == "__main__":
    main()
