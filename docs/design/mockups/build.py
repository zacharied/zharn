"""Static HTML mockups of the zharn UI (JetBrains New UI conventions + the story model).
Run: python build.py  → writes *.html next to this file. Pure design artifacts, no app code."""
from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------- icons (expui-style, 16px, stroke 1.5)
ICONS = {
    "stories": '<path d="M2.5 4h11M2.5 8h11M2.5 12h11"/><circle cx="2.5" cy="4" r=".9" fill="currentColor" stroke="none"/><circle cx="2.5" cy="8" r=".9" fill="currentColor" stroke="none"/><circle cx="2.5" cy="12" r=".9" fill="currentColor" stroke="none"/>',
    "files": '<path d="M2 4.5A1.5 1.5 0 0 1 3.5 3H6l1.5 1.5h5A1.5 1.5 0 0 1 14 6v5.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 11.5z"/>',
    "git": '<circle cx="4" cy="3.5" r="1.5"/><circle cx="4" cy="12.5" r="1.5"/><circle cx="12" cy="5.5" r="1.5"/><path d="M4 5v6M12 7c0 3-8 1.5-8 4"/>',
    "cast": '<circle cx="6" cy="5" r="2.25"/><path d="M1.75 13c0-2.4 1.9-4 4.25-4s4.25 1.6 4.25 4"/><circle cx="11.5" cy="5.5" r="1.75"/><path d="M11 9c1.9 0 3.25 1.3 3.25 3.25"/>',
    "contexts": '<rect x="2.5" y="2.5" width="11" height="4" rx="1"/><rect x="2.5" y="9.5" width="11" height="4" rx="1"/><circle cx="5" cy="4.5" r=".8" fill="currentColor" stroke="none"/><circle cx="5" cy="11.5" r=".8" fill="currentColor" stroke="none"/>',
    "terminal": '<path d="M3 4.5l4 3.5-4 3.5M8.5 12h4.5"/>',
    "search": '<circle cx="7" cy="7" r="4.25"/><path d="M10.2 10.2L13.5 13.5"/>',
    "settings": '<circle cx="8" cy="8" r="2"/><path d="M8 1.75v2M8 12.25v2M1.75 8h2M12.25 8h2M3.6 3.6l1.4 1.4M11 11l1.4 1.4M3.6 12.4L5 11M11 5l1.4-1.4"/>',
    "play": '<path d="M4.5 3.2v9.6L12.5 8z" fill="currentColor" stroke="none"/>',
    "plus": '<path d="M8 3v10M3 8h10"/>',
    "minus": '<path d="M3 8h10"/>',
    "more": '<circle cx="3.5" cy="8" r="1.1" fill="currentColor" stroke="none"/><circle cx="8" cy="8" r="1.1" fill="currentColor" stroke="none"/><circle cx="12.5" cy="8" r="1.1" fill="currentColor" stroke="none"/>',
    "down": '<path d="M4 6.5l4 3.5 4-3.5"/>',
    "right": '<path d="M6.5 4l3.5 4-3.5 4"/>',
    "close": '<path d="M4 4l8 8M12 4l-8 8"/>',
    "pin": '<path d="M9.5 2.5l4 4-2 1-1.5 4-2-2L4.5 13 3 11.5 6.5 8l-2-2 4-1.5z"/>',
    "story": '<rect x="2.5" y="2.5" width="11" height="11" rx="1.5"/><path d="M5 6h6M5 8.5h6M5 11h3.5"/>',
    "context": '<path d="M2.5 3.5h11v7h-6.5L4 13v-2.5H2.5z"/>',
    "splitv": '<rect x="2.5" y="2.5" width="11" height="11" rx="1.5"/><path d="M8 2.5v11"/>',
    "splith": '<rect x="2.5" y="2.5" width="11" height="11" rx="1.5"/><path d="M2.5 8h11"/>',
    "folder-open": '<path d="M2 5.5A1.5 1.5 0 0 1 3.5 4H6l1.5 1.5h5A1.5 1.5 0 0 1 14 7M2 5.5V12a1 1 0 0 0 1 1h9.2a1 1 0 0 0 .96-.72L14.5 8H4.6a1 1 0 0 0-.96.72z"/>',
    "check": '<path d="M3 8.5l3 3 7-7"/>',
    "x": '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>',
    "home": '<path d="M2.5 8L8 3l5.5 5M4 7v6h8V7"/>',
    "role": '<circle cx="8" cy="5.5" r="2.5"/><path d="M3 14c0-2.8 2.2-4.5 5-4.5s5 1.7 5 4.5"/>',
    "aside": '<path stroke-dasharray="2.6 1.9" d="M2.5 3.5h11v7h-6.5L4 13v-2.5H2.5z"/>',
}

def ic(name, size=16, cls=""):
    return (f'<svg class="ic {cls}" width="{size}" height="{size}" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')

# ---------------------------------------------------------------- tokens + shared css
CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
:root{
  --bg:#1E1F22; --panel:#2B2D30; --border:#393B40; --hover:#393B40; --sel:#2E436E; --sel-dim:#25324f;
  --accent:#3574F0; --accent-hi:#4A88FF; --text:#DFE1E5; --muted:#868A91; --dim:#6C707A; --btn-border:#5A5D63;
  --ph-todo:#7FB5AA; --ph-plan:#B893EA; --ph-impl:#7DA7FF; --ph-done:#7CC47F; --ph-off:#868A91;
  --amber:#D6AE58; --amber-dim:rgba(214,174,88,.14); --green:#5FAD65; --red:#F75464; --red-dim:rgba(247,84,100,.12);
  --ui:"Inter","Segoe UI",system-ui,sans-serif; --mono:"JetBrains Mono","Cascadia Mono",Consolas,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:#131417;overflow:hidden}
body{font:13px/1.35 var(--ui);color:var(--text);-webkit-font-smoothing:antialiased}
.ic{flex:none;display:inline-block;vertical-align:-3px}
.mono{font-family:var(--mono)}
.frame{position:absolute;top:0;left:0;transform-origin:0 0;background:var(--bg);overflow:hidden;box-shadow:0 0 0 1px #000}
.win{display:flex;flex-direction:column;width:100%;height:100%}

/* ---- main toolbar */
.toolbar{height:40px;background:var(--panel);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 8px 0 10px;gap:6px;flex:none}
.tb-widget{display:flex;align-items:center;gap:7px;height:28px;padding:0 8px 0 6px;border-radius:4px;color:var(--text)}
.tb-widget:hover{background:var(--hover)}
.ws-icon{width:20px;height:20px;border-radius:5px;background:linear-gradient(135deg,#7C5CFF,#3574F0);display:grid;place-items:center;font:600 11px var(--ui);color:#fff}
.tb-sep{width:1px;height:20px;background:var(--border);margin:0 4px}
.tb-spacer{flex:1}
.tb-btn{width:28px;height:28px;border-radius:4px;display:grid;place-items:center;color:var(--muted)}
.tb-btn:hover{background:var(--hover);color:var(--text)}
.run-widget{display:flex;align-items:center;height:28px;border-radius:4px;background:#2E3238;color:var(--text)}
.run-widget .go{display:flex;align-items:center;gap:6px;padding:0 10px 0 8px;height:100%;color:var(--green)}
.run-widget .go span{color:var(--text)}
.run-widget .dd{height:100%;padding:0 6px;display:grid;place-items:center;border-left:1px solid var(--border);color:var(--muted)}

/* ---- body: strips / tool windows / editor */
.body{flex:1;display:flex;min-height:0}
.strip{width:40px;background:var(--panel);display:flex;flex-direction:column;align-items:center;padding:6px 0;gap:4px;flex:none}
.strip.left{border-right:1px solid var(--border)} .strip.right{border-left:1px solid var(--border)}
.strip .gap{flex:1}
.sbtn{position:relative;width:28px;height:28px;border-radius:6px;display:grid;place-items:center;color:var(--muted)}
.sbtn:hover{background:var(--hover);color:var(--text)}
.sbtn.on{background:var(--hover);color:var(--text)}
.sbtn .badge{position:absolute;top:-3px;right:-4px;min-width:15px;height:15px;padding:0 4px;border-radius:8px;background:var(--amber);color:#1E1F22;font:600 10px/15px var(--ui);text-align:center}
.sbtn .dot{position:absolute;top:2px;right:2px;width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 2px var(--panel)}

.toolwin{background:var(--panel);display:flex;flex-direction:column;flex:none;min-width:0}
.toolwin.left{width:290px;border-right:1px solid var(--border)}
.toolwin.right{width:320px;border-left:1px solid var(--border)}
.toolwin.bottom{border-top:1px solid var(--border);width:auto}
.tw-head{height:36px;display:flex;align-items:center;padding:0 6px 0 12px;gap:8px;flex:none}
.tw-head .t{font-weight:600}
.tw-head .sub{color:var(--muted);font-weight:400}
.tw-head .sp{flex:1}
.tw-head .a{width:24px;height:24px;border-radius:4px;display:grid;place-items:center;color:var(--muted)}
.tw-head .a:hover{background:var(--hover);color:var(--text)}
.chip{display:inline-flex;align-items:center;gap:5px;height:18px;padding:0 7px;border-radius:9px;font:500 11px/18px var(--ui)}
.chip.amber{background:var(--amber-dim);color:var(--amber)}
.chip.blue{background:rgba(53,116,240,.16);color:#7DA7FF}
.chip.grey{background:rgba(134,138,145,.14);color:var(--muted)}

.center{flex:1;display:flex;flex-direction:column;min-width:0;min-height:0;background:var(--bg)}
.center-split{flex:1;display:flex;flex-direction:column;min-height:0}
.tabs{height:36px;display:flex;align-items:stretch;background:var(--panel);border-bottom:1px solid var(--border);flex:none;overflow:hidden;min-width:0}
.tab span:not(.cl):not(.live){overflow:hidden;text-overflow:ellipsis;max-width:220px}
.tab{display:flex;align-items:center;gap:7px;padding:0 10px 0 12px;color:var(--muted);border-right:1px solid var(--border);position:relative;white-space:nowrap}
.tab .ic{color:var(--muted)}
.tab.on{background:var(--bg);color:var(--text)}
.tab.on::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:var(--accent)}
.tab .cl{margin-left:4px;color:var(--dim);width:16px;height:16px;border-radius:3px;display:grid;place-items:center}
.tab .cl:hover{background:var(--hover);color:var(--text)}
.tab .live{width:6px;height:6px;border-radius:50%;background:var(--accent);margin-left:2px;animation:pulse 1.4s ease-in-out infinite}
.tabs .sp{flex:1}
.tabs .a{width:28px;display:grid;place-items:center;color:var(--dim)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}

/* ---- tree (Stories) */
.tree{padding:4px 0;overflow:auto;flex:1}
.grp{display:flex;align-items:center;gap:6px;height:24px;padding:0 8px 0 10px;color:var(--text);font-weight:600}
.grp .ic{color:var(--muted)} .grp .n{margin-left:auto;font-weight:400;font-variant-numeric:tabular-nums;opacity:.75}
.ph-todo{color:var(--ph-todo)} .ph-plan{color:var(--ph-plan)} .ph-impl{color:var(--ph-impl)} .ph-done{color:var(--ph-done)} .ph-off{color:var(--ph-off)}
.row{display:flex;align-items:center;gap:8px;height:24px;padding:0 10px 0 30px;white-space:nowrap;color:var(--text)}
.row:hover{background:var(--hover)}
.row.sel{background:var(--sel)}
.row .k{font:12px var(--mono);color:var(--muted);width:44px;flex:none}
.row.sel .k{color:#B7C9F2}
.row .t{flex:1;overflow:hidden;text-overflow:ellipsis;min-width:0}
.row.you .t{font-weight:500}
.row.mutedrow .t,.row.mutedrow .k{color:var(--muted)}
.row .fl{font-size:11px;color:var(--amber);flex:none}
.row .fl.m{color:var(--dim)}
.row .ld{width:7px;height:7px;border-radius:50%;background:var(--accent);flex:none;animation:pulse 1.4s ease-in-out infinite}

/* ---- story page (editor) */
.story{flex:1;overflow:auto;min-height:0}
.story-in{max-width:820px;padding:20px 28px 40px 28px}
.sh-title{display:flex;align-items:baseline;gap:12px}
.sh-title .k{font:500 14px var(--mono);color:var(--muted)}
.sh-title h1{font:600 20px/1.25 var(--ui);color:var(--text);flex:1}
.sh-title .a{color:var(--dim)}
.sh-state{margin-top:8px;display:flex;align-items:center;gap:10px;color:var(--muted)}
.sh-state .ph{font-weight:500}
.sh-state .turn{display:inline-flex;align-items:center;gap:6px;color:var(--amber);font-weight:500}
.turn .ball{width:10px;height:10px;border-radius:50%;background:conic-gradient(var(--amber) 0 50%,transparent 50% 100%);border:1.5px solid var(--amber)}
.envs{margin-top:10px;display:flex;flex-direction:column;gap:3px}
.env{display:flex;align-items:center;gap:8px;height:22px;font-size:12px;color:var(--muted);min-width:0}
.env .ic{color:var(--dim)}
.env .repo{font:500 12px var(--mono);color:var(--text)}
.env .br{font:12px var(--mono);color:var(--text)}
.env .into{color:var(--muted)} .env .into b{font:12px var(--mono);font-weight:400;color:var(--muted)}
.env .path{margin-left:auto;font:11px var(--mono);color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:300px}
.chip.red{background:var(--red-dim);color:var(--red);white-space:nowrap;flex:none}
.actions{margin-top:12px;display:flex;align-items:center;gap:8px;padding:10px 12px;border:1px solid var(--border);border-left:3px solid var(--amber);border-radius:6px;background:var(--panel)}
.actions .why{color:var(--muted);margin-right:auto}
.btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 12px;border-radius:4px;border:1px solid var(--btn-border);color:var(--text);background:transparent;font:500 13px var(--ui);white-space:nowrap}
.btn:hover{border-color:#7a7d84}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{background:var(--accent-hi)}
.btn.quiet{border-color:transparent;color:var(--muted)}
.btn.sm{height:24px;padding:0 9px;font-size:12px}
.btn.opt{border-color:var(--btn-border)}
.btn.opt.picked{border-color:var(--green);color:var(--green)}
.btn:disabled,.btn.dis{opacity:.45}

/* ---- threads as a script */
.thread{margin-top:22px;border-top:1px solid var(--border);padding-top:10px}
.th-head{display:flex;align-items:center;gap:8px;height:24px;color:var(--muted);font-size:12px}
.th-head .ic{color:var(--dim)}
.th-head .n{font:12px var(--mono)}
.th-head .t{color:var(--text);font-weight:500}
.th-head .w{margin-left:auto;font-size:11px}
.th-head .w.you{color:var(--amber)}
.th-head .w.cast{color:var(--dim)}
.script{padding:4px 0 0 26px;max-width:640px}
.line{margin-top:14px}
.speaker{display:flex;align-items:baseline;gap:10px;font:500 11px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.speaker .who{color:#B4B8C0}
.speaker.you .who{color:var(--text)}
.speaker .at{font-weight:400;letter-spacing:0;text-transform:none;font-family:var(--ui);color:var(--dim);margin-left:auto}
.said{margin-top:4px;line-height:1.5;color:var(--text)}
.said p+p{margin-top:6px}
.said ul{padding-left:18px;margin-top:4px} .said li{margin-top:2px}
.said code{font:12px var(--mono);background:rgba(255,255,255,.06);padding:1px 4px;border-radius:3px}
.stage{margin-top:12px;font-style:italic;color:var(--muted);font-size:12.5px}
.yield{margin-top:12px;display:flex;align-items:center;gap:10px;font:500 12px var(--ui)}
.yield::before,.yield::after{content:"";height:1px;background:var(--border);flex:1}
.yield::after{flex:5}
.yield.pending{color:var(--amber)} .yield.pending::before,.yield.pending::after{background:rgba(214,174,88,.35)}
.yield.settled{color:var(--green)} .yield.settled::before,.yield.settled::after{background:rgba(95,173,101,.3)}
.yield.question{color:var(--muted)}
.opts{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}
.reply{margin-top:10px;padding-left:14px;border-left:2px solid var(--border)}
.checks{margin-top:10px;border:1px solid var(--border);border-radius:6px;overflow:hidden;font:12px var(--mono)}
.checks .ch{display:flex;align-items:center;gap:8px;height:26px;padding:0 10px;background:var(--panel);color:var(--text)}
.checks .ch .ic.ok{color:var(--green)} .checks .ch .ic.bad{color:var(--red)}
.checks .ch .r{margin-left:auto;color:var(--muted)}
.checks .ch + .ch{border-top:1px solid var(--border)}
.checks .ch:hover{background:var(--hover)}
.checks .ch .ic.chev{color:var(--dim);margin-right:-2px}
.checks pre{padding:8px 12px;color:var(--muted);background:var(--bg);white-space:pre-wrap;border-top:1px solid var(--border);font:11.5px/1.5 var(--mono)}
.checks pre b{color:var(--red);font-weight:500}
.composer{margin-top:14px;display:flex;gap:8px;align-items:flex-end}
.composer .box{flex:1;min-height:56px;border:1px solid var(--border);border-radius:6px;background:var(--bg);padding:7px 10px;color:var(--dim);display:flex;flex-direction:column;justify-content:space-between}
.composer .box.focus>span:not(.lbl){color:var(--text)}
.composer .box .lbl{font:500 11px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.composer .box.focus{border-color:var(--accent);box-shadow:0 0 0 2px rgba(53,116,240,.25)}
.composer .box .cur{display:inline-block;width:1px;height:14px;background:var(--text);vertical-align:-2px;margin-left:1px}
.composer .hint{font-size:11px;color:var(--dim)}
/* aside: floating on a comment, top-right. .ghost = hover affordance, .has = an aside exists, .off = disabled */
.line{position:relative}
.aside-btn{position:absolute;top:-4px;right:-36px;display:inline-flex;align-items:center;gap:5px;height:22px;padding:0 8px;border-radius:11px;font:500 11px var(--ui);color:var(--muted);border:1px solid var(--border);background:var(--bg)}
.aside-btn:hover{color:var(--text);border-color:var(--btn-border)}
.aside-btn.has{color:var(--text);background:var(--panel)}
.aside-btn.off{opacity:.4}
.folded{display:flex;align-items:center;gap:8px;height:28px;color:var(--muted);font-size:12px;margin-top:6px;padding:0 4px;border-radius:4px}
.folded:hover{background:var(--panel)}
.folded .n{font:12px var(--mono)} .folded .t{color:var(--text)} .folded .w{margin-left:auto;font-size:11px}
.folded .w.you{color:var(--amber)} .folded .w.res{color:var(--dim)} .folded .acts{display:flex;gap:4px;margin-left:8px}
.newthread{margin-top:28px;padding-top:14px;border-top:1px solid var(--border)}

/* ---- cast tool window */
.cast{padding:4px 0;flex:1;overflow:auto}
.member{padding:8px 12px 8px 12px;display:grid;grid-template-columns:16px 1fr auto;column-gap:8px;row-gap:3px;align-items:center}
.member:hover{background:var(--hover)}
.member .st{width:10px;height:10px;border-radius:50%;justify-self:center}
.st.live{background:var(--accent);animation:pulse 1.4s ease-in-out infinite}
.st.asks{background:conic-gradient(var(--amber) 0 50%,transparent 50% 100%);border:1.5px solid var(--amber)}
.st.idle{border:1.5px solid var(--dim)}
.member .nm{font-weight:500}
.member .nm .role{color:var(--muted);font-weight:400;margin-left:6px}
.member .what{font-size:11px}
.member .what.you{color:var(--amber)} .member .what.m{color:var(--muted)}
.member .meta{display:flex;align-items:center;gap:10px;font-size:11px;color:var(--dim);white-space:nowrap;overflow:hidden;min-width:0}
.member .meta .ic{color:var(--dim);margin-right:-6px}
.member .vitals{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--dim);white-space:nowrap;overflow:hidden;min-width:0;margin-top:1px;font-variant-numeric:tabular-nums}
.member .vitals.due{color:var(--amber)}
.meter{position:relative;flex:none;width:72px;height:4px;border-radius:2px;background:var(--border);display:inline-block;vertical-align:middle}
.meter i{display:block;height:100%;border-radius:2px;background:var(--muted)} .meter i.hot{background:var(--amber)}
.meter b{position:absolute;left:60%;top:-2px;width:1px;height:8px;background:var(--text);opacity:.55}
.member .what,.member .meta,.member .vitals{grid-column:2/span 2}
.member .btn{grid-column:3;grid-row:1;align-self:start}
.member.retired{opacity:.55}
.cv-head .meter{width:72px}
.cv-head .due{color:var(--amber)}
.sect{display:flex;align-items:center;gap:6px;height:24px;padding:0 12px;margin-top:6px;color:var(--muted);font-weight:600;font-size:12px}
.sect .ic{color:var(--dim)}
.substory{display:flex;align-items:center;gap:8px;height:24px;padding:0 12px 0 30px}
.substory:hover{background:var(--hover)}
.substory .k{font:12px var(--mono);color:var(--muted)} .substory .t{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.substory .ph{font-size:11px}

/* ---- contexts tool window (services) */
.ctx-body{flex:1;display:flex;min-height:0}
.ctx-tree{width:320px;border-right:1px solid var(--border);overflow:auto;padding:4px 0;flex:none}
.ctx-tree .row{padding-left:10px}
.ctx-tree .row.l1{padding-left:28px} .ctx-tree .row.l2{padding-left:46px}
.ctx-tree .row .ic{color:var(--dim)}
.ctx-tree .row .t.dim{color:var(--muted);font-style:italic}
.ctx-tree .row .st{width:8px;height:8px;border-radius:50%;flex:none}
.ctx-tree .row .m{font-size:11px;color:var(--dim);margin-left:auto}
.ctx-view{flex:1;display:flex;flex-direction:column;min-width:0;background:var(--bg)}
.cv-head{height:32px;display:flex;align-items:center;gap:10px;padding:0 12px;border-bottom:1px solid var(--border);background:var(--panel);font-size:12px;color:var(--muted);flex:none}
.cv-head .nm{color:var(--text);font-weight:600}
.cv-head .sp{flex:1}
.cv-head .a{color:var(--dim)}
.cv-scroll{flex:1;overflow:auto;padding:8px 14px}
.pred{display:flex;align-items:center;gap:8px;height:26px;padding:0 8px;border:1px dashed var(--border);border-radius:4px;color:var(--muted);font-size:12px;margin-bottom:6px}
.pred .ic{color:var(--dim)}
.ev{margin-top:8px;font-size:12.5px;line-height:1.45}
.ev .kind{font:500 11px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:6px}
.ev .kind .ic{color:var(--dim)}
.ev.think .body{color:var(--muted);font-style:italic}
.ev.tool .body{margin-top:3px;border:1px solid var(--border);border-radius:4px;background:var(--panel);padding:5px 8px;font:12px var(--mono);color:var(--text)}
.ev.tool .body.res{color:var(--muted);background:var(--bg)}
.ev.text .body{color:var(--text);margin-top:2px}
.cv-input{border-top:1px solid var(--border);padding:8px 12px;display:flex;gap:8px;align-items:center;background:var(--panel);flex:none}
.cv-input .box{flex:1;height:30px;border:1px solid var(--border);border-radius:4px;background:var(--bg);padding:0 10px;color:var(--dim);display:flex;align-items:center;gap:8px;font-size:12.5px}
.cv-input .box .lbl{font:500 11px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.cursor-blink{display:inline-block;width:8px;height:13px;background:var(--accent);opacity:.7;vertical-align:-2px}

/* ---- status bar */
.status{height:26px;background:var(--panel);border-top:1px solid var(--border);display:flex;align-items:center;padding:0 10px;gap:16px;font-size:12px;color:var(--muted);flex:none}
.status .sp{flex:1}
.status .w{display:flex;align-items:center;gap:6px}
.spin{width:12px;height:12px;border-radius:50%;border:2px solid var(--border);border-top-color:var(--accent);animation:rot 1s linear infinite}
@keyframes rot{to{transform:rotate(360deg)}}

/* ---- workspace page (Settings › Project as an editor tab) */
.ws-page{flex:1;overflow:auto;min-height:0}
.ws-in{max-width:880px;padding:20px 28px 40px 28px}
.ws-title{display:flex;align-items:center;gap:12px}
.ws-title .ws-icon{width:28px;height:28px;border-radius:7px;font-size:14px}
.ws-title .nm{font:600 20px/1.25 var(--ui);color:var(--text);padding:2px 8px;margin-left:-8px;border:1px solid transparent;border-radius:4px}
.ws-title .nm:hover{border-color:var(--btn-border)}
.ws-state{margin-top:8px;display:flex;align-items:center;gap:10px;color:var(--muted)}
.ws-state .pt{font:12px var(--mono)}
.ws-state .pf{font:500 12px var(--mono);color:var(--text)}
.ws-sect{margin-top:26px;display:flex;align-items:center;gap:10px}
.ws-sect h2{font:600 14px var(--ui);color:var(--text)}
.ws-sect .n{color:var(--muted)}
.ws-sect .sp{flex:1}
.repos{margin-top:10px;border:1px solid var(--border);border-radius:6px;overflow:hidden}
.repos .hd,.repos .rp{display:grid;grid-template-columns:18px 130px 1fr 88px 150px 120px 90px;column-gap:10px;align-items:center;padding:0 12px}
.repos .hd{height:26px;background:var(--panel);color:var(--muted);font-size:11px;border-bottom:1px solid var(--border)}
.repos .rp{height:34px;color:var(--text);font-size:12.5px}
.repos .rp+.rp,.repos .rp+.wt,.repos .wt+.rp,.repos .form{border-top:1px solid var(--border)}
.repos .rp:hover{background:var(--panel)}
.repos .rp .ic{color:var(--dim)}
.repos .rp .nm{font:500 12.5px var(--mono)}
.repos .rp .mono{font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.repos .rp .none{color:var(--dim)}
.repos .rp .stt{display:flex;align-items:center;gap:6px;justify-self:end;font-size:11px;color:var(--muted)}
.repos .rp .stt .d{width:7px;height:7px;border-radius:50%;background:var(--green)}
.repos .rp .stt.bad{color:var(--red)} .repos .rp .stt.bad .d{background:var(--red)}
.repos .rp .acts{display:flex;gap:4px;justify-self:end}
.repos .wt{display:flex;align-items:center;gap:8px;height:26px;padding:0 12px 0 40px;font-size:11px;color:var(--dim);background:var(--bg)}
.repos .wt .k{font:11px var(--mono);color:var(--muted)}
.repos .wt .k:hover{color:var(--text)}
.repos .miss{display:flex;align-items:center;gap:8px;padding:8px 12px 10px 40px;font-size:12px;color:var(--muted);background:var(--bg)}
.repos .miss .lbl{color:var(--red)}
.repos .miss .fld{flex:1;height:28px;border:1px solid var(--accent);box-shadow:0 0 0 2px rgba(53,116,240,.25);border-radius:4px;background:var(--bg);display:flex;align-items:center;padding:0 8px;font:12px var(--mono);color:var(--text)}
.repos .form{padding:10px 12px;background:var(--bg);display:flex;flex-direction:column;gap:8px}
.repos .form .r{display:flex;gap:8px;align-items:center}
.repos .form .fld{height:28px;border:1px solid var(--btn-border);border-radius:4px;background:var(--bg);display:flex;align-items:center;padding:0 8px;font-size:12.5px;color:var(--dim);gap:6px}
.repos .form .fld.wide{flex:1} .repos .form .fld.sm{width:160px}
.repos .form .fld b{font-weight:500;color:var(--muted);font-size:11px}
.repos .form .hint{font-size:11px;color:var(--dim)}

/* ---- welcome */
.welcome{display:flex;width:100%;height:100%;background:var(--bg)}
.w-nav{width:220px;background:var(--panel);border-right:1px solid var(--border);padding:22px 12px;display:flex;flex-direction:column;gap:2px}
.w-brand{display:flex;align-items:center;gap:10px;padding:0 8px 22px 8px}
.w-brand .ws-icon{width:28px;height:28px;border-radius:7px;font-size:14px}
.w-brand b{font-size:15px;font-weight:600} .w-brand span{color:var(--muted);font-size:11px;display:block}
.w-item{display:flex;align-items:center;gap:8px;height:28px;padding:0 10px;border-radius:4px;color:var(--text)}
.w-item .ic{color:var(--muted)} .w-item.on{background:var(--sel)}
.w-main{flex:1;padding:22px 26px;display:flex;flex-direction:column;min-width:0}
.w-top{display:flex;align-items:center;gap:8px}
.w-search{flex:1;height:28px;border:1px solid var(--border);border-radius:4px;background:var(--panel);display:flex;align-items:center;gap:8px;padding:0 10px;color:var(--dim)}
.w-list{margin-top:14px;display:flex;flex-direction:column;gap:2px}
.w-row{display:grid;grid-template-columns:32px 1fr auto;column-gap:12px;align-items:center;padding:8px 10px;border-radius:6px}
.w-row:hover{background:var(--panel)}
.w-row .ws-icon{width:32px;height:32px;border-radius:8px;font-size:15px}
.w-row .nm{font-weight:500;display:flex;align-items:center;gap:8px}
.w-row .nm .ic{color:var(--dim)}
.w-row .pt{font:12px var(--mono);color:var(--muted);margin-top:2px}
.w-row .rt{text-align:right;font-size:11px;color:var(--dim)}
.w-row .rt b{display:block;font:500 12px var(--mono);color:var(--muted)}
.w-row .rt .chip{margin-top:3px}
"""

FIT_JS = """<script>
(function(){var W=%d,H=%d;function fit(){var f=document.querySelector('.frame');var s=Math.min(innerWidth/W,innerHeight/H);
f.style.width=W+'px';f.style.height=H+'px';f.style.transform='scale('+s+')';f.style.left=Math.max(0,(innerWidth-W*s)/2)+'px';f.style.top=Math.max(0,(innerHeight-H*s)/2)+'px';}
addEventListener('resize',fit);fit();})();</script>"""

def page(title, body, w=None, h=None, extra_css=""):
    js = FIT_JS % (w, h) if w else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>{CSS}{extra_css}</style></head><body>{body}{js}</body></html>"""

# ---------------------------------------------------------------- shared shell pieces
def toolbar():
    return f"""
<div class="toolbar">
  <div class="tb-widget"><div class="ws-icon">Z</div><b>zharn</b>{ic('down',14)}</div>
  <div class="tb-sep"></div>
  <div class="tb-widget" style="color:var(--muted)">{ic('git',14)}<span>3 repos</span>{ic('down',14)}</div>
  <div class="tb-spacer"></div>
  <div class="run-widget"><div class="go">{ic('play',14)}<span>New story</span></div><div class="dd">{ic('down',14)}</div></div>
  <div class="tb-btn">{ic('search')}</div>
  <div class="tb-btn">{ic('settings')}</div>
</div>"""

def strip_left(active):
    def b(name, icon, badge="", dot=False):
        on = " on" if name == active else ""
        extra = f'<span class="badge">{badge}</span>' if badge else ('<span class="dot"></span>' if dot else "")
        return f'<div class="sbtn{on}" title="{name}">{ic(icon, 20)}{extra}</div>'
    return f"""
<div class="strip left">
  {b('Stories','stories','2')}{b('Files','files')}{b('Git','git')}
  <div class="gap"></div>
  {b('Contexts','contexts',dot=True)}{b('Terminal','terminal')}
</div>"""

def strip_right(active):
    on = " on" if active == "Cast" else ""
    return f'<div class="strip right"><div class="sbtn{on}" title="Cast">{ic("cast",20)}</div></div>'

def stories_tree(selected="ZH-12"):
    def row(k, t, fl="", cls="", live=False):
        sel = " sel" if k == selected else ""
        flh = f'<span class="fl{" m" if "mutedrow" in cls.split() else ""}">{fl}</span>' if fl else ""
        ld = '<span class="ld"></span>' if live else ""
        return f'<div class="row{sel} {cls}"><span class="k">{k}</span><span class="t">{t}</span>{ld}{flh}</div>'
    def grp(name, n, open_=True, ph="todo"):
        return f'<div class="grp ph-{ph}">{ic("down" if open_ else "right",14)}{name}<span class="n">{n}</span></div>'
    return f"""
<div class="toolwin left">
  <div class="tw-head"><span class="t">Stories</span><span class="chip amber">2 need you</span><span class="sp"></span>
    <span class="a">{ic('plus')}</span><span class="a">{ic('more')}</span><span class="a">{ic('minus')}</span></div>
  <div class="tree">
    {grp('Planning', 2, ph='plan')}
    {row('ZH-9','Workspace spec: worked examples','question','you')}
    {row('ZH-14','Git status panel','',live=True)}
    {grp('Implementing', 4, ph='impl')}
    {row('ZH-12','Terminal panel on pyte','ready for review','you')}
    {row('ZH-11','Context meter in the cast panel','',live=True)}
    {row('ZH-15','Extract pyte screen model','sub-story · Protagonist','mutedrow')}
    {row('ZH-7','Recast ladder, rungs 1–3','',live=True)}
    {grp('Todo', 3, ph='todo')}
    {row('ZH-16','Files panel: tree over the workspace')}
    {row('ZH-17','Option buttons on question yields')}
    {row('ZH-18','Move story to workspace')}
    {grp('Backlog', 6, False, ph='todo')}
    {grp('Done', 14, False, ph='done')}
  </div>
</div>"""

def meter(tokens, hot=False, max_=500):
    """The runway: the bar ends at the recast line (500K on a 1M window), the tick is the recap line (300K)."""
    pct = min(100, round(100 * tokens / max_))
    return f'<span class="meter"><i{" class=hot" if hot else ""} style="width:{pct}%"></i><b></b></span>'

def member(st, name, role, what, meta, tokens, turns, cost, due=False, maxed=False, retired=False, what_cls="m"):
    parts = [f"{tokens}K" if tokens else "", "recap due" if due else "", "recast at turn end" if maxed else "",
             f"{turns} turn{'' if turns == 1 else 's'}", f"${cost:.2f}"]
    line = " · ".join(p for p in parts if p)
    return f"""
    <div class="member{" retired" if retired else ""}"><span class="st {st}"></span><span class="nm">{name}<span class="role">{role}</span></span>
      {'' if retired else '<span class="btn sm quiet">Recast</span>'}
      <span class="what {what_cls}">{what}</span>
      <span class="meta">{meta}</span>
      <span class="vitals{" due" if due else ""}">{meter(tokens, due)}{line}</span></div>"""

def cast_members():
    return (member("asks", "Protagonist", "opus", "waits on you · ready for review", "inbox 1 · owes #1 · in zharn", 312, 41, 0.61, due=True, what_cls="you")
          + member("live", "Implementor", "sonnet", "working on #3", "inbox 0 · in zharn", 503, 88, 1.12, maxed=True)
          + member("idle", "Reviewer", "sonnet", "waiting · awaits #5", "inbox 0 · in pywinpty-shim", 96, 9, 0.09)
          + member("idle", "Implementor-2", "sonnet · forked from Implementor", "idle", "inbox 0", 184, 2, 0.03))

def cast_toolwin():
    return f"""
<div class="toolwin right">
  <div class="tw-head"><span class="t">Cast</span><span class="sub">· ZH-12</span><span class="sp"></span>
    <span class="a">{ic('more')}</span><span class="a">{ic('minus')}</span></div>
  <div class="cast">
    {cast_members()}
    <div class="sect">{ic('story',14)}Sub-stories</div>
    <div class="substory"><span class="k">ZH-15</span><span class="t">Extract pyte screen model</span><span class="ph ph-impl">implementing · cast</span></div>
  </div>
</div>"""

def cast_closeup():
    """The cast tool window at 1:1: the ZH-12 scene, then one row per state of the meter, captioned."""
    states = [("no reading yet", member("idle", "Protagonist", "opus", "idle · attending #1", "inbox 0 · in zharn", 0, 0, 0.00)),
              ("first call", member("live", "Protagonist", "opus", "working on #1", "inbox 0 · in zharn", 22, 1, 0.01)),
              ("well inside", member("live", "Protagonist", "opus", "working on #1", "inbox 0 · in zharn", 184, 23, 0.28)),
              ("past the recap line, recap due", member("live", "Protagonist", "opus", "working on #1", "inbox 0 · owes #1 · in zharn", 312, 41, 0.61, due=True)),
              ("past the recap line, recap posted", member("idle", "Protagonist", "opus", "waiting · awaits #3", "inbox 0 · in zharn", 348, 44, 0.66)),
              ("past the recast line, recap due", member("live", "Protagonist", "opus", "working on #1", "inbox 0 · owes #1 · in zharn", 503, 88, 1.12, due=True, maxed=True)),
              ("past the recast line, recap posted", member("live", "Protagonist", "opus", "working on #1", "inbox 0 · in zharn", 503, 88, 1.12, maxed=True)),
              ("retired", member("idle", "Protagonist", "opus", "retired", "inbox 0", 214, 61, 0.80, retired=True))]
    rows = "".join(f'<div class="state"><div class="toolwin right">{m}</div><div class="cap">{c}</div></div>' for c, m in states)
    body = f"""<div class="frame" style="position:static;transform:none;width:100%;min-height:100%;box-shadow:none;background:#131417">
      <div class="closeup-grid">
        <div class="toolwin right">{cast_toolwin().split('<div class="toolwin right">',1)[1]}
        <div class="states">{rows}</div>
      </div></div>"""
    css = """html,body{overflow:auto} .closeup-grid{display:flex;gap:28px;padding:24px;align-items:flex-start}
    .closeup-grid .toolwin{border:1px solid var(--border);height:auto;padding:2px 0} .states{display:flex;flex-direction:column;gap:10px}
    .state{display:flex;gap:14px;align-items:center} .cap{font-size:12px;color:var(--muted)}"""
    return page("zharn — cast panel, 1:1", body, extra_css=css)

def editor_tabs(active="ZH-12", workspace=False):
    def tab(icon, label, key, live=False, closable=True):
        on = " on" if key == active else ""
        return (f'<div class="tab{on}">{ic(icon,14)}<span>{label}</span>'
                f'{"<span class=live></span>" if live else ""}'
                f'{f"<span class=cl>{ic(chr(99)+chr(108)+chr(111)+chr(115)+chr(101),12)}</span>" if closable else ""}</div>')
    return f"""
<div class="tabs">
  {tab('home','Welcome','welcome')}
  {tab('folder-open','Workspace','workspace') if workspace else ''}
  {tab('story','ZH-12  Terminal panel on pyte','ZH-12', live=True)}
  {tab('story','ZH-9  Workspace spec','ZH-9')}
  {tab('context','Protagonist · ZH-12','ctx')}
  <span class="sp"></span><span class="a">{ic('splitv')}</span><span class="a">{ic('splith')}</span>
</div>"""

def story_page(compact=False):
    """The ZH-12 story page. compact=False renders the whole thread history for the 1:1 close-up."""
    return f"""
<div class="story"><div class="story-in">
  <div class="sh-title"><span class="k">ZH-12</span><h1>Terminal panel on pyte</h1><span class="a">{ic('more')}</span></div>
  <div class="sh-state"><span class="ph ph-impl">Implementing</span><span>·</span>
    <span class="turn"><span class="ball"></span>your turn — ready for review</span>
    <span>·</span><span>3 threads</span><span>·</span><span>cast of 3</span></div>
  <div class="envs">
    <div class="env">{ic('git',14)}<span class="repo">zharn</span><span class="br">zharn/ZH-12</span><span class="into">into <b>main</b></span><span class="path">.zharn/local/worktrees/zharn/ZH-12</span></div>
    <div class="env">{ic('git',14)}<span class="repo">pywinpty-shim</span><span class="br">zharn/ZH-12</span><span class="into">into <b>main</b></span><span class="path">.zharn/local/worktrees/pywinpty-shim/ZH-12</span></div>
  </div>
  <div class="actions"><span class="why">Protagonist handed off. Approve, reply with changes, or send it back to planning.</span>
    <span class="chip red">1 check failing</span>
    <span class="btn primary">Approve</span><span class="btn">Reply</span><span class="btn">Back to planning</span><span class="btn quiet">Cancel</span></div>

  <div class="thread">
    <div class="th-head">{ic('down',14)}<span class="n">#1</span><span class="t">Main thread</span><span>You → Protagonist</span><span class="w you">waits on you</span></div>
    <div class="script">
      <div class="line"><div class="speaker you"><span class="who">You</span><span class="at">yesterday 22:14</span></div>
        <div class="said"><p>Let's get the terminal panel in on top of <code>pyte</code>. Windows has to work — no qtermwidget. Keep it reloadable.</p></div></div>
      <div class="stage">(Started · Protagonist cast from <i>claude-deep</i>)</div>

      <div class="line"><div class="speaker"><span class="who">Protagonist</span>· opus<span class="at">22:16</span></div>
        <span class="aside-btn has" title="Reopen the aside on this comment">{ic('aside',13)}aside</span>
        <div class="said"><p>This needs an outline — the screen model, the QML view, and the PTY driver are three separable pieces and the PTY story differs per OS. One question before I write it:</p></div>
        <div class="yield question">Question</div>
        <div class="said"><p>Should a terminal be scoped to an <b>environment</b> (one shell per worktree, shared by the cast) or to a <b>context</b> (each character gets its own)?</p></div>
        <div class="opts"><span class="btn sm opt picked">{ic('check',12)}Per environment</span><span class="btn sm opt dis">Per context</span><span class="btn sm opt dis">Both, environment default</span></div></div>
      <div class="reply"><div class="line" style="margin-top:8px"><div class="speaker you"><span class="who">You</span><span class="at">22:31</span></div>
        <div class="said"><p>Per environment. A character can always open a second one.</p></div></div></div>

      <div class="line"><div class="speaker"><span class="who">Protagonist</span>· opus<span class="at">22:58</span></div>
        <div class="yield settled">Handoff · outline</div>
        <div class="said"><p>Outline: (1) <code>harness/term.py</code> — pyte <code>Screen</code> + <code>ByteStream</code> behind a QObject, exposes a row model; (2) <code>qml/content/Terminal.qml</code> — <code>ListView</code> of rows, monospace cells, selection later; (3) PTY: <code>pty.fork</code> on POSIX, ConPTY via <code>pywinpty</code> on Windows, chosen at import. Sub-story for (1) so the screen model gets its own tests.</p></div></div>
      <div class="stage">(Outline approved — Proceed by you, 23:05 · implementing)</div>
      <div class="stage">(Protagonist called in Implementor · sonnet on #3 · created sub-story ZH-15)</div>

      <div class="line"><div class="speaker"><span class="who">Protagonist</span>· opus<span class="at">today 09:42</span></div>
        <span class="aside-btn ghost" title="Aside: ask a private copy of Protagonist about this comment">{ic('aside',13)}</span>
        <div class="yield pending">Handoff · ready for review</div>
        <div class="said">
          <p><b>What changed.</b> <code>harness/term.py</code> (from ZH-15), <code>qml/content/Terminal.qml</code>, ConPTY driver behind <code>HARNESS_PTY</code>. The panel opens one shell per environment and survives QML reloads (screen state lives in Python).</p>
          <p><b>How verified.</b> 31 new unit tests on the screen model; UI test drives <code>ls</code> through the fake PTY and asserts rows. Reviewer signed off in #3 after one round of fixes.</p>
          <p><b>Look first at</b> <code>term.py::Screen.feed</code> — the resize path is the only part I am not fully happy with.</p>
        </div>
        <div class="checks">
          <div class="ch">{ic('right',14,'chev')}{ic('check',14,'ok')}<span>zharn</span><span class="mono" style="color:var(--muted)">pytest -q</span><span class="r">passed</span></div>
          <div class="ch">{ic('down',14,'chev')}{ic('x',14,'bad')}<span>pywinpty-shim</span><span class="mono" style="color:var(--muted)">npm test</span><span class="r" style="color:var(--red)">exit 1</span></div>
          <pre>FAIL  resize.spec.ts › shrinks columns without dropping the prompt
  expected 80, received <b>81</b>
  at Screen.resize (src/screen.ts:118)</pre>
        </div></div>

      <div class="composer"><div class="box focus"><span class="lbl">Reply to Protagonist</span><span>The resize failure is real — fix that before I look further.<span class="cur"></span></span></div><span class="btn primary">Send</span></div>
    </div>
  </div>

  <div class="thread" style="padding-top:6px">
    <div class="folded">{ic('right',14)}<span class="n">#2</span><span class="t">why pyte and not a real PTY lib?</span><span>You → Protagonist · 2 comments</span><span class="w you">answered · waits on you</span><span class="acts"><span class="btn sm quiet">Reply</span><span class="btn sm quiet">Resolve</span></span></div>
    <div class="folded">{ic('right',14)}<span class="n">#3</span><span class="t">build the terminal view</span><span>Protagonist → Implementor · 7 comments</span><span class="w">Implementor's turn</span></div>
    <div class="folded">{ic('right',14)}<span class="n">#5</span><span class="t">review #3</span><span>Protagonist → Reviewer · 2 comments</span><span class="w">Reviewer's turn</span></div>
    <div class="folded">{ic('right',14)}<span class="n">#4</span><span class="t">does ConPTY need Windows 10 1809+?</span><span>You → Protagonist · 3 comments</span><span class="w res">resolved</span></div>
  </div>

  <div class="newthread"><div class="composer"><div class="box"><span class="lbl">New thread</span><span>Write to the Protagonist, @Name, /call &lt;role&gt;, or /fork @Name for a copy of their memory</span></div><span class="btn">Open</span></div></div>
</div></div>"""

def workspace_page():
    """The workspace page: Settings › Project as an editor tab — name, prefix, repos with status + Relocate/Unregister."""
    return f"""
<div class="ws-page"><div class="ws-in">
  <div class="ws-title"><div class="ws-icon">Z</div><span class="nm">zharn</span></div>
  <div class="ws-state"><span class="pt">~/code/zharn</span><span>·</span><span>keys <span class="pf">ZH-</span></span><span>·</span><span>14 stories</span><span>·</span><span>3 repos</span></div>

  <div class="ws-sect"><h2>Repos</h2><span class="sp"></span></div>
  <div class="repos">
    <div class="hd"><span></span><span>Name</span><span>Path</span><span>Base</span><span>Checks</span><span>Setup</span><span></span></div>

    <div class="rp" style="background:var(--panel)">{ic('git',14)}<span class="nm">zharn</span><span class="mono">.</span><span class="mono">main</span><span class="mono">pytest -q</span><span class="none">—</span>
      <span class="acts"><span class="btn sm quiet">Unregister</span></span></div>
    <div class="wt">3 worktrees ·<span class="k">ZH-12</span><span class="k">ZH-14</span><span class="k">ZH-15</span></div>

    <div class="rp">{ic('git',14)}<span class="nm">pywinpty-shim</span><span class="mono">repos/pywinpty-shim</span><span class="mono">main</span><span class="mono">npm test</span><span class="mono">npm ci</span><span></span></div>
    <div class="wt">1 worktree ·<span class="k">ZH-12</span></div>

    <div class="rp">{ic('git',14)}<span class="nm">client</span><span class="mono">/home/zach/code/client</span><span class="mono">develop</span><span class="mono">npm test</span><span class="none">—</span>
      <span class="stt bad"><span class="d"></span>missing</span></div>
    <div class="miss"><span class="lbl">Not found at that path.</span><span class="fld">/home/zach/code/client-v2<span class="cur"></span></span><span class="btn sm primary">Move here</span><span class="btn sm quiet">Cancel</span><span class="btn sm quiet">Unregister</span></div>

    <div class="form">
      <div class="r"><span class="fld wide">Path to a git repository</span><span class="btn">Register</span></div>
      <div class="r"><span class="fld sm"><b>name</b>folder name</span><span class="fld sm"><b>checks</b>none</span><span class="fld sm"><b>setup</b>none</span><span class="fld sm"><b>base</b>HEAD branch</span></div>
    </div>
  </div>
</div></div>"""

def contexts_toolwin():
    def row(level, icon, text, st="", m="", dim=False, sel=False):
        sth = f'<span class="st {st}"></span>' if st else ""
        return (f'<div class="row l{level}{" sel" if sel else ""}">{ic(icon,14) if icon else ""}{sth}'
                f'<span class="t{" dim" if dim else ""}">{text}</span><span class="m">{m}</span></div>')
    return f"""
<div class="toolwin bottom" style="height:330px">
  <div class="tw-head"><span class="t">Contexts</span><span class="sub">· 7 live</span><span class="sp"></span>
    <span class="btn sm">{ic('plus',12)}New context</span><span class="a">{ic('more')}</span><span class="a">{ic('minus')}</span></div>
  <div class="ctx-body">
    <div class="ctx-tree">
      {row(0,'down','ZH-12  Terminal panel on pyte')}
      {row(1,'down','Protagonist · opus','asks','312K · 41t · $0.61',sel=True)}
      {row(2,'','recast at 512K','','read-only',dim=True)}
      {row(2,'','recast at 498K','','read-only',dim=True)}
      {row(1,'down','Implementor · sonnet','live','503K · 88t · $1.12')}
      {row(2,'','minion: find every caller of Screen.resize','','running',dim=True)}
      {row(1,'right','Reviewer · sonnet','idle','96K · 9t · $0.09')}
      {row(1,'','aside on #1 · Protagonist','','yours',dim=True)}
      {row(0,'down','ZH-14  Git status panel')}
      {row(1,'right','Protagonist · sonnet','live','58K · 4t · $0.04')}
      {row(0,'down','Bare')}
      {row(1,'','what does ipc.py actually do','idle','31K · 3t · $0.02')}
    </div>
    <div class="ctx-view">
      <div class="cv-head"><span class="st asks" style="width:9px;height:9px;border-radius:50%;background:conic-gradient(var(--amber) 0 50%,transparent 50% 100%);border:1.5px solid var(--amber)"></span>
        <span class="nm">Protagonist</span><span>opus · idle</span><span class="sp"></span>
        {meter(312, True)}<span class="due">312K · recap due</span><span>$0.611</span><span class="a">{ic('splitv',14)}</span></div>
      <div class="cv-scroll">
        <div class="pred">{ic('right',12)}recast at 512K · 212 turns · recap posted in #1</div>
        <div class="pred">{ic('right',12)}recast at 498K · 88 turns · no recap (rung 3)</div>
        <div class="ev think"><div class="kind">thinking</div><div class="body">Both checks ran; the pywinpty shim fails on resize. That is the part I flagged. Hand off anyway with the failure attached, since the author asked for Windows first and the failure is real information.</div></div>
        <div class="ev tool"><div class="kind">{ic('terminal',12)}Bash</div><div class="body">$HARNESS_CLI story yield --handoff --body-file /tmp/handoff.md</div></div>
        <div class="ev tool"><div class="kind">result</div><div class="body res">yielded on #1 · checks attached: zharn ✓ pywinpty-shim ✗ · turn → author</div></div>
        <div class="ev text"><div class="kind">text</div><div class="body">Handed off on the main thread with the check results. Waiting on the author.<span class="cursor-blink"></span></div></div>
      </div>
      <div class="cv-input"><div class="box"><span class="lbl">Comment in #1</span><span>Typing here posts a comment in the thread Protagonist is attending</span></div><span class="btn sm">Send</span></div>
    </div>
  </div>
</div>"""

def status_bar():
    return f"""
<div class="status"><span>ready</span><span class="sp"></span>
  <span class="w"><span class="spin"></span>3 characters working</span><span class="w">$1.84 today</span><span class="w">gen 7 · watch:poll</span></div>"""

# ---------------------------------------------------------------- pages
def main_window():
    body = f"""<div class="frame"><div class="win">
  {toolbar()}
  <div class="body">
    {strip_left('Stories')}
    {stories_tree()}
    <div class="center">{editor_tabs()}{story_page()}</div>
    {cast_toolwin()}
    {strip_right('Cast')}
  </div>
  {status_bar()}
</div></div>"""
    return page("zharn — main window", body, 1440, 900)

def contexts_window():
    body = f"""<div class="frame"><div class="win">
  {toolbar()}
  <div class="body">
    {strip_left('Contexts')}
    {stories_tree()}
    <div class="center"><div class="center-split">{editor_tabs()}{story_page()}</div>{contexts_toolwin()}</div>
    {strip_right('')}
  </div>
  {status_bar()}
</div></div>"""
    return page("zharn — contexts", body, 1440, 900)

def workspace_window():
    body = f"""<div class="frame"><div class="win">
  {toolbar()}
  <div class="body">
    {strip_left('Stories')}
    {stories_tree(selected="")}
    <div class="center">{editor_tabs(active="workspace", workspace=True)}{workspace_page()}</div>
    {strip_right('')}
  </div>
  {status_bar()}
</div></div>"""
    return page("zharn — workspace page", body, 1440, 900)

def workspace_closeup():
    body = f"""<div class="frame" style="position:static;transform:none;width:100%;min-height:100%;box-shadow:none">
      <div style="max-width:940px">{workspace_page()}</div></div>"""
    return page("zharn — workspace page, 1:1", body, extra_css="html,body{overflow:auto;background:var(--bg)} .ws-page{overflow:visible}")

def closeup():
    body = f"""<div class="frame" style="position:static;transform:none;width:100%;min-height:100%;box-shadow:none">
      <div style="max-width:880px">{story_page()}</div></div>"""
    return page("zharn — story thread, 1:1", body, extra_css="html,body{overflow:auto;background:var(--bg)} .story{overflow:visible}")

def welcome():
    def row(letter, grad, name, path, prefix, when, pinned=False):
        pin = ic('pin',12) if pinned else ""
        return f"""<div class="w-row"><div class="ws-icon" style="background:{grad}">{letter}</div>
          <div><div class="nm">{name}{pin}</div><div class="pt">{path}</div></div>
          <div class="rt"><b>{prefix}</b>{when}</div></div>"""
    body = f"""<div class="frame"><div class="welcome">
  <div class="w-nav">
    <div class="w-brand"><div class="ws-icon">Z</div><div><b>zharn</b><span>0.0.1 · gen 7</span></div></div>
    <div class="w-item on">{ic('folder-open')}Workspaces</div>
    <div class="w-item">{ic('role')}Roles</div>
    <div class="w-item">{ic('settings')}Settings</div>
  </div>
  <div class="w-main">
    <div class="w-top"><div class="w-search">{ic('search',14)}Search workspaces</div><span class="btn">{ic('folder-open',14)}Open folder…</span></div>
    <div class="w-list">
      {row('S','linear-gradient(135deg,#8A8F98,#5A5D63)','Scratch','~/.local/share/zharn/scratch','SCR','pinned · 2 stories need you',True)}
      {row('Z','linear-gradient(135deg,#7C5CFF,#3574F0)','zharn','~/code/zharn','ZH','2 min ago')}
      {row('N','linear-gradient(135deg,#F0A732,#E5534B)','NecoBowl','/mnt/c/Users/zachd/Code/NecoBowlGodot','NECO','3 days ago')}
      {row('B','linear-gradient(135deg,#5FAD65,#2E7D5B)','bb-plugins','~/code/bb-plugins','BBP','Aug 22')}
    </div>
  </div>
</div></div>"""
    return page("zharn — start", body, 1000, 600)

OUT = {
    "01-main-window.html": main_window,
    "02-story-thread-1to1.html": closeup,
    "03-contexts.html": contexts_window,
    "04-start-screen.html": welcome,
    "05-workspace-page.html": workspace_window,
    "06-workspace-1to1.html": workspace_closeup,
    "07-cast-1to1.html": cast_closeup,
}
if __name__ == "__main__":
    for name, fn in OUT.items():
        (HERE / name).write_text(fn(), encoding="utf-8")
        print("wrote", name)
