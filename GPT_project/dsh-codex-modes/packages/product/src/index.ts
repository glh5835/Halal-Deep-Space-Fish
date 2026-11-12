import type { Host } from '../../../src/contracts.js'
// Runtime source
import { fileURLToPath } from 'node:url'
import { parseMode, presetDefinitions, presetMode, products } from '../../../src/presets.js'

export const name = 'dsh-codex-product'
export const inject = ['agentPresets', 'agents', 'commands', 'systemPrompt', 'tools']
const switched = 'Product selected: '

function eventAt(session, index) {
  return session.eventAt?.(index) ?? session.events?.[index]
}

function recordedMode(session) {
  const results = new Map()
  for (let index = session.seq - 1; index >= 0; index--) {
    const event = eventAt(session, index)
    if (event?.type === 'command/done' && event.data.kind === 'success' &&
        typeof event.data.text === 'string' && event.data.text.startsWith(switched)) {
      const mode = parseMode(event.data.text.slice(switched.length))
      if (mode) results.set(event.data.commandId, mode)
    } else if (event?.type === 'command/run' && event.data.name === 'product') {
      const mode = results.get(event.data.commandId)
      if (mode) return mode
    }
  }
}

export async function apply(ctx: Host) {
  const roster = ctx.agentPresets
  const disposePresets = []
  if (roster.register) {
    try {
      for (const preset of presetDefinitions(process.platform === 'win32')) {
        disposePresets.push(await roster.register(preset))
      }
    } catch (error) {
      for (const dispose of disposePresets.reverse()) await dispose()
      throw error
    }
  } else {
    // The legacy roster discovers presets from its live configured roots.
    const roots = roster.roots
    if (!Array.isArray(roots) || Object.isFrozen(roots)) throw new Error('Cannot register legacy DSH presets')
    const root = { path: fileURLToPath(new URL('./presets/', import.meta.url)), trust: 'system' }
    roots.push(root)
    disposePresets.push(() => {
      const index = roots.indexOf(root)
      if (index >= 0) roots.splice(index, 1)
    })
  }

  const selections = new WeakMap()
  const masks = new Map()

  function modeFor(agent) {
    const override = selections.get(agent)
    if (override) return override
    if (roster.presetForSession) return presetMode(roster.presetForSession(agent.session))
    for (let index = agent.session.seq - 1; index >= 0; index--) {
      const event = eventAt(agent.session, index)
      if (event?.type === 'agent-preset/selected') return presetMode(event.data.agentPreset)
    }
    return presetMode(agent.session.header.agentPreset)
  }

  function refresh(agent) {
    const mode = modeFor(agent)
    const prior = masks.get(agent)
    if (prior?.mode === mode) return
    prior?.dispose()
    masks.delete(agent)
    if (!mode) return
    const names = new Set(ctx.tools.schemas(agent).map(tool => tool.name))
    const allow = products[mode].tools.filter(tool => names.has(tool))
    // Scope the tool defaults to this session. No policy or approval is changed.
    masks.set(agent, { mode, dispose: agent.ctx.get('tools').restrict({ allow }) })
  }

  ctx.effect(() => async () => {
    for (const { dispose } of masks.values()) await dispose()
    masks.clear()
    for (const dispose of disposePresets.reverse()) await dispose()
  })
  ctx.systemPrompt.section({
    name: 'codex-product:prefix',
    order: -9000,
    text: ({ agent }) => {
      const mode = agent && modeFor(agent)
      return mode ? products[mode].prefix : ''
    },
  })
  ctx.on('agent/created', ({ agent }) => {
    const previous = recordedMode(agent.session)
    if (previous) selections.set(agent, previous)
    refresh(agent)
  })
  ctx.on('agent/disposed', ({ agent }) => {
    masks.get(agent)?.dispose()
    masks.delete(agent)
  })
  ctx.on('agent-preset/selected', id => {
    const agent = ctx.agents.get(id)
    if (agent && agent.status === 'idle') refresh(agent)
  })
  ctx.commands.register({
    name: 'product',
    description: 'Show or select the Chat, Work, or Codex product mode',
    input: { hint: '[chat|work|codex]' },
    handler({ agent, rawInput }) {
      const value = rawInput.trim().toLowerCase()
      if (!value) {
        const mode = modeFor(agent)
        return { kind: 'success', text: 'Product: ' + (mode ? products[mode].label : 'DSH session preset') }
      }
      const mode = parseMode(value)
      if (!mode) return { kind: 'error', text: 'Usage: /product chat|work|codex' }
      if (agent.status !== 'idle') return { kind: 'error', text: 'Wait for the active turn before switching product mode.' }
      const previous = selections.get(agent)
      selections.set(agent, mode)
      try {
        refresh(agent)
      } catch (error) {
        if (previous) selections.set(agent, previous)
        else selections.delete(agent)
        refresh(agent)
        throw error
      }
      return { kind: 'success', text: switched + mode }
    },
  })
}
