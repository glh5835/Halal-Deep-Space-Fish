export function makeHarness({ cwd, initialPreset, legacy = false, approvalBypass = false, reviewStream, onHuman } = {}) {
  const handlers = new Map()
  const commands = new Map()
  const guards = []
  const cleanups = []
  const presets = []
  const prefixes = []
  const humanRequests = []
  const approvalRequests = []
  const log = []
  const prompts = []
  const events = []
  const toolNames = ['read', 'glob', 'grep', 'write', 'edit', 'apply_patch', 'bash', 'pwsh', 'web_search', 'exit_plan_mode']
  let commandId = 0
  let allowedTools
  let active = false
  let pending

  const session = {
    id: 'session-1',
    header: { cwd, agentPreset: initialPreset },
    get seq() { return events.length },
    eventAt(index) { return events[index] },
  }

  const agent = {
    id: session.id,
    session,
    status: 'idle',
    options: { provider: 'deepseek-official' },
    ctx: { get: () => scopedTools },
    steer(message) {
      prompts.push({ mode: active, message })
      agent.status = 'running'
    },
  }

  const scopedTools = {
    restrict({ allow }) {
      allowedTools = allow
      return () => { allowedTools = undefined }
    },
  }

  function on(event, handler, options) {
    if (!handlers.has(event)) handlers.set(event, [])
    const list = handlers.get(event)
    if (options?.prepend) list.unshift(handler)
    else list.push(handler)
  }
  function emit(event, data) {
    for (const handler of handlers.get(event) ?? []) handler(data)
  }
  function waterfall(event, input, final) {
    const chain = handlers.get(event) ?? []
    const step = index => index === chain.length ? final() : chain[index](input, () => step(index + 1))
    return step(0)
  }

  class LocalFileSystem {}
  const ctx = {
    agents: { get: id => id === agent.id ? agent : undefined },
    agentPresets: legacy
      ? { roots: [] }
      : {
          presetForSession: target => target.header.agentPreset,
          async register(preset) {
            presets.push(preset)
            return () => presets.splice(presets.indexOf(preset), 1)
          },
        },
    commands: { register: command => commands.set(command.name, command) },
    tools: {
      guard: guard => guards.push(guard),
      schemas: () => (allowedTools ?? toolNames).map(name => ({ name })),
    },
    systemPrompt: { section: section => prefixes.push(section) },
    planMode: {
      get: () => ({ active, pending }),
      set(_, mode) {
        if (agent.status === 'running') pending = mode === active ? undefined : mode
        else {
          active = mode
          pending = undefined
        }
      },
    },
    fs: new LocalFileSystem(),
    llm: reviewStream ? { stream: reviewStream } : undefined,
    approval: {
      async request(request) {
        approvalRequests.push(request)
        if (approvalBypass) return 'allowed-once'
        return waterfall('approval/request', request, async () => {
          humanRequests.push(request)
          return onHuman ? onHuman(request) : 'allowed-once'
        })
      },
    },
    logger: { info: message => log.push(message) },
    on,
    effect: setup => cleanups.push(setup()),
    get(key) { return ctx[key] },
  }

  on('agent/pre-step', async (_, next) => {
    const decision = await next()
    if (decision.kind === 'enter' && pending !== undefined) {
      active = pending
      pending = undefined
    }
    return decision
  })

  return {
    ctx, agent, session, presets, prefixes, prompts, humanRequests, approvalRequests, log, cleanups,
    created: () => emit('agent/created', { agent }),
    async step(messages, modelSelection) {
      const signal = new AbortController().signal
      return waterfall('agent/pre-step', { agent, messages, signal, modelSelection },
        async () => ({ kind: 'enter', messages }))
    },
    command(name, rawInput, attachments = []) {
      const id = ++commandId
      events.push({ type: 'command/run', data: { commandId: id, name } })
      const result = commands.get(name).handler({ agent, rawInput, attachments, signal: new AbortController().signal })
      events.push({ type: 'command/done', data: { commandId: id, ...result } })
      return result
    },
    async execute(name, args, body = () => 'ran') {
      const call = { name, arguments: args, agent, signal: new AbortController().signal, callId: 'call-' + commandId }
      const pre = await waterfall('tools/pre-execute', call, async () => ({ kind: 'allow' }))
      if (pre.kind !== 'allow') return { ok: false, reason: pre.reason }
      for (const guard of guards) {
        const reason = guard(call)
        if (reason) return { ok: false, reason }
      }
      try {
        return { ok: true, value: await waterfall('tools/execute', call, body) }
      } catch (error) {
        return { ok: false, reason: error.message }
      }
    },
  }
}
