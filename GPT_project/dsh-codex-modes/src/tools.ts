const reads = new Set(['read', 'read_image', 'glob', 'grep'])
const dialogue = new Set(['ask_user_question', 'exit_plan_mode'])
export const defaultTrustedProviders = ['deepseek-official']

export function argsOf(call) {
  const value = call.arguments
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

export function isReadTool(call) {
  return reads.has(call.name) || call.name === 'str_replace_editor' && argsOf(call).command === 'view'
}

export function isDialogueTool(call) {
  return dialogue.has(call.name)
}

export function inPlan(ctx, agent) {
  const plan = ctx.get('planMode')
  if (!plan) return false
  const visited = new Set()
  while (agent && !visited.has(agent.session.id)) {
    const state = plan.get(agent)
    if (state.active || state.pending === true) return true
    visited.add(agent.session.id)
    const parent = agent.session.header.parentSession
    const id = typeof parent === 'string' ? parent : parent?.id ?? parent?.sessionId
    agent = id ? ctx.get('agents')?.get(id) : undefined
  }
  return false
}

export function denyPlanTool(ctx, call) {
  if (inPlan(ctx, call.agent) && !isReadTool(call) && !isDialogueTool(call)) {
    return 'Plan is read-only. Switch to Default to request execution.'
  }
}

export function guardModelRoutes(ctx, isRestricted, providers, name) {
  const trusted = new Set(providers)
  // In 0.1.x this is the final route after request selection.
  ctx.on('agent/request', async ({ agent }, next) => {
    const selection = await next()
    if (isRestricted(agent) && !trusted.has(selection.provider)) {
      throw new Error(name + ': this provider is outside the trusted model-only routes.')
    }
    return selection
  })
  // In 0.2.x the resolved selection is already present at pre-step.
  ctx.on('agent/pre-step', async ({ agent, modelSelection }, next) => {
    const result = await next()
    const provider = modelSelection?.provider ?? agent.options.provider
    if (result.kind === 'enter' && provider && isRestricted(agent) && !trusted.has(provider)) {
      return { kind: 'reject', reason: name + ': this provider is outside the trusted model-only routes.' }
    }
    return result
  })
}
