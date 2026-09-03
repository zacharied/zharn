"""`python -m harness.cli` — the CLI agents use from inside a context (like bb's BB_CLI).
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
        sys.exit("HARNESS_IPC is not set (run this from inside a harness context)")
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
                print("  ".join(f"{k}={row[k]}" for k in ("id", "key", "name", "phase", "ball", "status", "title", "storyKey", "owner", "kind", "model") if k in row))
            else:
                print(row)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k not in ("comments", "cast", "contexts", "transcript"):
                print(f"{k}: {v}")
        for c in value.get("comments", []):
            print(f"[{c.get('authorName', '')}/{c['kind']}] {c['body']}")
        for row in value.get("transcript", []):
            print(f"[{row['role']}/{row['kind']}] {row.get('name', '')} {row.get('text') or row.get('input', '')}")
    else:
        print(value)


def main(argv=None):
    p = argparse.ArgumentParser(prog="zharn", description="Drive the running zharn app.")
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="noun", required=True)

    ctx = sub.add_parser("context").add_subparsers(dest="verb", required=True)
    nw = ctx.add_parser("new", help="Create a new context")
    nw.add_argument("--role", required=True)
    nw.add_argument("--prompt", default="")
    nw.add_argument("--title", default="")
    nw.add_argument("--open", action="store_true", help="Open the context as a tab in the UI")
    nw.add_argument("--wait", action="store_true", help="Block until the context settles and print its last reply")
    ctx.add_parser("list").add_argument("--story", default="")
    sh = ctx.add_parser("show"); sh.add_argument("id"); sh.add_argument("--transcript", action="store_true")
    wt = ctx.add_parser("wait"); wt.add_argument("id"); wt.add_argument("--timeout", type=float, default=1200)
    sd = ctx.add_parser("send"); sd.add_argument("id"); sd.add_argument("--message", required=True)
    ctx.add_parser("stop").add_argument("id")

    rl = sub.add_parser("role").add_subparsers(dest="verb", required=True)
    rl.add_parser("list")

    stp = sub.add_parser("story").add_subparsers(dest="verb", required=True)
    stp.add_parser("list")
    stp.add_parser("show").add_argument("key", nargs="?", default=os.environ.get("HARNESS_STORY_KEY", ""))
    c = stp.add_parser("create"); c.add_argument("--title", required=True); c.add_argument("--description", default="")
    c.add_argument("--start", action="store_true", help="Start it now (characters: a sub-story you author)"); c.add_argument("--role", default="")
    s = stp.add_parser("start"); s.add_argument("key"); s.add_argument("--note", default=""); s.add_argument("--role", default="")
    y = stp.add_parser("yield"); y.add_argument("--question", action="store_true"); y.add_argument("--handoff", action="store_true")
    y.add_argument("--body", required=True); y.add_argument("--options", default=""); y.add_argument("--thread", default="")
    pr = stp.add_parser("proceed"); pr.add_argument("key", nargs="?", default=""); pr.add_argument("--note", default="")
    rc = stp.add_parser("recap"); rc.add_argument("--body", required=True); rc.add_argument("--thread", default="")
    cm = stp.add_parser("comment"); cm.add_argument("--body", required=True); cm.add_argument("--thread", default=""); cm.add_argument("--story", default=os.environ.get("HARNESS_STORY_KEY", ""))
    cm.add_argument("--to", action="append", default=[], help="@Name — deliver to Name too; with no --thread, open a thread to Name")
    cl = stp.add_parser("call", help="Cast a friend on its own thread"); cl.add_argument("--role", required=True)
    cl.add_argument("--as", dest="as_name", default=""); cl.add_argument("--fork", action="store_true", help="the friend starts with a copy of your memory")
    cl.add_argument("--note", required=True)
    stp.add_parser("wait", help="List what you await; then end your turn")
    stp.add_parser("inbox", help="Comments waiting for you")
    stp.add_parser("cast", help="The cast of a story").add_argument("key", nargs="?", default="")
    rp = stp.add_parser("reply"); rp.add_argument("key"); rp.add_argument("--body", required=True); rp.add_argument("--thread", default="")
    rv = stp.add_parser("resolve", help="Close a side thread waiting on you; nobody is resumed")
    rv.add_argument("key", nargs="?", default=""); rv.add_argument("--thread", required=True); rv.add_argument("--note", default="")
    for v in ("approve", "back", "cancel", "reopen"):
        x = stp.add_parser(v); x.add_argument("key"); x.add_argument("--note", default="")

    rcst = stp.add_parser("recast", help="Replace a character's context: same character, fresh memory")
    rcst.add_argument("key"); rcst.add_argument("target", help="character id"); rcst.add_argument("--role", default=""); rcst.add_argument("--model", default="")
    sub.add_parser("ping")
    a = p.parse_args(argv)

    def wait(cid, timeout):
        t0 = time.time()
        while time.time() - t0 < timeout:
            s = request("context.show", {"id": cid})
            if s["status"] in ("idle", "failed", "stopped"):
                return s
            time.sleep(0.5)
        sys.exit(f"timeout waiting for {cid}")

    def character() -> str:
        ch = os.environ.get("HARNESS_CHARACTER_ID", "")
        if not ch:
            sys.exit("HARNESS_CHARACTER_ID is not set (run this inside a character)")
        return ch

    if a.noun == "ping":
        out(request("ping", {}), a.json)
    elif a.noun == "role":
        out(request("role.list", {}), a.json)
    elif a.noun == "context":
        if a.verb == "new":
            s = request("context.new", {"role": a.role, "prompt": a.prompt, "title": a.title, "open": a.open})
            if a.wait:
                s = wait(s["id"], 1200)
                out(s if a.json else (s.get("lastText") or s["status"]), a.json)
            else:
                out(s if a.json else s["id"], a.json)
        elif a.verb == "list": out(request("context.list", {"story": a.story}), a.json)
        elif a.verb == "show": out(request("context.show", {"id": a.id, "transcript": a.transcript}), a.json)
        elif a.verb == "wait":
            s = wait(a.id, a.timeout)
            out(s if a.json else (s.get("lastText") or s["status"]), a.json)
        elif a.verb == "send": out(request("context.send", {"id": a.id, "text": a.message}), a.json)
        elif a.verb == "stop": out(request("context.stop", {"id": a.id}), a.json)
    elif a.noun == "story":
        ch = os.environ.get("HARNESS_CHARACTER_ID", "")
        if a.verb == "list": out(request("story.list", {}), a.json)
        elif a.verb == "show": out(request("story.show", {"key": a.key}), a.json)
        elif a.verb == "create":
            args = {"title": a.title, "description": a.description}
            if ch:
                args.update(character=ch, start=a.start, role=a.role)
            out(request("story.create", args), a.json)
        elif a.verb == "start": out(request("story.start", {"key": a.key, "note": a.note, "role": a.role}), a.json)
        elif a.verb == "yield":
            if a.question == a.handoff:
                sys.exit("yield needs exactly one of --question / --handoff")
            opts = [o.strip() for o in a.options.split(",") if o.strip()]
            out(request("story.yield", {"character": character(), "kind": "question" if a.question else "handoff",
                                        "body": a.body, "options": opts, "thread": a.thread}), a.json)
        elif a.verb == "recap": out(request("story.recap", {"character": character(), "body": a.body, "thread": a.thread}), a.json)
        elif a.verb == "call": out(request("story.call", {"character": character(), "role": a.role, "note": a.note, "as": a.as_name, "fork": a.fork}), a.json)
        elif a.verb == "wait": out(request("story.wait", {"character": character()}), a.json)
        elif a.verb == "inbox": out(request("story.inbox", {"character": character()}), a.json)
        elif a.verb == "cast": out(request("story.cast", {"key": a.key, **({"character": ch} if ch else {})}), a.json)
        elif a.verb == "proceed":
            args = {"character": ch, "note": a.note} if ch and not a.key else {"key": a.key, "note": a.note, **({"character": ch} if ch else {})}
            out(request("story.proceed", args), a.json)
        elif a.verb == "comment":
            args = {"character": ch, "body": a.body, "thread": a.thread, "to": a.to} if ch else {"key": a.story, "body": a.body, "thread": a.thread}
            out(request("story.comment", args), a.json)
        elif a.verb == "reply":
            if ch:
                out(request("story.reply", {"character": ch, "key": a.key, "thread": a.thread, "body": a.body}), a.json)
            else:
                out(request("story.comment", {"key": a.key, "body": a.body, "thread": a.thread}), a.json)
        elif a.verb == "resolve":
            args = {"character": ch, "thread": a.thread, "note": a.note} if ch and not a.key else {"key": a.key, "thread": a.thread, "note": a.note, **({"character": ch} if ch else {})}
            out(request("story.resolve", args), a.json)
        elif a.verb == "recast":
            out(request("story.recast", {"key": a.key, "target": a.target, "role": a.role, "model": a.model, **({"character": ch} if ch else {})}), a.json)
        else: out(request(f"story.{a.verb}", {"key": a.key, "note": a.note, **({"character": ch} if ch else {})}), a.json)


if __name__ == "__main__":
    main()
