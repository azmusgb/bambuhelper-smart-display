#!/usr/bin/env node
// Copied into each app by appliance-ui's sync. Counts what an app wrote by hand instead of taking from the kit
// (Pi Hub amendment A22 1.5), and fails when a count is not the one in the app's baseline: a ratchet, never a rewrite.
//   node literals.mjs <folder>… [--baseline <file>] [--allow <file>] [--list] [--write-baseline] [--remeasure]
// <folder>…          the app's own interface, relative to where this runs (Pi Hub: hub/static). The kit's own folder
//                    (the one this file is in), node_modules and dot-folders are skipped.
// --baseline         .kit-literals-baseline.json: { kit, files: { "<path>": { "<category>": count } } }
// --allow            .kit-literals-allow.json: { files: [globs: art or third-party code, not interface],
//                    names: [per-instance custom properties, "*" allowed] }. Missing means none.
// --list             print every finding as path:line  category  text
// --write-baseline   write lower counts, and files that are gone; refuses to write a higher one
// --remeasure        write whatever is measured; only when the baseline was measured by another kit version
// Exit 0 when every count equals the baseline, 1 when one rose or fell (a fall must be written back), 2 for usage, a
// missing baseline or an unreadable file.
//
// What it reads. A .css file, a <style> block and a style="…" attribute: every category. A script (.js, .mjs, .cjs,
// <script>): colour literals anywhere, and its style="…" attributes for the rest. A page (.html) outside those: colour
// literals in fill, stroke, color, stop-color, flood-color, bgcolor and content attributes.
// What it cannot see: a size a script sets through element.style, and a colour a script builds from numbers. It is a
// text scan, not a parser, so it runs in well under a second; in a script, "#fed" as an element's id reads as a colour.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const CATEGORIES = ['colour', 'type', 'space', 'radius', 'shadow', 'motion', 'layer', 'name'];
const NAMED = new Set(('aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown burlywood '
  + 'cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey '
  + 'darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey '
  + 'darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite '
  + 'gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush lawngreen lemonchiffon '
  + 'lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue '
  + 'lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid '
  + 'mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin '
  + 'navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip '
  + 'peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown seagreen seashell sienna '
  + 'silver skyblue slateblue slategray slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke '
  + 'yellow yellowgreen').split(' '));
const COLOUR_PROP = /^(color|background(-color|-image)?|border(-(top|right|bottom|left|inline|block)(-(start|end))?)?(-color)?|outline(-color)?|fill|stroke|box-shadow|text-shadow|caret-color|accent-color|text-decoration(-color)?|column-rule(-color)?|scrollbar-color|stop-color|flood-color)$/;
const SPACE_PROP = /^((margin|padding|inset)(-.+)?|(grid-)?((row|column)-)?gap)$/;
const HEX = /(?<![\w&])#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3,4})(?![\w-])/gi;
const COLOUR_FN = /(?<![\w-])(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/gi;
// In a script, lab( or color( is as likely a function of the app's own, so only the four that A22 names count there.
const SCRIPT_COLOUR_FN = /(?<![\w.$-])(?:rgba?|hsla?)\(/gi;
const LENGTH = /(?<![\w.])-?(?:\d*\.)?\d+(?:px|rem|em)\b/g;

// Same length, same line breaks: what a pattern matches becomes spaces, so offsets still give the line.
const blank = (text, re, keep = 0) => text.replace(re, m => m.slice(0, keep) + m.slice(keep).replace(/[^\n]/g, ' '));
const lineAt = (text, i) => { let n = 1; for (let k = text.indexOf('\n'); k >= 0 && k < i; k = text.indexOf('\n', k + 1)) n++; return n; };
const nonZero = (value, re) => (value.match(re) || []).some(n => parseFloat(n) !== 0);
const glob = (pattern, star) => new RegExp('^' + pattern.split('**').map(part => part.split('*')
  .map(s => s.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join(star)).join('.*') + '$');

function colours(text, add, at, fn = COLOUR_FN) {
  for (const re of [HEX, fn]) for (const m of text.matchAll(re)) add('colour', at + m.index, m[0]);
}

// One declaration, "property: value". skipColour is for a script's style attribute, whose colours the script's own
// scan has already counted.
function declaration(decl, at, add, names, skipColour) {
  const m = /^(\s*)([-\w]+)\s*:([\s\S]*)$/.exec(decl);
  if (!m) return;
  const prop = m[2].toLowerCase(), where = at + m[1].length, show = decl.trim().replace(/\s+/g, ' ').slice(0, 80);
  const value = m[3].toLowerCase().replace(/!important/, '');
  const hit = cat => add(cat, where, show);
  if (!skipColour) {
    colours(m[3], add, at + decl.indexOf(':') + 1);
    if (COLOUR_PROP.test(prop)) for (const w of value.replace(/--[\w-]+/g, ' ').split(/[^a-z-]+/)) if (NAMED.has(w)) hit('colour');
  }
  if (prop.startsWith('--')) { if (!prop.startsWith('--ui-') && !names.some(re => re.test(prop))) hit('name'); return; }
  const bare = value.replace(/--[\w-]+/g, ' ').replace(HEX, ' ');  // no custom-property names, no hex digits
  if ((prop === 'font-size' || prop === 'font') && nonZero(bare, LENGTH)) hit('type');
  if (SPACE_PROP.test(prop) && nonZero(bare, LENGTH)) hit('space');
  if (prop.includes('radius') && (bare.match(/(?<![\w.])-?(?:\d*\.)?\d+(?:%|[a-z]+)?/g) || []).some(n => parseFloat(n) !== 0 && n !== '50%')) hit('radius');
  if (prop === 'box-shadow' && !/^\s*(none|inherit|initial|unset|revert|(var\([^()]*\)\s*,?\s*)+)\s*$/.test(value)) hit('shadow');
  if (/^(transition|animation)(-|$)/.test(prop)) {
    const timed = nonZero(bare, /(?<![\w.])(?:\d*\.)?\d+m?s\b/g), curve = /(?<![\w-])(cubic-bezier|steps|linear)\(/.test(bare);
    const word = /^(transition|animation|.*-timing-function)$/.test(prop) && /(?<![\w-])(ease|ease-in|ease-out|ease-in-out|linear|step-start|step-end)(?![\w(-])/.test(bare);
    if (timed || curve || word) hit('motion');
  }
  if (prop === 'z-index' && (bare.match(/-?\d+/g) || []).some(n => !['0', '1', '-1'].includes(n))) hit('layer');
}

function declarations(text, at, add, names, skipColour) {
  let start = 0;
  for (let i = 0; i <= text.length; i++) {
    if (i === text.length || text[i] === ';') { declaration(text.slice(start, i), at + start, add, names, skipColour); start = i + 1; }
  }
}

export function scanCss(source, add, names = [], at = 0) {
  const text = blank(blank(blank(source, /\/\*[\s\S]*?\*\//g), /url\((?:"[^"]*"|'[^']*'|[^)]*)\)/gi, 4), /"[^"\n]*"|'[^'\n]*'/g, 1);
  let start = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '{') start = i + 1;  // what came before was a selector or an at-rule's condition
    else if (c === ';' || c === '}') { if (!/^\s*@/.test(text.slice(start, i))) declaration(text.slice(start, i), at + start, add, names, false); start = i + 1; }
  }
}

const STYLE_ATTR = /\bstyle\s*=\s*(\\?["'])([\s\S]*?)\1/gi;
export function scanScript(source, add, names = [], at = 0) {
  const text = blank(source, /(^|\s)\/\/[^\n]*/g);  // line comments; "https://" keeps its colon in front
  colours(text, add, at, SCRIPT_COLOUR_FN);
  for (const m of text.matchAll(STYLE_ATTR)) {
    let css = m[2]; for (let prev; prev !== css;) { prev = css; css = css.replace(/\$\{[^{}]*\}/g, s => 'var(--x)'.padEnd(s.length)); }
    declarations(css, at + m.index + m[0].indexOf(m[2]), add, names, true);
  }
}

export function scanHtml(source, add, names = []) {
  let text = source.replace(/<!--[\s\S]*?-->/g, m => m.replace(/[^\n]/g, ' '));
  for (const [re, scan] of [[/(<style\b[^>]*>)([\s\S]*?)<\/style>/gi, scanCss], [/(<script\b[^>]*>)([\s\S]*?)<\/script>/gi, scanScript]]) {
    for (const m of text.matchAll(re)) scan(m[2], add, names, m.index + m[1].length);
    text = text.replace(re, m => m.replace(/[^\n]/g, ' '));
  }
  for (const m of text.matchAll(/\sstyle\s*=\s*("([^"]*)"|'([^']*)')/gi)) declarations(m[2] ?? m[3], m.index + m[0].indexOf(m[1]) + 1, add, names, false);
  for (const m of text.matchAll(/\s(?:fill|stroke|color|stop-color|flood-color|bgcolor|content)\s*=\s*("([^"]*)"|'([^']*)')/gi)) colours(m[2] ?? m[3], add, m.index + m[0].indexOf(m[1]) + 1);
}

const KINDS = { '.css': scanCss, '.html': scanHtml, '.htm': scanHtml, '.js': scanScript, '.mjs': scanScript, '.cjs': scanScript };

// Every finding in one file's text: [{ category, line, text }], in the order they appear.
export function scanText(name, source, names = []) {
  const scan = KINDS[path.extname(name).toLowerCase()], found = [];
  if (scan) scan(source, (category, i, text) => found.push({ category, line: lineAt(source, i), text }), names);
  return found.sort((a, b) => a.line - b.line || CATEGORIES.indexOf(a.category) - CATEGORIES.indexOf(b.category));
}

const tally = found => { const c = {}; for (const f of found) c[f.category] = (c[f.category] || 0) + 1; return c; };

// What differs between what was measured and the baseline: [{ file, category, have, want, kind }], by file then category.
// kind: 'rise' (fails), 'new' (a file the baseline doesn't know starts at zero), 'fall' and 'gone' (write them back).
export function compare(measured, baseline) {
  const out = [];
  for (const file of [...new Set([...Object.keys(measured), ...Object.keys(baseline)])].sort()) {
    for (const category of CATEGORIES) {
      const have = measured[file]?.[category] || 0, want = baseline[file]?.[category] || 0;
      if (have === want) continue;
      out.push({ file, category, have, want, kind: have > want ? (file in baseline ? 'rise' : 'new') : (file in measured ? 'fall' : 'gone') });
    }
  }
  return out;
}

const walk = (dir, skip) => fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1)).flatMap(e => {
  const p = path.join(dir, e.name);
  if (e.name.startsWith('.') || e.name === 'node_modules' || skip(p)) return [];
  return e.isDirectory() ? walk(p, skip) : (path.extname(e.name).toLowerCase() in KINDS ? [p] : []);
});

function kitVersion(here) {
  for (const [file, key] of [['VERSION', 'version'], ['../tokens.json', 'version']]) {
    try { const v = JSON.parse(fs.readFileSync(path.join(here, file), 'utf8'))[key]; if (typeof v === 'string') return v; } catch { /* next */ }
  }
  return null;
}

const usage = 'usage: literals.mjs <folder>… [--baseline <file>] [--allow <file>] [--list] [--write-baseline] [--remeasure]';
const fail = message => Object.assign(new Error(message), { usage: true });
function readJson(file, what) {
  let text;
  try { text = fs.readFileSync(file, 'utf8'); } catch { return undefined; }
  try { return JSON.parse(text); } catch (e) { throw fail(`${what} ${file} is not JSON: ${e.message}`); }
}
const isCounts = v => v && typeof v === 'object' && !Array.isArray(v)
  && Object.entries(v).every(([k, n]) => CATEGORIES.includes(k) && Number.isInteger(n) && n > 0);

// opts (for tests): cwd, out, err, here (the folder this file is in), kit (its version).
export function main(argv, opts = {}) {
  const out = opts.out ?? (line => console.log(line)), err = opts.err ?? (line => console.error(line));
  try { return run(argv, { cwd: process.cwd(), here: path.dirname(fileURLToPath(import.meta.url)), ...opts, out, err }); }
  catch (e) { if (!e.usage) throw e; err(e.message); return 2; }
}

function run(argv, { cwd, here, out, err, kit = kitVersion(here) }) {
  const flags = new Set(), roots = [], named = { '--baseline': '.kit-literals-baseline.json', '--allow': '.kit-literals-allow.json' }, given = new Set();
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a in named) { if (!argv[i + 1] || argv[i + 1].startsWith('--')) throw fail(usage); named[a] = argv[++i]; given.add(a); }
    else if (['--list', '--write-baseline', '--remeasure'].includes(a)) flags.add(a);
    else if (a.startsWith('--')) throw fail(usage);
    else roots.push(a);
  }
  if (!roots.length) throw fail(usage);
  const baselineFile = path.resolve(cwd, named['--baseline']), allowFile = path.resolve(cwd, named['--allow']);

  const allow = readJson(allowFile, 'the allow list');
  if (allow === undefined && given.has('--allow')) throw fail(`the allow list ${allowFile} is missing`);
  const { files: allowFiles = [], names: allowNames = [], ...rest } = allow ?? {};
  const strings = v => Array.isArray(v) && v.every(s => typeof s === 'string' && s);
  if (Object.keys(rest).length || !strings(allowFiles) || !strings(allowNames) || allowNames.some(n => !n.startsWith('--'))) {
    throw fail(`the allow list ${allowFile} must be { "files": [paths], "names": ["--name"] } and nothing else`);
  }
  const art = allowFiles.map(p => glob(p, '[^/]*')), names = allowNames.map(n => glob(n, '[a-z0-9_-]*'));

  const rel = p => path.relative(cwd, p).split(path.sep).join('/');
  const measured = {}, listed = [];
  for (const root of roots) {
    const dir = path.resolve(cwd, root);
    if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) throw fail(`${root} is not a folder`);
    for (const file of walk(dir, p => path.resolve(p) === path.resolve(here) || art.some(re => re.test(rel(p))))) {
      const found = scanText(file, fs.readFileSync(file, 'utf8'), names);
      if (found.length) measured[rel(file)] = tally(found);
      for (const f of found) listed.push(`${rel(file)}:${f.line}\t${f.category}\t${f.text}`);
    }
  }
  if (flags.has('--list')) for (const line of listed) out(line);

  const stored = readJson(baselineFile, 'the baseline');
  if (stored !== undefined && !(stored && typeof stored === 'object' && stored.files && typeof stored.files === 'object'
    && Object.values(stored.files).every(isCounts))) {
    throw fail(`the baseline ${baselineFile} must be { "kit": "<version>", "files": { "<path>": { "<category>": count } } }`);
  }
  const write = () => {
    const files = Object.fromEntries(Object.keys(measured).sort().map(f => [f, Object.fromEntries(CATEGORIES.filter(c => measured[f][c]).map(c => [c, measured[f][c]]))]));
    fs.writeFileSync(baselineFile, JSON.stringify({ kit, files }, null, 2) + '\n');
  };
  const totals = CATEGORIES.map(c => `${c} ${Object.values(measured).reduce((n, f) => n + (f[c] || 0), 0)}`).join(', ');
  const say = d => `${d.file}: ${d.category} ${d.have}, the baseline says ${d.want}`;

  if (flags.has('--remeasure')) {
    if (stored && stored.kit === kit) throw fail(`--remeasure is only for a baseline measured by another kit version; this one is v${kit}. Use --write-baseline.`);
    write(); out(`kit literals: baseline measured again with v${kit} (${totals})`); return 0;
  }
  if (stored === undefined) {
    if (!flags.has('--write-baseline')) throw fail(`no baseline at ${baselineFile}; write the first one with --write-baseline`);
    write(); out(`kit literals: first baseline written (${totals})`); return 0;
  }
  const diffs = compare(measured, stored.files), up = diffs.filter(d => d.kind === 'rise' || d.kind === 'new');
  if (flags.has('--write-baseline')) {
    if (up.length) { err('kit literals: not written, because a count would go up. Use the kit\'s value instead:'); for (const d of up) err('  ' + say(d)); return 1; }
    write(); out(`kit literals: baseline written, ${diffs.length} count${diffs.length === 1 ? '' : 's'} lower (${totals})`); return 0;
  }
  if (!diffs.length) { out(`kit literals: ${Object.keys(measured).length} files match the baseline (${totals})`); return 0; }
  const gone = new Set();
  for (const d of diffs) {
    if (d.kind === 'gone') { if (gone.has(d.file)) continue; gone.add(d.file); }
    err(d.kind === 'rise' ? `${say(d)}. Use the kit's value instead (--list shows each one).`
      : d.kind === 'new' ? `${say(d)}: a new file starts at zero. Use the kit's value instead (--list shows each one).`
        : d.kind === 'gone' ? `${d.file} is gone but still in the baseline. Write the baseline back: --write-baseline.`
          : `${say(d)}. Lower the baseline in the same change: --write-baseline.`);
  }
  return 1;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) process.exit(main(process.argv.slice(2)));
