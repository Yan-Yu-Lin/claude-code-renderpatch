# External preload runtime: findings, limits, and update boundary

This document records the external-JavaScript preload experiment for Claude Code's
Bun-compiled executable. Its purpose is to separate three questions that are easy to
conflate:

1. Can code run inside the Claude Code process before the CLI starts? **Yes.**
2. Can that code modify process-wide JavaScript surfaces? **Yes.**
3. Does same-process execution expose Claude Code's closure-bound bundled internals?
   **No.**

The distinction matters because the existing renderer and subagent-routing changes are
version-pinned byte patches. The repository explicitly warns that embedded minified byte
patterns must be semantically rediscovered after every update
([README.md lines 74–81](../README.md#L74-L81)), while an external preload can follow the
newest installed Claude candidate without changing its bytes.

## Evidence labels

This document uses two labels:

- **Tested fact** — directly observed in the 2.1.219/2.1.220 experiments described below.
- **Inferred design** — an architecture or compatibility conclusion derived from those
  observations. It is a recommendation, not a claim that the complete production design
  has already been implemented or verified.

Repository links describe the current lab implementation or the established binary-patch
workflow; they are not substitutes for the empirical labels.

## Tested versions and launch path

**Tested fact.** An external JavaScript file supplied through:

```text
BUN_OPTIONS=--preload=/absolute/path/to/preload.js
```

ran successfully in-process on both:

- the ad-hoc-signed, patched Claude Code **2.1.219** executable; and
- the stock Claude Code **2.1.220** executable.

It ran before Claude Code parsed its own command-line arguments. This was not merely a
child process writing to the same terminal: process argument mutation and shared-global
interception both affected the subsequently running CLI in the same process.

The current experimental launcher resolves the numerically newest executable in the
installed versions directory rather than naming one version
([`preload/claude-preload-lab` lines 51–78](../preload/claude-preload-lab#L51-L78)), then
sets `BUN_OPTIONS=--preload=...` immediately before `exec`-ing that target
([lines 158–169](../preload/claude-preload-lab#L158-L169)). It does not modify the selected
binary.

## Empirical results

### Preload ordering and same-process proof

**Tested fact — argument ordering.** The preload mutated `process.argv`, and Claude Code's
later CLI parsing observed the modified argument vector. Therefore the preload executes
before application argument parsing, not after CLI initialization.

This result is stronger than observing a preload message on stderr: a separate process
could print a message, but it could not mutate the parent CLI's live `process.argv` array.

**Tested fact — shared global realm.** Replacing or wrapping `console.log` in the preload
intercepted later `console.log` activity from Claude Code. The preload and application
therefore share process-wide JavaScript global objects.

This proves access to ordinary globals. It does **not** prove access to every internal
logging path: code that writes directly to stderr, uses a captured function reference, or
calls another logging abstraction can bypass a later `console.log` wrapper.

### Runtime APIs available to the preload

**Tested fact.** The external preload successfully had access to all of the following in
the compiled Claude Code process:

| Surface | Observed availability | Practical use |
|---|---|---|
| CommonJS `require` | Available | Load compatible modules and inspect `require.cache` |
| Top-level dynamic `import()` | Available | Load ESM and Node-compatible built-ins asynchronously |
| `node:fs` | Available | Read trusted configuration or extension files |
| `Bun.file` | Available | Use Bun's native file API |
| `process` | Available | Read/mutate argv, environment, executable metadata, and process streams |
| `globalThis` / `console` | Available and shared | Publish a registry and install process-wide monkeypatches |

The lab bootstrap uses dynamic imports for `node:os`, `node:path`, `node:fs/promises`, and
`node:url` ([`preload/bootstrap.mjs` lines 89–141](../preload/bootstrap.mjs#L89-L141)).
Its registry is installed under a `Symbol.for(...)` key on `globalThis`
([lines 4 and 73–87](../preload/bootstrap.mjs#L73-L87)).

### Mechanisms that did not preload code

**Tested fact — `NODE_OPTIONS --require`.** Supplying a module through
`NODE_OPTIONS=--require=...` did not preload it into Claude Code. Claude Code is a
Bun-compiled executable, so Node's startup option is not a usable injection path here.

**Tested fact — direct `claude --preload`.** Passing `--preload` directly as a Claude Code
command-line argument did not run a Bun preload. At that point the executable is already
running and the argument belongs to Claude Code's application parser; it is not being
interpreted as a Bun launcher option.

The working distinction is:

```text
BUN_OPTIONS=--preload=/abs/module.js claude ...   # observed working
claude --preload=/abs/module.js ...               # observed not working
NODE_OPTIONS=--require=/abs/module.js claude ...  # observed not working
```

### `require.cache` and the internal-access limit

**Tested fact.** The observed `require.cache` contained only three relevant entries:

1. the external preload module;
2. `bun:main`; and
3. the compiled Claude Code CLI entry.

The `bun:main` and Claude Code CLI entry exposed empty exports. There was no cache tree of
Claude Code's bundled internal modules and no exported object containing renderer,
resolver, Ink instance, React state, or other application internals.

An empty export does not mean the CLI contains no code. It means the Bun bundle executes
that code behind its generated entry and lexical/module closures without publishing a
usable CommonJS export surface. Same-process execution shares globals and runtime APIs;
it does not merge lexical scopes.

Consequently, a preload cannot directly name a minified closure binding such as a current
version's redraw helper or subagent resolver. Those identifiers are private to the
compiled bundle. The existing repatching playbook makes the same version-instability
visible from the other direction: minified names must not be reused, and the stable
semantic neighborhood must be rediscovered
([REPATCHING-PLAYBOOK.md lines 310–352](../REPATCHING-PLAYBOOK.md#L310-L352)).

### macOS dynamic-library insertion

**Tested fact.** `DYLD_INSERT_LIBRARIES` was honored only by the ad-hoc-signed patched
binary in this experiment. It was not a usable insertion path for the stock signed
executable.

**Inferred design.** DYLD insertion is not recommended as the extension architecture:

- it forfeits the main benefit of a stock, update-following launch path;
- it is macOS-specific and native-ABI-sensitive;
- it couples operation to code-signing and hardened-runtime behavior;
- it increases the failure and security surface compared with an external JavaScript
  preload; and
- it still does not automatically provide stable names for JavaScript lexical bindings.

The established byte-patch workflow already requires extracting current entitlements and
re-signing each modified binary
([REPATCHING-PLAYBOOK.md lines 418–445](../REPATCHING-PLAYBOOK.md#L418-L445)). Adding a
native injection dependency would make that workflow more fragile, not less.

## The exact update-stability boundary

**Inferred design.** The useful boundary is not simply "external JavaScript versus binary
patch." It is **runtime-reachable surfaces versus closure-bound bundle internals**.

### Usually update-stable: runtime-reachable surfaces

An external preload can operate without modifying the Claude binary when the target is
reachable through a runtime surface that exists before application initialization, for
example:

- `globalThis`, `console`, `process`, `process.argv`, or `process.env`;
- a Node/Bun runtime API available to the preload;
- a global function or object that Claude Code looks up dynamically at the point of use;
- an object deliberately published into the global registry by another trusted component;
- policy, configuration, logging, tracing, or extension dispatch implemented entirely in
  external modules.

"Update-stable" does not mean "guaranteed forever." Claude Code can stop calling a patched
global, capture a different reference, change its output path, or ship a Bun runtime that
changes preload behavior. These mechanisms normally require a compatibility test after an
update, but not a new byte patch.

Because the preload runs first, it can also affect an application reference captured
during later startup. It cannot affect a reference that the compiled runtime resolves
through an intrinsic or private lexical path which never consults the modified global.

### Version-pinned: closure-bound internals

A change remains version-pinned when it needs to access or alter:

- minified lexical bindings inside the compiled bundle;
- non-exported renderer state, functions, React setters, or Ink instances;
- internal call sites that never consult a shared global;
- control flow inside a private resolver or renderer function; or
- exact embedded JavaScript bytes.

The preload's empty `bun:main`/CLI exports and minimal `require.cache` establish that these
internals do not become reachable merely because external code runs in-process.

To reach them, a binary patch must either continue changing the internal behavior directly
or inject a small bridge at a semantically rediscovered internal site. Existing repository
patches must be equal-length because the Bun archive is offset-based
([`reference/patch-intent.md` lines 11–15](patch-intent.md#L11-L15)), and the playbook
requires unique contextual anchors rather than old offsets or minified names
([REPATCHING-PLAYBOOK.md lines 378–416](../REPATCHING-PLAYBOOK.md#L378-L416)).

### Hybrid boundary: a tiny pinned bridge with external policy

**Inferred design.** The most maintainable route to private internals is a hybrid:

1. Keep the launcher, bootstrap, registry, extension loader, policy, and most feature logic
   external.
2. If a feature truly needs a private Claude Code function, add the smallest possible
   version-pinned byte patch that publishes a narrow adapter to the registry or invokes a
   named registry hook.
3. Rediscover and repatch only that adapter after updates.
4. Keep unstable minified names and internal object shapes inside the adapter; expose a
   small, versioned, semantic interface to external code.

This does not make private internals update-stable. It confines version-specific work to a
small bridge instead of embedding all feature policy into same-length byte replacements.

## What requires repatching after an update?

In this table, **repatching** means modifying and re-signing the newly installed Claude
Code binary. A "No" still requires a smoke test.

| Mechanism or feature | Binary repatch after a normal Claude update? | Update action | Reason |
|---|---:|---|---|
| External `BUN_OPTIONS --preload` bootstrap | **No** | Resolve the new candidate and rerun ordering/global smoke tests | Verified on patched 2.1.219 and stock 2.1.220 without changing the preload |
| Launcher that selects the newest numeric installed version | **No** | Verify installation layout has not changed | Version selection is outside the executable |
| External registry and extension modules | **No** | Keep registry API compatible; update external JS if desired | They live outside Claude Code's bundle |
| `process.argv`, environment, or shared-global monkeypatches | **No**, normally | Retest that the new CLI still consults the affected surface | Runtime-reachable and installed before CLI parsing |
| Wrapping `console.log` | **No**, normally | Retest coverage; other logging paths may bypass it | Shared global interception was verified, but call-site usage can change |
| File/config access through `require`, `import()`, `node:fs`, or `Bun.file` | **No**, normally | Retest runtime API availability after major Bun packaging changes | These are preload runtime capabilities, not Claude internals |
| Existing renderer full-redraw byte patches | **Yes** | Rediscover semantic sites, reapply equal-length edits, re-sign, and run PTY/terminal verification | They alter closure-bound bundled renderer code |
| Existing explicit subagent model-routing patch | **Yes** | Rediscover from stable literals and patch only the intended call site | Its minified names and bundle layout regenerate |
| New direct patch to any private renderer/resolver/state binding | **Yes** | Re-derive against the new bundle | The binding is not exported to the preload |
| Minimal internal-to-registry bridge patch | **Yes, for the bridge only** | Rediscover the internal adapter site; keep external policy unchanged when its API remains compatible | The bridge touches version-specific internals even though its consumer is external |
| Pure external feature using only an already-stable bridge API | **No** for the feature; **possibly yes** for its bridge | Test the bridge contract and repatch only if the new binary needs a new adapter | Separates external policy from internal reachability |
| `DYLD_INSERT_LIBRARIES` native injection | **Effectively yes / not recommended** | Re-establish modified signing/injection compatibility for every target | Observed only on the ad-hoc-signed patched binary |
| `NODE_OPTIONS --require` | **Not applicable** | Do not use | It did not preload code into the Bun executable |
| Direct `claude --preload` | **Not applicable** | Do not use | Claude's CLI argument path is too late to configure Bun preload startup |

If a future Claude Code release stops honoring external `BUN_OPTIONS --preload`, that is a
runtime/packaging compatibility break, not a routine semantic repatch. Stop and redesign
the launch seam rather than silently falling back to native injection.

## Recommended architecture

The following is an **inferred design** based on the tested boundary.

### 1. Wrapper launcher

The wrapper should:

1. Resolve an explicit override or the newest numeric executable in the versions directory;
   this is intentionally independent of the active `~/.local/bin/claude` pin.
2. Validate the target and bootstrap as absolute, regular, trusted files.
3. Reject final symlinks and group/world-writable path components.
4. Scrub ambient preload variables when reporting status or using the safe path.
5. Set one known `BUN_OPTIONS=--preload=<bootstrap>` value and `exec` the binary.
6. Provide an obvious safe/bypass mode that unsets preload-related environment variables
   and directly executes the same resolved candidate.

The current lab launcher implements numeric target resolution
([`preload/claude-preload-lab` lines 51–78](../preload/claude-preload-lab#L51-L78)), path
validation ([lines 80–127](../preload/claude-preload-lab#L80-L127)), and a
`--renderpatch-safe` bypass ([lines 131–138](../preload/claude-preload-lab#L131-L138)).

The current experiment rejects an inherited `BUN_OPTIONS` before launching Claude. This
prevents an unrelated preload from executing before the trusted bootstrap gets a chance to
delete the variable. The explicit `--renderpatch-safe` path instead removes inherited Bun
and renderpatch variables before it invokes the same resolved candidate.

The optional installer copies the launcher and bootstrap into the durable user-owned runtime
directory `~/.local/share/claude-renderpatch/preload/`; it does not execute files directly
from the mutable Git checkout. Only `~/.local/bin/claude-preload-lab` is a symlink, and it
points to that installed wrapper. Reinstalling refreshes the durable copies, while
`preload/install.sh --uninstall` sends the link and runtime directory to `trash`. The
installer refuses to replace a non-symlink command or a symlink that points elsewhere. It
creates missing directories under `umask 077`, revalidates their ownership and modes before
copying, and requires its private marker before uninstalling a runtime directory. It never
changes `claude`, `claude-mix`, Claude settings, or an installed Claude executable.

### 2. Minimal bootstrap

The bootstrap should do as little as possible before handing off:

- delete `BUN_OPTIONS` immediately so Claude- or Bun-spawned child processes do not inherit
  the preload;
- remove one-shot extension-selection variables after reading them;
- install one non-enumerable, non-writable global binding under a documented
  `Symbol.for(...)` rendezvous key;
- freeze the registry API and process metadata while keeping hook state private;
- expose an explicit API and runtime version;
- validate optional extension entry paths before importing them; and
- catch synchronous throws, rejected imports, and sync/async hook failures, report them to
  stderr, and let Claude Code continue where the same-realm module has not intentionally
  exited or indefinitely blocked the process.

The lab bootstrap deletes inherited preload variables at startup
([`preload/bootstrap.mjs` lines 4–12](../preload/bootstrap.mjs#L4-L12)), creates a small
versioned hook registry ([lines 23–70](../preload/bootstrap.mjs#L23-L70)), and publishes it
as a protected global property ([lines 73–87](../preload/bootstrap.mjs#L73-L87)).

### 3. Versioned global registry

The registry is the stable rendezvous point between external modules and any future tiny
internal bridge. Its public contract should remain semantic, for example:

```text
Symbol.for("claude-code-renderpatch.runtime")
  apiVersion
  runtimeVersion
  register(name, handler)
  unregister(name)
  invoke(name, payload)
  listHooks()
```

The registry should not expose arbitrary eval, raw memory, or a large unstable internal
object graph. A bridge should publish only the capability needed by a feature, with a
version/capability check and a fail-open result when absent.

### 4. Optional external extensions

Extensions should contain most feature logic. They may register hooks, configure
process-wide monkeypatches, or consume a narrow bridge capability. They should not be
auto-discovered from the current project.

The current bootstrap loads only an explicitly named external module and validates its
entry path before dynamic import
([`preload/bootstrap.mjs` lines 89–141](../preload/bootstrap.mjs#L89-L141)). Ordinary thrown
or rejected imports are caught and reported, after which Claude startup continues
([lines 137–146](../preload/bootstrap.mjs#L137-L146)); intentional exit, indefinite await,
and already-applied global mutations remain outside that error boundary.

### 5. Optional version-pinned internal bridge

When a requirement crosses the closure boundary, the bridge patch should be minimal. Two
preferred forms are:

- publish one narrow adapter into the existing global registry; or
- invoke a named registry hook from one internal call site.

Do not publish the whole internal module or depend externally on current minified names.
The bridge should tolerate the registry being absent so the patched binary remains
launchable through a bypass path.

## Security and failure rules

These are **inferred design requirements**, with current implementation references where
available.

### Trust paths, not the current directory

- Bootstrap and extension paths must be absolute.
- They must resolve under the current user's home and be owned by that user.
- The file and every checked path component must not be group/world writable.
- Reject symlink inputs rather than silently following them.
- Require a regular file.

The launcher performs these checks for the bootstrap
([`preload/claude-preload-lab` lines 80–127](../preload/claude-preload-lab#L80-L127)); the
bootstrap performs equivalent entry-path checks for the optional extension
([`preload/bootstrap.mjs` lines 89–135](../preload/bootstrap.mjs#L89-L135)).

### Never autoload project code

Do not scan `$PWD`, `.claude/`, `package.json`, a repository plugin directory, or a relative
module name. Claude Code is commonly launched inside untrusted or newly cloned projects;
project-relative autoload would turn opening a repository into arbitrary code execution in
the user's Claude process.

Only an explicit, validated user-owned path should enable an extension.

### Delete `BUN_OPTIONS`

The bootstrap must delete `process.env.BUN_OPTIONS` immediately after it starts. Otherwise
every Bun or Claude child process can recursively preload the runtime, causing duplicated
hooks, surprising behavior, or extension execution outside the intended process. The lab
bootstrap does this before registry construction
([`preload/bootstrap.mjs` lines 4–12](../preload/bootstrap.mjs#L4-L12)).

The lab launcher also rejects arbitrary inherited `BUN_OPTIONS` before normal startup;
the verification harness checks both this refusal and the safe bypass behavior.

### Keep a bypass launcher

There must always be a direct path to the exact same resolved candidate with preload
variables unset. This is the recovery path for bootstrap incompatibility, extension bugs,
or startup regressions. The lab provides `--renderpatch-safe`, which unsets preload-related
variables and executes the resolved target
([`preload/claude-preload-lab` lines 131–138](../preload/claude-preload-lab#L131-L138)).
Launching the resolved candidate directly is an additional bypass.

### Fail closed on trust, fail open on optional behavior

Entry-path validation must fail closed: an untrusted, relative, writable, or wrongly owned
entry module must not run. These Unix owner/mode checks do not validate macOS ACLs or the
module's transitive import graph; a trusted entry module and everything it imports has full
same-user code execution.

Once a module has passed the trust boundary, ordinary synchronous throws, rejected imports,
and sync/async hook failures should fail open: report the error, skip that extension/hook,
and allow Claude Code to start or continue. Same-realm JavaScript cannot safely roll back
partial mutations, cancel unresolved top-level await, or prevent a module from calling
`process.exit`; the safe launcher is the recovery path for those cases. The lab registry
catches hook exceptions and rejections
([`preload/bootstrap.mjs` lines 53–64](../preload/bootstrap.mjs#L53-L64)), and the extension
loader catches import failures ([lines 137–146](../preload/bootstrap.mjs#L137-L146)).

The core bootstrap itself should remain tiny because a syntax error or failure before its
own error boundary can still prevent startup. The bypass launcher is the final recovery
mechanism.

## Verification checklist for future Claude Code updates

No-repatch mechanisms still need verification. For each new version:

1. Launch through the preload wrapper and confirm a preload marker appears once.
2. Repeat the `process.argv` mutation test to prove execution still precedes CLI parsing.
3. Repeat the `console.log` wrapper test to prove the global realm is still shared.
4. Verify `require`, top-level `import()`, `node:fs`, `Bun.file`, and `process` remain
   available if extensions depend on them.
5. Inspect `require.cache` again; do not assume a new release still exposes only the same
   three entries, and do not treat newly visible exports as stable until verified.
6. Confirm the bootstrap deletes `BUN_OPTIONS` before any child-process test.
7. Test an invalid/untrusted extension path: it must not execute.
8. Test a throwing trusted extension: Claude Code must still start.
9. Test the safe/bypass launcher against the same resolved candidate.
10. If a feature uses a version-pinned internal bridge, separately rediscover, re-sign,
    and verify that bridge under the repository's patching rules.

## Conclusion

The external Bun preload is a real, zero-binary-patch startup seam: it ran before CLI
parsing on patched 2.1.219 and stock 2.1.220, shared process globals with Claude Code, and
provided useful Bun/Node/process APIs. It is suitable for a wrapper, bootstrap, global
registry, trusted external extensions, and update-stable monkeypatches of runtime-reachable
surfaces.

It is not an automatic doorway into the bundled application's lexical scope. The minimal
`require.cache`, empty CLI exports, and closure boundary mean private renderer and resolver
internals still require a version-pinned patch. The recommended long-term split is
therefore external policy plus, only where necessary, the smallest possible rediscovered
internal bridge.
