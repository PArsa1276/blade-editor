#!/usr/bin/env node
// One-command install: `npx blade-editor` (or `npx github:PArsa1276/blade-editor`).
// Runs the platform installer from this package: Python + ffmpeg checks, Blade Editor in its own
// environment, the MCP entry in the Claude settings, the skills, the Chrome extension, Kinetograph.
const { spawnSync } = require('child_process');
const path = require('path');

const root = path.join(__dirname, '..');
const args = process.argv.slice(2);
if (args.includes('--help') || args.includes('-h')) {
  console.log('Usage: npx blade-editor\n\nInstalls the Blade Editor MCP server and skills for Claude ' +
              '(Claude app, Claude Code, Claude Desktop). Quit the Claude app first; open it again after.');
  process.exit(0);
}
const win = process.platform === 'win32';
const cmd = win ? 'powershell' : 'bash';
const cmdArgs = win
  ? ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(root, 'install.ps1')]
  : [path.join(root, 'install.sh')];
console.log('Blade Editor: installing from ' + root);
const r = spawnSync(cmd, cmdArgs, { cwd: root, stdio: 'inherit' });
if (r.error) {
  console.error('Could not start ' + cmd + ': ' + r.error.message);
  process.exit(1);
}
process.exit(r.status === null ? 1 : r.status);
