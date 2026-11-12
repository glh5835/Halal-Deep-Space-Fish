import type { Host } from '../../../src/contracts.js'
export interface Config { trustedProviders?: string[] }
// Runtime source
import { randomUUID } from 'node:crypto'
import { defaultTrustedProviders, denyPlanTool, guardModelRoutes, inPlan } from '../../../src/tools.js'

export const name = 'dsh-codex-collaboration'
export const inject = ['commands', 'planMode', 'tools']

export function apply(ctx: Host, config: Config = {}) {
  const submissions = new WeakMap()
  const denial = call => denyPlanTool(ctx, call)
  ctx.tools.guard(denial)
  ctx.on('tools/execute', async (call, next) => {
    const reason = denial(call)
    if (reason) throw new Error(reason)
    return next()
  })
  guardModelRoutes(ctx, agent => inPlan(ctx, agent), config.trustedProviders ?? defaultTrustedProviders, 'Plan')

  ctx.on('agent/pre-step', async ({ agent, messages, signal }, next) => {
    const pending = submissions.get(agent)
    if (!pending || !messages.some(({ id }) => id === pending.id)) return next()
    try {
      signal.throwIfAborted()
      ctx.planMode.set(agent, pending.active)
      const step = await next()
      if (step.kind === 'enter' && ctx.planMode.get(agent).active !== pending.active) {
        return { kind: 'reject', reason: 'The requested collaboration mode could not be committed.' }
      }
      return step
    } finally {
      submissions.delete(agent)
    }
  }, { prepend: true })

  ctx.commands.register({
    name: 'collab',
    description: 'Select Plan or Default, optionally submit a message in the same action',
    input: { hint: '[plan|default] [message]', images: true },
    recordInput: false,
    handler({ agent, rawInput, attachments, signal }) {
      const state = ctx.planMode.get(agent)
      const input = rawInput.trim()
      if (!input && !attachments.length) {
        return { kind: 'success', text: 'Collaboration: ' + ((state.pending ?? state.active) ? 'Plan' : 'Default') }
      }
      const match = /^(plan|default)(?:\s+([\s\S]*))?$/i.exec(input)
      if (!match) return { kind: 'error', text: 'Usage: /collab plan|default [message]' }
      if (submissions.has(agent) && agent.status === 'running') {
        return { kind: 'error', text: 'A mode and message are already awaiting admission.' }
      }
      submissions.delete(agent)
      const active = match[1].toLowerCase() === 'plan'
      const text = match[2]?.trim()
      const submit = Boolean(text || attachments.length)
      if (submit && agent.status !== 'idle') {
        return { kind: 'error', text: 'Wait for the current turn before submitting a mode with a message.' }
      }

      signal?.throwIfAborted()
      ctx.planMode.set(agent, active)
      if (submit) {
        const message = {
          id: randomUUID(),
          role: 'user',
          source: { kind: 'user' },
          content: [...attachments, ...(text ? [{ type: 'text', text }] : [])],
        }
        submissions.set(agent, { active, id: message.id })
        try {
          agent.steer(message)
        } catch (error) {
          submissions.delete(agent)
          ctx.planMode.set(agent, state.pending ?? state.active)
          throw error
        }
      }
      return { kind: 'success', text: 'Collaboration selected: ' + (active ? 'Plan' : 'Default') }
    },
  })
}
