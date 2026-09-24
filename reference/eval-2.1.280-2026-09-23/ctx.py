# /// script
# requires-python = ">=3.11"
# ///
"""ctx.py GRAPH_DIR PATTERN [before] [after] [maxhits] -- regex context search across *.js"""
import re, sys
from pathlib import Path

g, pat = Path(sys.argv[1]), sys.argv[2]
before = int(sys.argv[3]) if len(sys.argv) > 3 else 300
after = int(sys.argv[4]) if len(sys.argv) > 4 else 300
maxhits = int(sys.argv[5]) if len(sys.argv) > 5 else 5
rx = re.compile(pat)
n = 0
for p in sorted(g.glob("*.js")):
    t = p.read_text(errors="replace")
    for m in rx.finditer(t):
        print(f"=== {p.name} @{m.start()}")
        print(t[max(0, m.start() - before): m.end() + after])
        print()
        n += 1
        if n >= maxhits:
            sys.exit()
