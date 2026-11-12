export {}
declare const window: { __ModuleLoader__: any }
// Runtime source
window.__ModuleLoader__.load({
  id: '__PACKAGE_ID__',
  factory(require) {
    const React = require('react')
    const h = React.createElement
    const slot = 'conversation.input.plan'

    function ModeSelect({ useProjection, locked, switchTo }) {
      const plan = useProjection('plan')
      const [pending, setPending] = React.useState(null)
      const [error, setError] = React.useState('')
      if (!plan) return null
      const current = (plan.pending ? !plan.active : plan.active) ? 'plan' : 'default'

      return h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: '6px' } },
        h('select', {
          'aria-label': 'Collaboration mode',
          title: 'Collaboration mode',
          value: pending ?? current,
          disabled: locked || pending !== null,
          style: {
            color: 'var(--dsw-alias-label-primary)',
            background: 'var(--dsw-alias-bg-module-platform)',
            borderRadius: '6px',
            padding: '3px 5px',
          },
          onChange: async event => {
            const mode = event.currentTarget.value
            setPending(mode)
            setError('')
            try {
              await switchTo(mode)
            } catch (failure) {
              setError(failure instanceof Error ? failure.message : 'Mode switch failed.')
            } finally {
              setPending(null)
            }
          },
        }, h('option', { value: 'default' }, 'Default'), h('option', { value: 'plan' }, 'Plan')),
        error && h('span', { role: 'alert' }, error))
    }

    return {
      inject: ['slots', 'remote', 'remote.commands'],
      apply(ctx) {
        ctx.slots.inject(slot, () => ctx.slots.register({
          name: slot,
          priority: -1,
          inject: sessionId => ({
            async switchTo(mode) {
              const reply = await ctx.remote.commands.execute(sessionId, '/collab ' + mode, [])
              if (!reply.ok) throw new Error(reply.error.message)
              if (reply.value?.result?.kind !== 'success') throw new Error(reply.value?.result?.text ?? 'The collaboration command is unavailable.')
            },
          }),
        }, ModeSelect))
      },
    }
  },
})
