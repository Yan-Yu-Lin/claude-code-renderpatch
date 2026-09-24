# /// script
# requires-python = ">=3.11"
# ///
"""resolve.py GRAPH CHUNK NAME [after] -- follow chunk-local import alias to its definition and print it"""
import re, sys
from pathlib import Path

g, chunk, name = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
after = int(sys.argv[4]) if len(sys.argv) > 4 else 900
seen = set()
while (chunk, name) not in seen:
    seen.add((chunk, name))
    t = (g / chunk).read_text(errors="replace")
    m = re.search(r"(?:function\*?\s+|async function\s+)" + re.escape(name) + r"\(", t) or re.search(r"(?:[,;{\s]|^|var |let |const )" + re.escape(name) + r"=", t)
    if m:
        print(f"=== {chunk} @{m.start()} ({name})")
        print(t[m.start(): m.start() + after])
        break
    found = False
    for im in re.finditer(r'import\{([^}]*)\}from"([^"]+)"', t):
        for part in im.group(1).split(","):
            part = part.strip()
            if part == name or part.endswith(" as " + name):
                src = part.split(" as ")[0].strip()
                chunk, name = im.group(2).split("/")[-1], src
                found = True
                break
        if found:
            break
    if not found:
        print("unresolved", chunk, name)
        break
