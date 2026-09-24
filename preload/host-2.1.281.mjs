// Host preload for the 2.1.281 source bridge.
//
// Claude Code >= 2.1.271 renders through Bun.ant.CellSegmenter, which exists
// only in Anthropic's internal Bun build embedded in the official executable;
// no published Bun can run the interactive UI. The bridge therefore runs its
// patched, extracted graph inside a verbatim copy of the official executable:
// this module is the last --preload, imports the patched entry, and never
// settles, so the embedded (unpatched) entry never starts. Only
// RP_HOST_ENTRY selects the graph; it is removed before any child can inherit it.
const entry = process.env.RP_HOST_ENTRY
delete process.env.RP_HOST_ENTRY
if (typeof entry === "string" && entry.startsWith("/") && entry.endsWith("/graph/cli")) {
  try {
    await import(entry)
  } catch (error) {
    process.stderr.write(`[renderpatch-host] patched graph failed to load: ${error?.stack ?? error}\n`)
    process.exit(70)
  }
  await new Promise(() => {})
}
