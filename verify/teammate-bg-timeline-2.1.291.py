"""Print a compact timeline of a test session: lead + teammate transcripts.
usage: python3 timeline.py <project-dir>"""
import glob
import json
import os
import sys

proj = sys.argv[1]
rows = []
for f in glob.glob(os.path.join(proj, "*.jsonl")) + glob.glob(os.path.join(proj, "*/subagents/*.jsonl")):
    who = "LEAD" if "/subagents/" not in f else os.path.basename(f).split("-")[1]
    for line in open(f):
        r = json.loads(line)
        ts = r.get("timestamp", "")[11:23]
        t = r.get("type")
        if t == "queue-operation":
            c = r.get("content") or ""
            if "task-notification" in c:
                desc = c[c.find("<summary>") + 9 : c.find("</summary>")][:80] if "<summary>" in c else c[:80]
                rows.append((ts, who, f"QUEUE {r.get('operation')}: {desc}"))
            continue
        if t == "attachment":
            a = r.get("attachment", {})
            if a.get("type") == "queued_command":
                p = a.get("prompt") or ""
                s = p[p.find("<summary>") + 9 : p.find("</summary>")] if "<summary>" in p else p[:80]
                rows.append((ts, who, f"GOT queued_command: {s[:90]}"))
            continue
        m = r.get("message", {})
        c = m.get("content")
        if isinstance(c, str):
            if "task-notification" in c or "teammate-message" in c or "Another Claude" in c:
                s = c.replace("\n", " ")
                k = s.find("<summary>")
                rows.append((ts, who, f"USER-MSG: {s[k:k+110] if k >= 0 else s[:110]}"))
        elif isinstance(c, list):
            for b in c:
                if b.get("type") == "tool_use":
                    i = b["input"]
                    if b["name"] == "SendMessage":
                        rows.append((ts, who, f"SendMessage -> {i.get('to')}: {str(i.get('message'))[:90]}"))
                    elif b["name"] == "Agent":
                        rows.append((ts, who, f"Agent bg={i.get('run_in_background')} desc={i.get('description')}"))
                    elif b["name"] == "Bash" and i.get("run_in_background"):
                        rows.append((ts, who, f"Bash BG desc={i.get('description')}"))
                elif b.get("type") == "tool_result":
                    cc = b.get("content")
                    s = json.dumps(cc) if not isinstance(cc, str) else cc
                    if "Async agent launched" in s or "running in background" in s:
                        rows.append((ts, who, "  -> async launched / bg started"))
                elif b.get("type") == "text" and r.get("type") == "user":
                    s = b["text"].replace("\n", " ")
                    if "task-notification" in s or "teammate-message" in s:
                        k = s.find("<summary>")
                        rows.append((ts, who, f"USER-MSG: {s[k:k+110] if k >= 0 else s[:110]}"))
for r in sorted(rows):
    print(*r)
