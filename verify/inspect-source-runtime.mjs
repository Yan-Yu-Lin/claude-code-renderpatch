// Explicit test extension: metadata and pure resolver calls only, no inference.
import { appendFileSync, readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'

export function activate(runtime) {
  const target = process.env.RP_VERIFY_TARGET
  const log = process.env.RP_VERIFY_LOG
  if (!target || !log) throw new Error('Missing explicit verification paths')
  const status = runtime.read.status()
  const artifactSha256 = createHash('sha256').update(readFileSync(target)).digest('hex')
  const activation = runtime.registerExtension({
    id: 'verify-source-runtime', version: '1.0.0', schemaVersion: 1, unsafeRaw: true,
    requires: {
      policyApiVersion: 2, bridges: [], bridgeAbi: 1, rawSlotApi: status.rawSlotApi,
      target: {
        version: '2.1.261', bridgeBuildId: status.bridgeBuildId, artifactSha256,
        stockSha256: '5efecaff231b798be3c66def9be54183623b328b80eaef17f93c43987024e82a',
      },
      captureDomains: Array.from({ length: 6 }, (_, id) => ({ id, abiVersion: 1 })),
    },
  })
  const record = value => appendFileSync(log, JSON.stringify(value) + '\n')
  record({ kind: 'activation', unsafe: !!activation.unsafe, active: status.bridgeFacade.active })
  if (!activation.unsafe) throw new Error('Exact-version capture negotiation failed')
  const recorded = new Set()
  for (let id = 0; id < 6; id++) runtime.read.observe(id, ({ event }) => {
    if (event === 'clear' || recorded.has(id)) return
    const capture = activation.unsafe.capture(id)
    if (!capture) return
    recorded.add(id)
    record({ kind: 'capture', id, bitmap: capture.presenceBitmap, types: capture.slots.map(v => v === null ? 'null' : Array.isArray(v) ? 'array' : typeof v) })
    if (id === 4) {
      const modelCapture = activation.unsafe.capture(0)
      const models = ['sonnet', 'haiku', 'gpt-5.6-sol', 'kimi-k3', 'claude-f51[1m]', 'custom-route']
      record({ kind: 'windows', values: Object.fromEntries(models.map(m => [m, runtime.read.mc.windowPreview(m)])) })
      const resolver = modelCapture.slots[15]
      const parent = 'claude-sonnet-4-6'
      record({ kind: 'routing', explicit: resolver(undefined, parent, 'sonnet', 'default'), frontmatter: resolver('sonnet', parent, undefined, 'default'), inherited: resolver(undefined, parent, 'inherit', 'default'), canonical: modelCapture.slots[1]('sonnet') })
    }
    if (id === 2) record({kind:'app',defaultStateObject:typeof capture.slots[5]() === 'object',liveStateObject:typeof capture.slots[2]() === 'object'})
    if (id === 3) record({kind:'messages',value:runtime.read.messages()})
    if (id === 4) record({kind:'repl',value:runtime.read.repl.state(),commands:runtime.read.repl.catalogs()})
  })
}
