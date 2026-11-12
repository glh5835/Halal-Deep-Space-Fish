export function addScenarios(test, assert, { makeHarness, product, collaboration, sandbox, workspace, outside, join, exists, write }) {
  test('standalone Plan blocks all write and opaque tool bodies', async () => {
    const h = makeHarness({ cwd: workspace })
    collaboration.apply(h.ctx)
    h.command('collab', 'plan')
    for (const name of ['write', 'edit', 'apply_patch', 'pwsh', 'custom_action']) {
      const result = await h.execute(name, { file_path: 'planned.txt' }, () => write(join(workspace, 'planned.txt')))
      assert.equal(result.ok, false)
      assert.match(result.reason, /Plan is read-only/)
    }
    assert.equal(exists(join(workspace, 'planned.txt')), false)
    assert.equal((await h.execute('read', { file_path: 'baseline.txt' })).ok, true)
  })

  test('one command switches mode and sends the same pending message', async () => {
    const h = makeHarness({ cwd: workspace })
    collaboration.apply(h.ctx)
    assert.equal(h.command('collab', 'plan Inspect the workspace').kind, 'success')
    assert.equal(h.prompts[0].mode, true)
    assert.equal(h.prompts[0].message.content[0].text, 'Inspect the workspace')
    assert.equal(h.command('collab', 'default').kind, 'error')
    h.ctx.planMode.set(h.agent, false)
    assert.equal((await h.step([h.prompts[0].message])).kind, 'enter')
    assert.equal(h.ctx.planMode.get(h.agent).active, true)
    h.agent.status = 'idle'
    assert.equal(h.command('collab', 'default Apply the plan').kind, 'success')
    assert.equal(h.prompts[1].mode, false)
    assert.equal((await h.step([h.prompts[1].message])).kind, 'enter')
    assert.equal(h.ctx.planMode.get(h.agent).active, false)
  })

  test('workspace-write on-request writes inside and asks outside without widening', async () => {
    const h = makeHarness({ cwd: workspace })
    sandbox.apply(h.ctx)
    const inside = join(workspace, 'allowed.txt')
    const external = join(outside, 'outside.txt')
    assert.equal((await h.execute('write', { file_path: 'allowed.txt' }, () => write(inside))).ok, true)
    assert.equal(exists(inside), true)
    assert.equal(h.humanRequests.length, 0)
    const result = await h.execute('write', { file_path: external }, () => write(external))
    assert.equal(result.ok, false)
    assert.match(result.reason, /outside the verified workspace/)
    assert.equal(h.humanRequests.length, 1)
    assert.equal(exists(external), false)
  })

  test('reviewer rejects destructive and protected operations before human approval', async () => {
    let modelCalls = 0
    const h = makeHarness({ cwd: workspace, reviewStream() { modelCalls++; throw new Error('unexpected call') } })
    sandbox.apply(h.ctx, { reviewer: { model: 'reviewer-test' } })
    const deletion = await h.execute('delete_file', { file_path: 'baseline.txt' })
    const credential = await h.execute('read', { file_path: '.env' })
    assert.match(deletion.reason, /Auto-review denied.*destructive/)
    assert.match(credential.reason, /Auto-review denied.*protected/)
    assert.equal(modelCalls, 0)
    assert.equal(h.humanRequests.length, 0)
  })

  test('reviewer receives structured evidence without tools, then human grants one call', async () => {
    const order = []
    const h = makeHarness({
      cwd: workspace,
      async *reviewStream(request) {
        order.push('review')
        assert.deepEqual(request.tools, [])
        assert.equal(request.model, 'reviewer-test')
        const evidence = JSON.parse(request.messages[0].content[0].text)
        assert.equal(evidence.effect, 'write')
        assert.equal(evidence.outside, false)
        assert.equal(JSON.stringify(evidence).includes('private-content'), false)
        yield { type: 'text-delta', delta: '{"decision":"allow","reason":"Verified local write"}' }
        yield { type: 'finish', reason: { kind: 'stop' } }
      },
      onHuman() { order.push('human'); return 'allowed-once' },
    })
    sandbox.apply(h.ctx, { approvalPolicy: 'untrusted', reviewer: { model: 'reviewer-test' } })
    for (let i = 0; i < 2; i++) {
      assert.equal((await h.execute('write', { file_path: 'normal.txt', content: 'private-content' }, () => { order.push('body') })).ok, true)
    }
    assert.deepEqual(order, ['review', 'human', 'body', 'review', 'human', 'body'])
  })

  test('reviewer failure and timeout fail closed', async () => {
    const h = makeHarness({
      cwd: workspace,
      async *reviewStream() {
        yield { type: 'text-delta', delta: 'not a verdict' }
        yield { type: 'finish', reason: { kind: 'stop' } }
      },
    })
    sandbox.apply(h.ctx, { approvalPolicy: 'untrusted', reviewer: { model: 'reviewer-test' } })
    const result = await h.execute('write', { file_path: 'normal.txt' })
    assert.match(result.reason, /could not return a verified decision/)
    assert.equal(h.humanRequests.length, 0)

    const pending = makeHarness({ cwd: workspace, reviewStream: () => new Promise(() => {}) })
    sandbox.apply(pending.ctx, { approvalPolicy: 'untrusted', reviewer: { model: 'reviewer-test', timeoutMs: 10 } })
    const keepAlive = setTimeout(() => {}, 200)
    try {
      const timeout = await pending.execute('write', { file_path: 'normal.txt' })
      assert.match(timeout.reason, /could not return a verified decision/)
    } finally {
      clearTimeout(keepAlive)
    }
    assert.equal(pending.humanRequests.length, 0)
  })

  test('product presets and in-session selection preserve both independent guards', async () => {
    const h = makeHarness({ cwd: workspace, initialPreset: 'codex-product-chat' })
    await product.apply(h.ctx)
    collaboration.apply(h.ctx)
    sandbox.apply(h.ctx)
    h.created()
    assert.deepEqual(h.presets.map(preset => preset.name), ['Chat', 'Work', 'Codex'])
    assert.equal(h.ctx.tools.schemas().some(tool => tool.name === 'write'), false)
    h.command('product', 'work')
    assert.equal(h.ctx.tools.schemas().some(tool => tool.name === 'write'), true)
    assert.match(h.prefixes[0].text({ agent: h.agent }), /^Work/)
    h.command('collab', 'plan')
    h.command('product', 'codex')
    assert.equal((await h.execute('write', { file_path: 'plan.txt' })).ok, false)
    h.command('collab', 'default')
    assert.equal((await h.execute('write', { file_path: join(outside, 'external.txt') })).ok, false)
    assert.equal(h.humanRequests.length, 1)
  })

  test('legacy file roster mounts and disposes the plugin preset root', async () => {
    const h = makeHarness({ cwd: workspace, legacy: true, initialPreset: 'codex-product-work' })
    await product.apply(h.ctx)
    h.created()
    assert.equal(h.ctx.agentPresets.roots.length, 1)
    assert.match(h.prefixes[0].text({ agent: h.agent }), /^Work/)
    await h.cleanups[0]()
    assert.equal(h.ctx.agentPresets.roots.length, 0)
  })

  test('never is silent and read-only or full access remain independent choices', async () => {
    const confined = makeHarness({ cwd: workspace })
    sandbox.apply(confined.ctx, { sandbox: 'read-only', approvalPolicy: 'never' })
    assert.equal((await confined.execute('write', { file_path: 'inside.txt' })).ok, false)
    assert.equal(confined.approvalRequests.length, 0)

    const full = makeHarness({ cwd: workspace })
    sandbox.apply(full.ctx, { sandbox: 'danger-full-access', approvalPolicy: 'never' })
    assert.equal((await full.execute('write', { file_path: join(outside, 'outside.txt') })).ok, true)
    full.ctx.planMode.set(full.agent, true)
    assert.equal((await full.execute('write', { file_path: 'inside.txt' })).ok, false)
    assert.equal(full.approvalRequests.length, 0)
  })

  test('an approval response that bypasses the answerer cannot grant execution', async () => {
    const h = makeHarness({ cwd: workspace, approvalBypass: true })
    sandbox.apply(h.ctx, { approvalPolicy: 'untrusted' })
    const result = await h.execute('write', { file_path: 'inside.txt' })
    assert.match(result.reason, /No approval/)
  })

  test('a pending approval is rechecked against Plan at dispatch', async () => {
    const h = makeHarness({ cwd: workspace, onHuman() {
      h.ctx.planMode.set(h.agent, true)
      return 'allowed-once'
    } })
    sandbox.apply(h.ctx, { approvalPolicy: 'untrusted' })
    const result = await h.execute('write', { file_path: 'inside.txt' })
    assert.match(result.reason, /Plan is read-only/)
  })

  test('a linked directory resolving outside the workspace cannot receive writes', async () => {
    const h = makeHarness({ cwd: workspace })
    sandbox.apply(h.ctx)
    const destination = join(outside, 'alias.txt')
    const result = await h.execute('write', { file_path: join('outside-link', 'alias.txt') }, () => write(destination))
    assert.equal(result.ok, false)
    assert.equal(exists(destination), false)
    assert.equal(h.humanRequests.length, 1)
  })

  test('a separately executing model provider is rejected while restricted', async () => {
    const h = makeHarness({ cwd: workspace })
    collaboration.apply(h.ctx)
    h.command('collab', 'plan')
    assert.equal((await h.step([], { provider: 'external-executor' })).kind, 'reject')
    assert.equal((await h.step([], { provider: 'deepseek-official' })).kind, 'enter')
    h.command('collab', 'default')
    assert.equal((await h.step([], { provider: 'external-executor' })).kind, 'enter')
  })
}
