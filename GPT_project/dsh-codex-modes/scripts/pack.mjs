import { mkdir } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const destination = join(root, 'dist')
await mkdir(destination, { recursive: true })
const npm = process.env.npm_execpath
if (!npm) throw new Error('Run this script with npm run pack:all')

function run(args, cwd = root) {
  const result = spawnSync(process.execPath, args, { cwd, stdio: 'inherit' })
  if (result.status !== 0) process.exit(result.status ?? 1)
}

run([join(root, 'scripts/build.mjs'), '--check'])
for (const path of ['.', 'packages/product', 'packages/collaboration', 'packages/sandbox']) {
  run([npm, 'pack', '--pack-destination', destination, '--quiet'], join(root, path))
}
