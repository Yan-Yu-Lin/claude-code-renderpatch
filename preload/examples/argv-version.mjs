// Demonstrate that the preload runs before Claude Code parses process.argv.
if (!process.argv.includes("--version") && !process.argv.includes("-v")) {
  process.argv.push("--version")
}
