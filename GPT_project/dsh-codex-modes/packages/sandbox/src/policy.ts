import { lstatSync, realpathSync } from 'node:fs'
import { basename, dirname, isAbsolute, join, parse, resolve, sep } from 'node:path'
import { argsOf, isDialogueTool, isReadTool } from '../../../src/tools.js'

export const sandboxModes = ['read-only', 'workspace-write', 'danger-full-access']
export const approvalPolicies = ['untrusted', 'on-request', 'never']
const sensitive = /^(?:\.env(?:\..*)?|\.ssh|\.aws|\.gnupg|\.git|\.npmrc|\.netrc|\.kube|credentials(?:\.json)?|id_(?:ed25519|ecdsa|rsa)(?:\.pub)?)$/i
const device = /^(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)/i

function effectOf(call) {
  if (isDialogueTool(call)) return 'dialogue'
  if (isReadTool(call)) return 'read'
  if (call.name === 'write' || call.name === 'edit') return 'write'
  if (call.name === 'todo_write') return 'session'
  return 'opaque'
}

function pathArgument(name, args) {
  return ['glob', 'grep', 'str_replace_editor'].includes(name) ? args.path : args.file_path
}

function protectedPath(path) {
  return path.split(/[/\\]+/).some(part => sensitive.test(part))
}

function verifiedSpelling(raw) {
  if (!raw.trim() || raw.includes('\0') || raw.startsWith('~')) return false
  if (sep !== '\\') return true
  const root = parse(raw).root
  if (root && !/^[a-z]:[/\\]$/i.test(root)) return false
  return raw.slice(root.length).split(/[/\\]+/).every(part => part === '.' || part === '..' ||
    !/[:*?"<>|]|[. ]$/.test(part) && !device.test(part))
}

function canonicalTarget(path, writing) {
  let ancestor = path
  const suffix = []
  while (true) {
    let info
    try {
      info = lstatSync(ancestor)
    } catch (error) {
      const parent = dirname(ancestor)
      if (error.code !== 'ENOENT' || parent === ancestor) throw error
      suffix.unshift(basename(ancestor))
      ancestor = parent
      continue
    }
    if (writing && ancestor === path && (!info.isFile() || info.nlink !== 1)) {
      throw new Error('Unsafe existing write target')
    }
    return join(realpathSync.native(ancestor), ...suffix)
  }
}

function within(path, root) {
  return path === root || path.startsWith(root.endsWith(sep) ? root : root + sep)
}

export function assess(call, sandbox, isLocalFs) {
  const args = argsOf(call)
  const effect = effectOf(call)
  const evidence = {
    tool: call.name,
    effect,
    sandbox,
    sensitive: false,
    destructive: /(?:^|_)(?:delete|remove|unlink|rmdir|trash)(?:_|$)/i.test(call.name) ||
      call.name === 'apply_patch' && Object.values(args).some(value => typeof value === 'string' && /^\*\*\* Delete File:/m.test(value)),
    outside: false,
    unverified: false,
    escalation: args.sandbox_permissions !== undefined || args.justification !== undefined,
  }

  if (effect === 'read' || effect === 'write') {
    const workspace = call.agent?.session.header.cwd
    const implicitRoot = (call.name === 'glob' || call.name === 'grep') && args.path === undefined
    const raw = implicitRoot ? workspace : pathArgument(call.name, args)
    if (typeof raw === 'string') evidence.sensitive = protectedPath(raw)
    try {
      if (!isLocalFs || typeof raw !== 'string' || !verifiedSpelling(raw) || (!workspace && !isAbsolute(raw))) {
        throw new Error('Filesystem location cannot be verified')
      }
      const target = canonicalTarget(resolve(workspace ?? process.cwd(), raw), effect === 'write')
      evidence.sensitive ||= protectedPath(target)
      evidence.outside = !workspace || !within(target, realpathSync.native(workspace))
    } catch {
      evidence.unverified = true
    }
  }

  let denial
  if (evidence.escalation) denial = 'Tool-supplied sandbox escalation is disabled by this profile.'
  else if (sandbox !== 'danger-full-access') {
    if (effect === 'opaque') denial = 'This tool has no verified confinement in the selected sandbox.'
    else if (evidence.sensitive) denial = 'The operation targets a protected path.'
    else if (effect === 'read' && evidence.unverified) denial = 'The local read target could not be verified.'
    else if (sandbox === 'read-only' && (effect === 'write' || effect === 'session')) denial = 'The sandbox is read-only.'
    else if (effect === 'write' && (evidence.outside || evidence.unverified)) denial = 'The write target is outside the verified workspace.'
  }
  return { evidence, denial }
}

export function needsApproval(assessment, policy) {
  if (policy === 'never') return false
  if (assessment.denial) return true
  if (policy !== 'untrusted') return false
  const { effect, sensitive } = assessment.evidence
  return effect === 'write' || effect === 'session' || effect === 'opaque' || sensitive
}
