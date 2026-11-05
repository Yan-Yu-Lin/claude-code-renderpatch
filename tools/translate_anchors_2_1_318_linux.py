"""Translate the Darwin 2.1.318 recipes into exact Linux x64 2.1.318 edits.

Both official builds are compiled from the same source, but Bun chooses
different minified identifiers and a different chunk split per platform. The
Linux builder therefore runs the unchanged Darwin recipes against the
hash-pinned Darwin graph and, in lockstep, translates every edit:

* every minified-looking identifier in the Darwin anchor (<= 4 chars, not a
  keyword/global, not a property name, not an object-literal key, not rp*)
  becomes a wildcard; repeated identifiers must bind identically and distinct
  ones distinctly; the generalized anchor must match exactly once in the whole
  current Linux graph;
* identifiers in the replacement are mapped through that binding; names the
  replacement itself declares are renamed to a private rpv_ prefix (no
  shadowing of differently-named Linux symbols); other free names are resolved
  by voting over generalized witness windows from the same Darwin chunk
  matched uniquely inside the Linux chunk (closest-to-anchor first);
* added named imports are resolved to the Linux chunk that exports the same
  definition and added as separate import declarations.

The strict editor then enforces old=1/new=0 before and old=0/new=1 after on
the Linux graph exactly as on Darwin. Ambiguity is a hard error. Every
decision is written to a reviewable JSON log.
"""

import json
import re
from collections import Counter

ROOT = "/$bunfs/root/"
GLOBALS = set(
    "break case catch class const continue debugger default delete do else export extends "
    "finally for function if import in instanceof let new of return super switch this throw "
    "try typeof var void while with yield async await null true false undefined from as get "
    "set static Set Map Date Math JSON Bun NaN URL Error Array Object Symbol".split()
)
IDENT = re.compile(r"[A-Za-z_$][\w$]*")
NUM = re.compile(r"\d[\w.]*")
CHUNK = re.compile(r"chunk-[a-z0-9]{8}\.js")


def tokens(text):
    """(token, kind): kind 'gen' (translatable identifier) or 'lit'."""
    out, i, n = [], 0, len(text)
    stack = []
    while i < n:
        ch = text[i]
        state = stack[-1] if stack else None
        if state in ('"', "'", "`"):
            if ch == "\\":
                out.append((text[i:i + 2], "lit")); i += 2; continue
            if ch == state:
                stack.pop(); out.append((ch, "lit")); i += 1; continue
            if state == "`" and text.startswith("${", i):
                stack.append("${"); out.append(("${", "lit")); i += 2; continue
            out.append((ch, "lit")); i += 1; continue
        if ch in "\"'`":
            stack.append(ch); out.append((ch, "lit")); i += 1; continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append((text[i:j], "lit")); i = j; continue
        if ch == "{":
            stack.append("{"); out.append((ch, "lit")); i += 1; continue
        if ch == "}":
            if stack and stack[-1] in ("{", "${"):
                stack.pop()
            out.append((ch, "lit")); i += 1; continue
        m = IDENT.match(text, i)
        if m:
            word = m[0]
            before = text[:i].rstrip()
            prev = before[-1:] if before else ""
            nxt = text[m.end():m.end() + 1]
            spread = before.endswith("...")
            gen = (
                len(word) <= 4
                and word not in GLOBALS
                and (prev != "." or spread)
                and not (nxt == ":" and prev in "{,")
                and not word.startswith("rp")
            )
            out.append((word, "gen" if gen else "lit"))
            i = m.end(); continue
        m = NUM.match(text, i)
        if m:
            out.append((m[0], "lit")); i = m.end(); continue
        out.append((ch, "lit")); i += 1
    return out


def generalize(text):
    rx, order = [], []
    lits, cur = [], []
    for tok, kind in tokens(text):
        if kind == "gen":
            lits.append("".join(cur)); cur = []
            if tok in order:
                rx.append(f"(?P=g{order.index(tok)})")
            else:
                order.append(tok)
                rx.append(rf"(?<![\w$])(?P<g{len(order) - 1}>[A-Za-z_$][\w$]*)(?![\w$])")
        else:
            cur.append(tok)
            rx.append(re.escape(tok))
    lits.append("".join(cur))
    lits = sorted(lits, key=len, reverse=True)
    return re.compile("".join(rx), re.S), order, lits[:3]


def find(texts, snippet, only=None, limit=2):
    compiled, names, needles = generalize(snippet)
    hits = []
    for name in ([only] if only else texts):
        body = texts[name]
        if any(n and n not in body for n in needles):
            continue
        for m in compiled.finditer(body):
            hits.append((name, m))
            if len(hits) >= limit:
                return hits, names
    return hits, names


def declared(text):
    """Identifiers the snippet binds (params, let/const/var, catch)."""
    toks = [t for t in tokens(text) if not t[0].isspace()]
    out = set()
    for i, (tok, kind) in enumerate(toks):
        if tok in ("let", "const", "var") and i + 1 < len(toks):
            j, depth = i + 1, 0
            expect = True
            while j < len(toks):
                t, k = toks[j]
                if t in "([{":
                    depth += 1
                elif t in ")]}":
                    if depth == 0:
                        break
                    depth -= 1
                elif t == ";" and depth == 0:
                    break
                elif t == "," and depth == 0:
                    expect = True; j += 1; continue
                if expect and k == "gen":
                    out.add(t)
                if expect and depth == 0 and t not in "[{":
                    expect = False
                if depth > 0 and k == "gen" and toks[i + 1][0] in "[{" and j > i and toks[j + 1][0] in ",]}" if j + 1 < len(toks) else False:
                    out.add(t)
                j += 1
        if tok == "catch" and i + 2 < len(toks) and toks[i + 1][0] == "(" and toks[i + 2][1] == "gen":
            out.add(toks[i + 2][0])
        if tok == "=>":
            if toks[i - 1][1] == "gen":
                out.add(toks[i - 1][0])
            elif toks[i - 1][0] == ")":
                j, depth = i - 2, 0
                params = []
                while j >= 0:
                    t = toks[j][0]
                    if t == ")":
                        depth += 1
                    elif t == "(":
                        if depth == 0:
                            break
                        depth -= 1
                    params.append(toks[j])
                    j -= 1
                for k2, (t, k) in enumerate(params):
                    nxt = params[k2 - 1][0] if k2 else ")"
                    if k == "gen" and nxt in (",", ")", "="):
                        out.add(t)
        if tok == "function":
            j = i + 1
            if j < len(toks) and toks[j][0] != "(":
                j += 1
            if j < len(toks) and toks[j][0] == "(":
                j += 1
                depth = 0
                while j < len(toks):
                    t, k = toks[j]
                    if t == "(":
                        depth += 1
                    elif t == ")":
                        if depth == 0:
                            break
                        depth -= 1
                    if k == "gen" and depth == 0 and toks[j - 1][0] in ("(", ","):
                        out.add(t)
                    j += 1
    return out


def import_lists(body):
    """{local_name: (exported_name, source_path)} for named imports."""
    out = {}
    for m in re.finditer(r'import\{([^}]*)\}from"([^"]+)"', body):
        for item in m[1].split(","):
            item = item.strip()
            if not item:
                continue
            exp, _, local = item.partition(" as ")
            out[(local or exp).strip()] = (exp.strip(), m[2])
    return out


def exports(body):
    names = {}
    for m in re.finditer(r"export\{([^}]*)\}", body):
        for item in m[1].split(","):
            item = item.strip()
            if item:
                local, _, exp = item.partition(" as ")
                names[(exp or local).strip()] = local.strip()
    return names


class Translator:
    def __init__(self, darwin_before, linux_result, graph_prefix_d, graph_prefix_l):
        self.d = darwin_before          # live dict: Darwin pre-edit state
        self.l = linux_result           # live dict: Linux state
        self.pd = graph_prefix_d
        self.pl = graph_prefix_l
        self.added_imports = {}         # (linux chunk, darwin local) -> linux local
        self.log = []

    # ---- symbol resolution -------------------------------------------------
    def chunk_of(self, path, prefix):
        return path[len(prefix):] if path.startswith(prefix) else path.split("/")[-1]

    def definition_linux(self, dchunk, dname):
        """Linux (chunk, local) for the top-level definition of dname in dchunk."""
        body = self.d[dchunk]
        local = exports(body).get(dname, dname)
        m = re.search(
            rf"(?:function\*?\s*{re.escape(local)}\(|(?:var|let|const|class)\s+{re.escape(local)}(?![\w$])|[,;]{re.escape(local)}=(?!=))",
            body,
        )
        if not m:
            raise ValueError(f"no definition of {local} in {dchunk}")
        pos = m.start() + m[0].index(local)
        votes = Counter()
        for width in (100, 200, 400, 800):
            lo = max(0, pos - width // 2)
            hi = min(len(body), pos + width)
            window = body[lo:hi]
            # trim partial tokens/strings at edges
            window = window[window.find(";") + 1 if window.find(";") < pos - lo else 0:]
            cut = window.rfind(";")
            if cut > 0 and cut + lo > pos:
                window = window[: cut + 1]
            try:
                hits, names = find(self.l, window)
            except re.error:
                continue
            if len(hits) == 1 and local in names:
                votes[(hits[0][0], hits[0][1][f"g{names.index(local)}"])] += 1
        if len(votes) != 1:
            raise ValueError(f"definition of {dchunk}:{local} -> {dict(votes)}")
        return next(iter(votes))

    def linux_local_for(self, lchunk, def_chunk, def_local):
        """Name usable inside lchunk for the Linux symbol def_chunk:def_local."""
        if lchunk == def_chunk:
            return def_local, None
        exp = {v: k for k, v in exports(self.l[def_chunk]).items()}.get(def_local)
        if exp is None:
            raise ValueError(f"{def_chunk}:{def_local} is not exported")
        for local, (e, src) in import_lists(self.l[lchunk]).items():
            if e == exp and self.chunk_of(src, self.pl) == def_chunk:
                return local, None
        local = exp
        if re.search(rf"(?<![\w$.]){re.escape(local)}(?![\w$])", self.l[lchunk]):
            local = f"rpi_{exp}"
        return local, f'import{{{exp}{"" if local == exp else " as " + local}}}from"{self.pl}{def_chunk}";'

    def resolve_free(self, dchunk, lchunk, ident, near):
        imports = import_lists(self.d[dchunk])
        key = (lchunk, dchunk, ident)
        if key in self.added_imports:
            return self.added_imports[key], "added-import", None
        if ident in imports:
            exp, src = imports[ident]
            schunk = self.chunk_of(src, self.pd)
            try:
                def_chunk, def_local = self.definition_linux(schunk, exp)
            except ValueError as error:
                def_chunk, why = None, str(error)
            if def_chunk is not None:
                local, stmt = self.linux_local_for(lchunk, def_chunk, def_local)
                return local, f"import {schunk}:{exp} -> {def_chunk}:{def_local}", stmt
        body = self.d[dchunk]
        # Top-level definition in the same chunk: anchor on the definition.
        if re.search(rf"(?:^|[;}}\n])(?:function\*?\s*{re.escape(ident)}\(|(?:var|let|const|class)\s+{re.escape(ident)}(?![\w$]))", body):
            try:
                def_chunk, def_local = self.definition_linux(dchunk, ident)
            except ValueError:
                def_chunk = None
            if def_chunk is not None:
                local, stmt = self.linux_local_for(lchunk, def_chunk, def_local)
                return local, f"definition {dchunk}:{ident} -> {def_chunk}:{def_local}", stmt
        # Enclosing local or shared symbol: vote over nearby witnesses.
        occ = [m.start() for m in re.finditer(rf"(?<![\w$.]){re.escape(ident)}(?![\w$])", body)]
        if near is not None:
            occ.sort(key=lambda p: abs(p - near))
        votes = Counter()
        for pos in occ[:24]:
            for width in (50, 100, 200):
                lo = body.rfind(";", max(0, pos - width), pos)
                lo = lo + 1 if lo >= 0 else max(0, pos - width)
                hi = body.find(";", pos, pos + width)
                hi = hi + 1 if hi >= 0 else min(len(body), pos + width)
                window = body[lo:hi]
                if len(window) < 20:
                    continue
                try:
                    hits, names = find(self.l, window, only=lchunk)
                except re.error:
                    continue
                if len(hits) == 1 and ident in names:
                    votes[hits[0][1][f"g{names.index(ident)}"]] += 1
                    break
            if sum(votes.values()) >= 5:
                break
        if not votes:
            raise ValueError(f"no witness for {dchunk}:{ident} in {lchunk}")
        (best, n), *rest = votes.most_common()
        # Each vote is a generalized window that matched exactly once in the
        # Linux chunk; any disagreement is fatal.
        if rest:
            raise ValueError(f"ambiguous witness for {dchunk}:{ident} in {lchunk}: {dict(votes)}")
        return best, f"witness {dict(votes)}", None

    # ---- translation ------------------------------------------------------
    def translate_text(self, text, mapping, decl, dchunk, lchunk, near, record):
        out = []
        new_imports = []
        for tok, kind in tokens(text):
            if kind != "gen":
                out.append(tok); continue
            if tok in mapping:
                out.append(mapping[tok]); continue
            if tok in decl:
                mapping[tok] = f"rpv_{tok}"
                record.append({"ident": tok, "linux": mapping[tok], "how": "declared-in-replacement"})
                out.append(mapping[tok]); continue
            linux, how, stmt = self.resolve_free(dchunk, lchunk, tok, near)
            if stmt:
                new_imports.append(stmt)
                self.added_imports[(lchunk, dchunk, tok)] = linux
            mapping[tok] = linux
            record.append({"ident": tok, "linux": linux, "how": how})
            out.append(linux)
        return "".join(out), new_imports

    def import_edit(self, dchunk, old, new, record):
        """Darwin added names to an import list; add Linux import declarations."""
        body = self.d[dchunk]
        pos = body.index(old)
        src = re.compile(r'from"([^"]+)"').search(body, pos)
        if src is None:
            raise ValueError(f"no import source for {old}")
        # The anchor must be inside one import{...}from"..." statement.
        start = body.rfind("import{", 0, pos + len("import{"))
        if start < 0 or body.find("}", start) < pos or src.start() < pos or body.find(";", start, pos) >= 0:
            raise ValueError(f"import edit anchor not inside an import list: {old}")
        schunk = self.chunk_of(src[1], self.pd)
        o, n = import_list_items(old), import_list_items(new)
        return schunk, [x for x in n if x not in o]

    def add_imports(self, dchunk, lchunk, schunk, items, record):
        stmts = []
        for item in items:
            exp, _, local = item.partition(" as ")
            exp, local = exp.strip(), (local or exp).strip()
            def_chunk, def_local = self.definition_linux(schunk, exp)
            if local.startswith("__rp"):
                lexp = {v: k for k, v in exports(self.l[def_chunk]).items()}[def_local]
                stmts.append(f'import{{{lexp} as {local}}}from"{self.pl}{def_chunk}";')
                linux_local = local
            else:
                linux_local, stmt = self.linux_local_for(lchunk, def_chunk, def_local)
                if stmt:
                    stmts.append(stmt)
            self.added_imports[(lchunk, dchunk, local)] = linux_local
            record.append({"import": item, "from": schunk, "linux_def": f"{def_chunk}:{def_local}", "linux_local": linux_local})
        return stmts


LIST = r"[\w$]+(?: as [\w$]+)?(?:,[\w$]+(?: as [\w$]+)?)*"


def import_list_items(text):
    m = re.fullmatch(rf"(?:import\{{|,)?({LIST}),?(?:\}}(?:from)?)?", text)
    return [x.strip() for x in m[1].split(",")] if m else None


def is_import_edit(old, new):
    """old/new are slices of one named-import list; new only adds names."""
    o, n = import_list_items(old), import_list_items(new)
    if o is None or n is None or "," not in old:
        return False
    return [x for x in n if x in o] == o and len(n) > len(o)


def make_wrapper(darwin_texts, linux_texts, prefix_d, prefix_l, strict_linux_edit, log):
    """Return wrap_edit for patch_graph(darwin...) mirroring edits onto Linux."""

    def wrap(edit_darwin, darwin_result):
        tr = Translator(darwin_result, linux_texts, prefix_d, prefix_l)
        anchor_chunk = {}

        def edit(name, changes, extra=""):
            # Imports carried by `extra` are hoisted ESM declarations that the
            # changes may already use: resolve and add them first.
            extra_imports = list(re.finditer(r'import\{([^}]*)\}from"\./(chunk-[a-z0-9]{8}\.js)";', extra))
            if extra_imports:
                plain = [o for o, n in changes if not is_import_edit(o, n)]
                if name in anchor_chunk:
                    lchunk0 = anchor_chunk[name]
                elif plain:
                    lchunk0 = locate_anchor(darwin_result[name], darwin_result[name].index(plain[0]),
                                            plain[0], linux_texts, None)[0]
                else:
                    lchunk0 = locate_chunk(tr, name)
                anchor_chunk.setdefault(name, lchunk0)
                record = {"darwin_chunk": name, "extra_imports": [m[0] for m in extra_imports], "decisions": []}
                stmts = []
                for m in extra_imports:
                    stmts += tr.add_imports(name, lchunk0, m[2], [x.strip() for x in m[1].split(",")], record["decisions"])
                add_import_statements(linux_texts, lchunk0, stmts)
                record.update({"linux_chunk": lchunk0, "linux_append": "".join(sorted(set(stmts)))})
                log.append(record)
            for old, new in changes:
                record = {"darwin_chunk": name, "old": old, "new": new, "decisions": []}
                before = darwin_result[name]
                near = before.index(old)
                if is_import_edit(old, new):
                    schunk, items = tr.import_edit(name, old, new, record)
                    plain = [o for o, n in changes if not is_import_edit(o, n)]
                    lchunk = anchor_chunk.get(name) or (
                        locate_anchor(before, before.index(plain[0]), plain[0], linux_texts, None)[0]
                        if plain else locate_chunk(tr, name))
                    anchor_chunk.setdefault(name, lchunk)
                    stmts = tr.add_imports(name, lchunk, schunk, items, record["decisions"])
                    edit_darwin(name, [(old, new)])
                    if stmts:
                        add_import_statements(linux_texts, lchunk, stmts)
                    record.update({"linux_chunk": lchunk, "linux_append": "".join(stmts)})
                    log.append(record)
                    continue
                lchunk, m, names, widened = locate_anchor(before, near, old, linux_texts,
                                                          anchor_chunk.get(name))
                if widened:
                    record["widened_context"] = widened
                mapping = {d: m[f"g{i}"] for i, d in enumerate(names)}
                if len(set(mapping.values())) != len(mapping):
                    raise ValueError(f"non-injective binding {mapping} for {old[:160]}")
                anchor_chunk.setdefault(name, lchunk)
                if anchor_chunk[name] != lchunk:
                    record["note"] = f"anchor in different Linux chunk than first ({anchor_chunk[name]})"
                decl = declared(new) - set(names)
                lnew, stmts = tr.translate_text(new, mapping, decl, name, lchunk, near, record["decisions"])
                edit_darwin(name, [(old, new)])
                if stmts:
                    add_import_statements(linux_texts, lchunk, stmts)
                strict_linux_edit(lchunk, [(m[0], lnew)])
                record.update({"linux_chunk": lchunk, "linux_old": m[0], "linux_new": lnew,
                               "binding": mapping, "linux_imports": sorted(set(stmts))})
                log.append(record)
            if extra:
                record = {"darwin_chunk": name, "extra": extra, "decisions": []}
                lchunk = anchor_chunk.get(name) or locate_chunk(tr, name)
                text = extra
                for m in extra_imports:
                    text = text.replace(m[0], "")
                decl = declared(text)
                ltext, more = tr.translate_text(text, {}, decl, name, lchunk, None, record["decisions"])
                edit_darwin(name, [], extra)
                if more:
                    add_import_statements(linux_texts, lchunk, more)
                strict_linux_edit(lchunk, [], ltext)
                record.update({"linux_chunk": lchunk, "linux_extra": ltext, "linux_imports": sorted(set(more))})
                log.append(record)

        return edit

    return wrap


def _norm_paths(text):
    return re.sub(r'"/@(?:darwin|linux)-graph/[^"]*"', '"/@G/"', text)


def verify_alpha_equivalence(darwin_patched, linux_patched, log, minimum=150):
    """Independent post-check of every in-place edit.

    The patched Darwin site plus surrounding context (cut at statement
    boundaries; import paths normalized because chunk names differ) is
    generalized and must match exactly once in the patched Linux chunk with an
    injective identifier binding, covering the Linux replacement. A wrongly
    mapped local or free name breaks the consistent renaming and fails here.
    Left and right context are widened independently. Returns context sizes.
    """
    widths = []
    sizes = (0, 30, 60, 120, 200, 300, 400, 600)
    for r in log:
        if "linux_new" not in r:
            continue
        dbody = _norm_paths(darwin_patched[r["darwin_chunk"]])
        lbody = _norm_paths(linux_patched[r["linux_chunk"]])
        dnew, lnew = _norm_paths(r["new"]), _norm_paths(r["linux_new"])
        dcount, lcount = dbody.count(dnew), lbody.count(lnew)
        if dcount == 0 and lcount == 0:
            # Refined by a later layer, whose own record is checked instead.
            superseded = [x for x in log if x.get("old") and r["new"] and
                          (x["old"] in r["new"] or r["new"] in x["old"] or
                           x["old"][:40] in r["new"]) and x is not r]
            if not superseded:
                raise ValueError(f"replacement vanished without a refining edit: {r['new'][:120]}")
            r["verified_context_chars"] = "superseded"
            continue
        if dcount != 1 or lcount != 1:
            raise ValueError(f"replacement not unique after patch ({dcount},{lcount}): {r['new'][:120]}")
        dpos, lpos = dbody.index(dnew), lbody.index(lnew)
        dend = dpos + len(dnew)

        def ok(left, right):
            lo, hi = max(0, dpos - left), min(len(dbody), dend + right)
            if left:
                cut = dbody.find(";", lo, dpos)
                lo = cut + 1 if cut >= 0 else lo
            if right:
                cut = dbody.rfind(";", dend, hi)
                hi = cut + 1 if cut >= 0 else hi
            try:
                hits, names = find({"x": lbody}, dbody[lo:hi], only="x")
            except re.error:
                return None
            if len(hits) != 1:
                return None
            m = hits[0][1]
            bound = [m[f"g{i}"] for i in range(len(names))]
            if len(set(bound)) != len(bound):
                return None
            if not (m.start() <= lpos and lpos + len(lnew) <= m.end()):
                return None
            return (dpos - lo) + (hi - dend)

        left = max((w for w in sizes if ok(w, 0) is not None), default=None)
        right = max((w for w in sizes if ok(0, w) is not None), default=None)
        if left is None or right is None:
            raise ValueError(f"replacement site not alpha-equivalent: {r['new'][:160]}")
        best = ok(left, right) or max(ok(left, 0), ok(0, right))
        # The replacement text itself is part of the alpha-equivalent span.
        if best + len(dnew) < minimum:
            raise ValueError(
                f"alpha-equivalence context too small ({best}) for {r['darwin_chunk']}: {r['new'][:160]}")
        r["verified_context_chars"] = best
        widths.append(best)
    return widths


def add_import_statements(texts, chunk, stmts):
    """Append import declarations (hoisted by ESM) to one Linux chunk.

    Each must bind a name that is not yet used anywhere in the chunk, and the
    exact statement must not already be present in that chunk.
    """
    for stmt in sorted(set(stmts)):
        m = re.fullmatch(r'import\{([\w$]+)(?: as ([\w$]+))?\}from"([^"]+)";', stmt)
        if not m:
            raise ValueError(f"unsupported import statement {stmt}")
        local = m[2] or m[1]
        body = texts[chunk]
        if stmt in body:
            raise ValueError(f"import already present in {chunk}: {stmt}")
        if re.search(rf"(?<![\w$.]){re.escape(local)}(?![\w$])", body):
            raise ValueError(f"import local {local} already used in {chunk}")
        texts[chunk] = body + "\n" + stmt


class _Core:
    """Match-like view of the core anchor inside a widened match."""

    def __init__(self, m):
        self._m = m

    def __getitem__(self, key):
        return self._m[0] if key == 0 else self._m[key]

    def start(self):
        return self._m.start()


def locate_anchor(dbody, near, old, linux_texts, preferred_chunk):
    """Find the unique Linux span for Darwin anchor `old`.

    First the generalized anchor alone; if it is not unique, add growing
    Darwin context on both sides (cut at statement boundaries) until the
    widened pattern matches exactly once in the Linux graph, then locate the
    core inside that match (it must occur exactly once there too).
    """
    hits, names = find(linux_texts, old)
    if len(hits) == 1:
        return hits[0][0], hits[0][1], names, None
    core_rx, core_names, _ = generalize(old)
    end = near + len(old)
    for width in (40, 80, 160, 320, 640, 1280):
        lo = max(0, near - width)
        hi = min(len(dbody), end + width)
        cut = dbody.find(";", lo, near)
        lo = cut + 1 if cut >= 0 else lo
        cut = dbody.rfind(";", end, hi)
        hi = cut + 1 if cut >= 0 else hi
        wide = dbody[lo:hi]
        try:
            whits, _ = find(linux_texts, wide)
        except re.error:
            continue
        if len(whits) != 1:
            continue
        lchunk, wm = whits[0]
        inner = list(core_rx.finditer(linux_texts[lchunk], wm.start(), wm.end()))
        if len(inner) != 1:
            continue
        return lchunk, _Core(inner[0]), core_names, {"darwin_context": wide[:400], "width": width}
    raise ValueError(f"Linux anchor matches {len(hits)} times and widening failed: {old[:200]}")


def locate_chunk(tr, dchunk):
    """Linux chunk structurally matching dchunk (by a distinctive statement)."""
    body = tr.d[dchunk]
    for m in re.finditer(r"function [\w$]+\([^)]*\)\{[^{}]{40,200}\}", body):
        try:
            hits, _ = find(tr.l, m[0])
        except re.error:
            continue
        if len(hits) == 1:
            return hits[0][0]
    raise ValueError(f"cannot locate Linux chunk for {dchunk}")
