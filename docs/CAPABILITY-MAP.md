# 功能對照（Capability map）

本頁快速對照目前 runtime API 2 的實際 method、policy 與 capture。

| Domain | Safe read | Validated actions | Raw capture | Policy | 狀態 |
|---|---|---|---|---|---|
| `mc` | `read.mc.*` | — | `d0` | `3 provider.contextWindow` | working |
| `sr` | `read.sr.*` | — | `d0` | `4 subagent.explicitModelRouting` | working；`trace` 只是 alias |
| `msg` | `read.msg.*`, `read.messages` | `actions.msg.*` | `d3` | `0 renderer.messages` | working；summary only |
| `repl` | `read.repl*` | `actions.repl.*` | `d4` | `2 renderer.toggleRedraw` | dispatch denied |
| `app` | `read.app.metadata` | `actions.app.subscribe` | `d2` | — | direct callback only |
| `ink` | `read.ink.frame` | `actions.ink.*` | `d1` | `1 renderer.reset` | working |
| `key` | `read.key.catalog` | `actions.key.*` | `d5` | — | strict allowlist |
| `diag` | `read.diag.status` | `actions.diag.log` | `d1` | — | working |
| Banner | — | — | — | — | unbridged；domain 5 非目前 API |

## 實際 method 對照

### `mc`

```text
read.mc.catalog(model, generation?)
read.mc.canonicalize(model, generation?)
read.mc.provider(model, generation?)
read.mc.windowPreview(model, generation?)
```

### `sr`

```text
read.sr.preview(requestedModel, parentModel, generation?)
read.sr.trace(requestedModel, parentModel, generation?)
```

`trace` 目前等同 `preview`。

### `msg`

```text
read.msg.counts(generation?)
read.msg.snapshot(request?)
read.messages(generation?)
actions.msg.search(request)
actions.msg.export(request)
```

### `repl`

```text
read.repl(generation?)
read.repl.state(generation?)
read.repl.catalogs(generation?)
actions.repl.redraw({generation})
actions.repl.toggle({generation})
actions.repl.showAll({generation, enabled})
actions.repl.dispatch({generation, command})
```

`repl.dispatch` 固定 `denied`。

### `app`

```text
read.app.metadata(generation?)
actions.app.subscribe({generation}, callback)
```

`app.subscribe` 必須直接呼叫，不能透過 `actions.invoke()`。

### `ink`

```text
read.ink.frame(generation?)
actions.ink.redraw({generation})
actions.ink.invalidate({generation})
actions.ink.repaint({generation})
```

### `key`

```text
read.key.catalog(generation?)
actions.key.invoke({generation, action})
actions.key.register({generation, action}, handler)
```

`key.register` 必須直接呼叫。Safe allowlist：

```text
repl.toggleTranscript
repl.showAll
ink.redraw
```

### `diag`

```text
read.diag.status(generation?)
actions.diag.log({generation, message})
```

### 跨 domain API

```text
read.status()
read.captureMetadata(domain)
read.observe(domain, callback)
actions.list()
actions.invoke(name, request)
```

詳細 signature 與 result envelope：

- [api/read.md](api/read.md)
- [api/actions.md](api/actions.md)
- [api/unsafe.md](api/unsafe.md)

Banner 未 bridge 邊界：

- [internals/BANNER-RENDERER-2.1.220.md](internals/BANNER-RENDERER-2.1.220.md)
