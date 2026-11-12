import { randomUUID } from 'node:crypto'

const fallback = { decision: 'deny', reason: 'The reviewer could not return a verified decision.' }

export async function reviewOperation(llm, config, providers, evidence, callerSignal) {
  if (evidence.destructive) return { decision: 'deny', reason: 'The requested operation is destructive.' }
  if (evidence.sensitive) return { decision: 'deny', reason: 'The requested operation targets a protected path.' }
  if (evidence.unverified || evidence.escalation || evidence.effect === 'opaque') {
    return { decision: 'deny', reason: 'The operation does not have verifiable effects.' }
  }

  const provider = config.provider ?? 'deepseek-official'
  const timeout = config.timeoutMs ?? 15000
  if (!llm || !providers.includes(provider) || typeof config.model !== 'string' || !config.model.trim() ||
      !Number.isInteger(timeout) || timeout < 1 || timeout > 60000 || callerSignal.aborted) return fallback

  const signal = AbortSignal.any([callerSignal, AbortSignal.timeout(timeout)])
  const run = async () => {
    const stream = await llm.stream({
      provider,
      model: config.model,
      signal,
      maxTokens: 512,
      tools: [],
      system: 'You are a read-only approval reviewer. Evaluate the structured evidence only. Deny destructive or sensitive operations and deny on uncertainty. Return only JSON with decision ("allow" or "deny") and a short reason.',
      messages: [{
        id: randomUUID(),
        role: 'user',
        source: { kind: 'plugin', plugin: 'dsh-codex-sandbox' },
        content: [{ type: 'text', text: JSON.stringify(evidence) }],
      }],
    })

    let output = ''
    let complete = false
    for await (const chunk of stream) {
      signal.throwIfAborted()
      if (chunk.type === 'text-delta') {
        output += chunk.delta ?? ''
        if (output.length > 4096) return fallback
      }
      if (chunk.type === 'finish') {
        complete = chunk.reason?.kind === 'stop'
        break
      }
    }
    if (!complete) return fallback
    const result = JSON.parse(output)
    if ((result?.decision !== 'allow' && result?.decision !== 'deny') ||
        typeof result.reason !== 'string' || !result.reason.trim() || result.reason.length > 280) return fallback
    return { decision: result.decision, reason: result.reason.trim() }
  }

  let abort
  try {
    return await Promise.race([
      new Promise(resolve => {
        abort = () => resolve(fallback)
        signal.addEventListener('abort', abort, { once: true })
        if (signal.aborted) abort()
      }),
      run(),
    ])
  } catch {
    return fallback
  } finally {
    if (abort) signal.removeEventListener('abort', abort)
  }
}
