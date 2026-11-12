import type { Host } from '../../../src/contracts.js'
export interface Config {
  sandbox?: 'read-only' | 'workspace-write' | 'danger-full-access'
  approvalPolicy?: 'untrusted' | 'on-request' | 'never'
  trustedProviders?: string[]
  reviewer?: false | { provider?: string; model: string; timeoutMs?: number }
}
// Runtime source
import { defaultTrustedProviders, denyPlanTool, guardModelRoutes, inPlan } from '../../../src/tools.js'
import { approvalPolicies, assess, needsApproval, sandboxModes } from './policy.js'
import { reviewOperation } from './reviewer.js'

export const name = 'dsh-codex-sandbox'
export const inject = ['tools']
const localFsTypes = new Set(['SandboxedFileSystem', 'LocalFileSystem'])
const reject = reason => ({ kind: 'deny', reason })

export function apply(ctx: Host, config: Config = {}) {
  const sandbox = config.sandbox ?? 'workspace-write'
  const policy = config.approvalPolicy ?? 'on-request'
  const valid = sandboxModes.includes(sandbox) && approvalPolicies.includes(policy)
  const providers = Array.isArray(config.trustedProviders) ? config.trustedProviders : defaultTrustedProviders
  const owned = new WeakMap()
  const approved = new WeakSet()

  function inspect(call) {
    const fs = ctx.get('fs')
    return assess(call, inPlan(ctx, call.agent) ? 'read-only' : sandbox, localFsTypes.has(fs?.constructor?.name))
  }

  function guard(call) {
    if (!valid) return 'Sandbox configuration is invalid.'
    const planDenial = denyPlanTool(ctx, call)
    if (planDenial) return planDenial
    const state = inspect(call)
    if (state.denial) return state.denial
    if (needsApproval(state, policy) && !approved.has(call)) return 'No approval was granted for this call.'
  }

  async function review(state, signal) {
    if (!config.reviewer) return true
    const result = await reviewOperation(ctx.get('llm'), config.reviewer, providers, state.assessment.evidence, signal)
    ctx.logger.info('dsh-codex-sandbox: reviewer ' + result.decision + ' for ' + state.assessment.evidence.tool)
    if (result.decision === 'deny') state.reviewDenial = result.reason
    return result.decision === 'allow'
  }

  ctx.on('approval/request', async (request, next) => {
    const state = owned.get(request)
    if (!state) return policy === 'never' ? 'rejected' : next()
    state.seen = true
    if (!await review(state, request.signal) || request.signal.aborted) return 'rejected'
    return next()
  }, { prepend: true })

  ctx.on('tools/pre-execute', async (call, next) => {
    if (!valid) return reject('Sandbox configuration is invalid.')
    const planDenial = denyPlanTool(ctx, call)
    if (planDenial) return reject(planDenial)
    const assessment = inspect(call)
    const state = { assessment, seen: false, reviewDenial: undefined }
    if (needsApproval(assessment, policy)) {
      const approval = ctx.get('approval')
      if (!approval || !call.agent) return reject(assessment.denial ?? 'The approval channel is unavailable.')
      const request = {
        agent: call.agent,
        toolName: call.name,
        callId: call.callId,
        signal: call.signal,
        reason: assessment.denial
          ? assessment.denial + ' The fixed boundary applies after review.'
          : 'Untrusted policy requires a decision for this single ' + call.name + ' call.',
      }
      owned.set(request, state)
      let outcome
      try {
        outcome = await approval.request(request)
      } catch {
        outcome = 'unavailable'
      } finally {
        owned.delete(request)
      }
      if (state.reviewDenial) return reject('Auto-review denied the operation. ' + state.reviewDenial)
      if (assessment.denial) return reject(assessment.denial)
      if (!state.seen || outcome !== 'allowed-once' || call.signal.aborted) {
        return reject('No approval was granted for this call.')
      }
      approved.add(call)
    } else if (assessment.denial) {
      if (config.reviewer && !call.signal.aborted) await review(state, call.signal)
      return reject(state.reviewDenial ? 'Auto-review denied the operation. ' + state.reviewDenial : assessment.denial)
    }
    return next()
  }, { prepend: true })

  ctx.tools.guard(guard)
  ctx.on('tools/execute', async (call, next) => {
    try {
      const reason = guard(call)
      if (reason) throw new Error(reason)
      return await next()
    } finally {
      approved.delete(call)
    }
  })
  guardModelRoutes(ctx, agent => !valid || sandbox !== 'danger-full-access' || inPlan(ctx, agent), providers, 'Sandbox')

  ctx.get('systemPrompt')?.section({
    name: 'codex-sandbox:policy',
    order: -8000,
    text: ({ agent }) => 'Tool boundary: ' + (inPlan(ctx, agent) ? 'read-only' : sandbox) +
      '. Approval policy: ' + policy + '. Workspace-write permits verified local write/edit targets in the session workspace. Approval does not change the boundary.',
  })
}
