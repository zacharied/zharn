"""A stand-in for `claude -p --output-format stream-json --input-format stream-json`.
Speaks the real event protocol (captured from claude 2.1.250). Behaviour is keyed on the prompt:
  contains "tool"        → a tool_use + tool_result round before the answer
  contains "fail"        → result with is_error
  contains "slow"        → 1.5 s pause before answering
"""
import json
import os
import subprocess
import sys
import time

SESSION = "fake-session-1"


def emit(obj):
    obj.setdefault("session_id", SESSION)
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def text_turn(text):
    emit({"type": "stream_event", "event": {"type": "message_start"}})
    emit({"type": "stream_event", "event": {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}})
    for i in range(0, len(text), 4):
        emit({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text[i:i + 4]}}})
        time.sleep(0.005)
    emit({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "model": "fake-model"}})
    emit({"type": "stream_event", "event": {"type": "content_block_stop", "index": 0}})
    emit({"type": "stream_event", "event": {"type": "message_stop"}})


def tool_turn(name, inp, output, is_error=False):
    emit({"type": "stream_event", "event": {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "toolu_fake1", "name": name, "input": {}}}})
    emit({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": json.dumps(inp)}}})
    emit({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_fake1", "name": name, "input": inp}], "model": "fake-model"}})
    emit({"type": "stream_event", "event": {"type": "content_block_stop", "index": 0}})
    emit({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_fake1", "content": output, "is_error": is_error}]}})


def main():
    args = sys.argv[1:]
    global SESSION
    if "--resume" in args:
        SESSION = args[args.index("--resume") + 1]
        if "--fork-session" in args:  # a fork gets a fresh id; the source session is untouched
            SESSION = "fork-of-" + SESSION
    emit({"type": "system", "subtype": "init", "cwd": os.getcwd(), "model": "fake-model", "tools": ["Bash"], "argv": args,
          "harness_env": {k: os.environ[k] for k in ("HARNESS_CONTEXT_ID", "HARNESS_STORY_KEY", "HARNESS_CHARACTER_ID", "HARNESS_WORKSPACE", "HARNESS_REPO", "HARNESS_ENV") if k in os.environ}})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        prompt = "".join(b.get("text", "") for b in msg["message"]["content"] if isinstance(b, dict))
        if "--replay-user-messages" in args:  # like claude: echo a user message when it is consumed
            emit({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}})
        last = prompt.strip().splitlines()[-1] if prompt.strip() else ""
        emit({"type": "system", "subtype": "status", "status": "requesting"})
        if "slow" in prompt:
            time.sleep(1.5)
        elif "yield-question" in prompt:
            cli = os.environ["HARNESS_CLI"].split() + ["story", "yield", "--question", "--body", "which one?", "--options", "a,b"]
            r = subprocess.run(cli, capture_output=True, text=True, env=os.environ)
            tool_turn("Bash", {"command": "zharn story yield --question …"}, (r.stdout + r.stderr).strip(), is_error=r.returncode != 0)
        if "tool" in prompt:
            tool_turn("Bash", {"command": "echo hello-from-tool"}, "hello-from-tool")
        if "fail" in prompt:
            emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "simulated failure",
                  "num_turns": 1, "total_cost_usd": 0.001, "duration_ms": 5})
            continue
        text_turn(f"echo: {last}")
        emit({"type": "result", "subtype": "success", "is_error": False, "result": f"echo: {last}", "num_turns": 1,
              "total_cost_usd": 0.0123, "duration_ms": 42, "stop_reason": "end_turn"})


if __name__ == "__main__":
    main()
