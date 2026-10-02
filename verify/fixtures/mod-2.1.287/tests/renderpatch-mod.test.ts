import { expect, test } from 'claude-code/testing'

test('/renderpatch-hello returns the fixture marker', async ($) => {
  const answer = await $.command.run({ command: 'renderpatch-hello', args: '' })
  expect(answer.text).toBe('RENDERPATCH_MOD_2_1_287')
})
