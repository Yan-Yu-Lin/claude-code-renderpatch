# /// script
# requires-python = ">=3.11"
# ///
import ast, sys
from pathlib import Path

src = Path("/Users/linyanyu/20-29-Development/21-Active-Projects/claude-code-renderpatch/.claude/worktrees/bridge-2.1.261/tools/source_patches_2_1_261.py").read_text()
tree = ast.parse(src)
anchors = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "edit":
        chunk = node.args[0].value
        for tup in node.args[1].elts:
            old = ast.literal_eval(tup.elts[0])
            anchors.append((chunk, old))

graph = Path(sys.argv[1])
texts = {p.name: p.read_text(errors="replace") for p in graph.glob("*.js")}
for chunk, old in anchors:
    hits = [(n, t.count(old)) for n, t in texts.items() if old in t]
    print(f"{chunk:22} {len(hits)} files {hits[:3]}  :: {old[:70]!r}")
