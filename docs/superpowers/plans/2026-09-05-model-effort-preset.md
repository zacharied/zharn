# Model + effort + skills-preset, in place of roles

**Goal (ZHAR-5).** The one dropdown that picks a *role* — a bundle of provider, model, reasoning,
permission, instructions and outline_first — is replaced by two fine-grained controls: a **model**
selector and an **effort** selector, plus a **preset** selector whose only power is which skills a
character wakes up with. What the role used to carry besides model and effort now comes from the
**position** a character is cast into, which nobody picks: it is implied by the cast site.

Answers taken as decided (the author approved the defaults of the planning yield):

1. Instructions and the outline-first rule come **by position** from config. A friend's specific job
   stays in its call note.
2. A preset **names a subset of `harness/skills/`**; the harness builds a filtered plugin tree per
   preset. `being-a-character` and the phase skills are injected by the harness regardless — a preset
   cannot switch them off.
3. The model selector is an **editable combo** over a new `config.MODELS`; anything unlisted can be
   typed.
4. Permission comes from the position. Provider is a **property of the model**, not a choice.
5. All four surfaces get the controls: story Start row, Recast, New context, and CLI/IPC.

## The contract

```python
# config_def.py
MODELS = [{"id": "", "label": "cli default", "provider": "claude-code"}, ...]   # id "" = the CLI's own default
EFFORTS = ["", "low", "medium", "high", "xhigh", "max"]                        # "" = the provider's default
DEFAULT_PRESETS = [{"name": "full", "skills": ["*"]}, ...]                     # "*" = every skill in the tree
CAST_POSITIONS = {"protagonist": {"label", "instructions", "outline_first", "permission",
                                  "model", "effort", "preset"}, "friend": {...}, "bare": {...}}
```

```python
# casting.py (replaces roles.py) — CastStore, exposed to QML as `app.casting`
presets -> [{"name", "skills"}]      presetNames()      preset(name)      save(p) / remove(name)
models  -> [{"id", "label", "provider"}]                efforts -> [str]  positions -> [str]
resolve(position, model, effort, preset) -> cast        # the dict a context is spawned from
preset_skills(name) -> list[str] | None                 # None = the whole tree
```

A **cast** is `{position, label, instructions, outline_first, permission, provider, model, effort,
preset}`. It replaces `roleConfig` on a context's meta; `Character.role` becomes `position` and the
character also stores the `model`, `effort` and `preset` it was cast with, so a recast reuses them.

```python
# skills.py
plugin_dir(preset, names, cache) -> Path      # source tree when names is None; else a filtered copy under cache
plugin_args(preset, names, cache) -> [str]
```

## Steps

| # | Step | Files | Proof |
|---|---|---|---|
| 1 | Config + `casting.py` + preset-filtered plugin trees | `config_def.py`, `casting.py` (del `roles.py`), `skills.py` | `tests/test_casting.py` (new, replaces `test_roles.py`), `tests/test_skills.py` |
| 2 | Plumbing: cast through spawn, character records, recast, IPC, CLI | `contexts.py`, `stories.py`, `store.py`, `__main__.py`, `shell.py`, `ipc.py`, `cli.py` | `test_contexts_unit.py`, `test_stories.py`, `test_ipc.py`, `test_cli.py`, `test_agents.py`, `test_qmodels.py` |
| 3 | The three selectors | `qml/content/Story.qml`, `qml/ui/RecastDialog.qml`, `qml/content/Contexts.qml` | `test_ui_story.py`, `test_ui_chrome.py` |
| 4 | Spec and prose | `docs/specs/story-lifecycle.md` §1/§5/§6, `DESIGN.md`, `README.md`, skill bodies that say `--role` | `test_skills.py` |

Step 1 is the contract and lands first; 2 and 4 are disjoint and go out together; 3 follows 2.

## Not in scope

No new permission mode for bare contexts (they keep `auto`). Codex stays a provider a model may
name; it is still refused at spawn like today.
