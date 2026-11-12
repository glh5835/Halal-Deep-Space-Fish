import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import * as product from '../lib/product/index.js'
import * as collaboration from '../lib/collaboration/index.js'
import * as sandbox from '../lib/sandbox/index.js'
import { makeHarness } from './harness.mjs'
import { addScenarios } from './scenarios.mjs'

const fixture = mkdtempSync(join(tmpdir(), 'dsh-codex-modes-test-'))
const workspace = join(fixture, 'workspace')
const outside = join(fixture, 'other')
mkdirSync(workspace)
mkdirSync(outside)
symlinkSync(outside, join(workspace, 'outside-link'), process.platform === 'win32' ? 'junction' : 'dir')
after(() => rmSync(fixture, { recursive: true, force: true }))

addScenarios(test, assert, {
  product, collaboration, sandbox, makeHarness, workspace, outside, join,
  exists: existsSync,
  write: path => writeFileSync(path, 'fixture'),
})
