#!/usr/bin/env node
// Copied into each app by appliance-ui's sync. Fails when a shared file was edited or removed by hand:
// change appliance-ui and sync again instead. Usage: node verify.mjs <folder>
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const dir = process.argv[2] || path.dirname(new URL(import.meta.url).pathname);
const v = JSON.parse(fs.readFileSync(path.join(dir, 'VERSION'), 'utf8'));
const bad = Object.entries(v.files).filter(([name, sum]) => {
  try { return crypto.createHash('sha256').update(fs.readFileSync(path.join(dir, name))).digest('hex') !== sum; }
  catch { return true; }
}).map(([name]) => name);
if (bad.length) {
  console.error(`appliance-ui v${v.version}: changed or missing in ${dir}: ${bad.join(', ')}. Edit appliance-ui and sync instead.`);
  process.exit(1);
}
console.log(`appliance-ui v${v.version}: ${Object.keys(v.files).length} files match`);
