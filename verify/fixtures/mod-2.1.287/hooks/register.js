export function register(on) {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'renderpatch-hello',
      description: 'Print the renderpatch mod fixture marker',
    })
    return next(e)
  })

  on('command.run', { command: 'renderpatch-hello' }, async () => ({
    text: 'RENDERPATCH_MOD_2_1_287',
  }))
}
