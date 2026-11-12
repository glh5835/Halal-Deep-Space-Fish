export interface Session {
  id: string
  seq: number
  header: { cwd?: string; agentPreset?: string; parentSession?: string | { id: string } }
  eventAt?(sequence: number): { type: string; data: Record<string, unknown> } | undefined
}

export interface Agent {
  id: string
  session: Session
  ctx: Host
  status: 'idle' | 'running'
  options: { provider?: string; model?: string }
  steer(message: unknown): void
}

export interface ToolCall {
  name: string
  arguments: unknown
  agent?: Agent
  callId?: string
  signal: AbortSignal
}

export interface Host {
  agents: { get(id: string): Agent | undefined }
  agentPresets: {
    register?(definition: unknown): Promise<() => void | Promise<void>>
    roots?: { path: string; trust: string }[]
    presetForSession?(session: Session): string | null
  }
  approval: { request(request: unknown): Promise<string> }
  commands: { register(definition: unknown): unknown }
  logger: { info(message: string): void }
  planMode: {
    get(agent: Agent): { active: boolean; pending?: boolean }
    set(agent: Agent, active: boolean): unknown
  }
  systemPrompt: { section(definition: unknown): unknown }
  tools: {
    guard(guard: (call: ToolCall) => string | undefined): unknown
    schemas(agent: Agent): { name: string }[]
    restrict(filter: { allow: string[] }): () => void
  }
  get(key: string): any
  effect(register: () => () => void | Promise<void>): unknown
  on(event: string, listener: (...args: any[]) => unknown, options?: { prepend: boolean }): unknown
}
