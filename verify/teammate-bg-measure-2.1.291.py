"""Measure delivery for one test project dir.
usage: python3 -I measure.py <project-dir>
Prints: background task completions (from queue enqueue), when each teammate
saw them, hand-back messages and where they landed, and the lead's conversation
entries that carry child notifications (lead isolation)."""
import glob, json, os, re, sys

proj = sys.argv[1]
lead_files = glob.glob(os.path.join(proj, "*.jsonl"))
sub_files = glob.glob(os.path.join(proj, "*/subagents/*.jsonl"))

def who(f):
    if "/subagents/" not in f:
        return "LEAD"
    meta = f[:-6] + ".meta.json"
    try:
        m = json.load(open(meta))
    except Exception:
        m = {}
    return (m.get("name") or "helper:" + m.get("description", "?")) + ("" if not m.get("parentAgentId") else " (parent " + m["parentAgentId"] + ")")

def text_of(o):
    m = o.get("message") or {}
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join((b.get("text") or "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""

print("## enqueue (task finished) times")
for f in lead_files:
    for l in open(f):
        o = json.loads(l)
        if o.get("type") == "queue-operation" and o.get("operation") == "enqueue":
            c = o.get("content") or ""
            if "<task-notification>" in c:
                s = re.search(r"<summary>(.*?)</summary>", c)
                print(o["timestamp"][11:23], "ENQUEUE", s.group(1) if s else "?")
            elif "hand-back" in c:
                print(o["timestamp"][11:23], "ENQUEUE hand-back", re.search(r'from="([^"]+)"', c).group(1))

print("\n## who saw task-notifications / hand-backs in their conversation")
for f in lead_files + sub_files:
    w = who(f)
    for l in open(f):
        o = json.loads(l)
        ts = o.get("timestamp", "")[11:23]
        if o.get("type") == "attachment":
            a = o.get("attachment", {})
            if a.get("type") == "queued_command":
                p = a.get("prompt") or ""
                if "<task-notification>" in p or "hand-back" in p:
                    s = re.search(r"<summary>(.*?)</summary>", p)
                    print(ts, w, "ATTACH", s.group(1) if s else "HAND-BACK " + p[p.find("The report follows:") + 19:][:80].strip())
            continue
        if o.get("type") != "user":
            continue
        t = text_of(o)
        if "<task-notification>" in t:
            s = re.search(r"<summary>(.*?)</summary>", t)
            print(ts, w, "USER", s.group(1) if s else "?")
        elif "Subagent hand-back" in t:
            print(ts, w, "USER HAND-BACK:", t[t.find("The report follows:") + 19:][:100].replace("\n", " ").strip())
