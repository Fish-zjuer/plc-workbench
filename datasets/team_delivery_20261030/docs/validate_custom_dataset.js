#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function parseArgs(argv) {
  const options = { root: null, backup: null, positional: [] };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--root') options.root = argv[++i];
    else if (argv[i] === '--backup') options.backup = argv[++i];
    else options.positional.push(argv[i]);
  }
  if (!options.root && options.positional[0]) options.root = options.positional[0];
  if (!options.backup && options.positional[1]) options.backup = options.positional[1];
  return options;
}

const options = parseArgs(process.argv.slice(2));
const root = path.resolve(options.root || path.join(__dirname, '..'));
const backup = options.backup ? path.resolve(options.backup) : null;
const customDir = path.join(root, '自建题(1)', '自建题');
const specDir = path.join(root, '32题测试与规约', '32题测试与规约');
const docsDir = path.join(root, 'docs');

const finalFile = path.join(customDir, '自建题库_最终12题.json');
const metaFile = path.join(customDir, '自建题库_溯源与评测资料.json');
const mapFile = path.join(customDir, '题号映射.json');
const ltlFile = path.join(specDir, '自建12题_LTL规约.json');
const testFile = path.join(specDir, '自建12题_测试用例.json');
const usageFile = path.join(specDir, '使用说明.md');
const reportFile = path.join(docsDir, 'custom_dataset_audit.md');

const results = [];
function pass(name, detail = '') { results.push({ status: 'PASS', name, detail }); }
function fail(name, detail = '') { results.push({ status: 'FAIL', name, detail }); }
function skip(name, detail = '') { results.push({ status: 'SKIP', name, detail }); }
function check(name, ok, detail = '') { (ok ? pass : fail)(name, detail); }
function read(file) { return fs.readFileSync(file, 'utf8'); }
function json(file) { return JSON.parse(read(file)); }
function shaText(text) { return crypto.createHash('sha256').update(text, 'utf8').digest('hex'); }
function shaFile(file) { return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'); }
function stable(value) {
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stable(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}
function flattenBank(bank) {
  return ['easy', 'medium', 'hard'].flatMap(bucket =>
    (bank[bucket] || []).map((item, index) => ({ bucket, index, ...item })));
}
function walk(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(file) : [file];
  });
}
function withoutTitle(task) {
  const copy = JSON.parse(JSON.stringify(task));
  delete copy.title;
  return copy;
}
function interfaceTriples(markdown) {
  return markdown.split(/\r?\n/).map(line => {
    const match = line.match(/^\|\s*(Input|Output)\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|/);
    return match ? { direction: match[1], name: match[2], type: match[3] } : null;
  }).filter(Boolean);
}
function idsOf(items) { return items.map(item => item.id).sort(); }

check('交付目录结构完整', [customDir, specDir, docsDir].every(fs.existsSync), root);

const jsonFiles = walk(customDir).concat(walk(specDir)).filter(file => file.endsWith('.json'));
for (const file of jsonFiles) {
  try {
    JSON.parse(read(file));
    pass(`JSON可解析: ${path.relative(root, file)}`);
  } catch (error) {
    fail(`JSON可解析: ${path.relative(root, file)}`, error.message);
  }
}

let finalBank;
let metaBank;
let mapping;
let ltl;
let tests;
try {
  finalBank = json(finalFile);
  metaBank = json(metaFile);
  mapping = json(mapFile);
  ltl = json(ltlFile);
  tests = json(testFile);
} catch (error) {
  fail('核心数据载入', error.message);
}

if (finalBank && metaBank && mapping && ltl && tests) {
  const expectedIds = Array.from({ length: 12 }, (_, index) => `CUSTOM_${String(index + 1).padStart(2, '0')}`);
  const finalItems = flattenBank(finalBank);
  const metaItems = flattenBank(metaBank);
  const metaById = new Map(metaItems.map(item => [item.id, item]));
  const ltlById = new Map(ltl.tasks.map(task => [task.id, task]));
  const testById = new Map(tests.tasks.map(task => [task.id, task]));

  const idSetsOk = stable(idsOf(metaItems)) === stable(expectedIds)
    && stable(idsOf(mapping)) === stable(expectedIds)
    && stable(idsOf(ltl.tasks)) === stable(expectedIds)
    && stable(idsOf(tests.tasks)) === stable(expectedIds)
    && new Set(idsOf(metaItems)).size === 12;
  check('CUSTOM_01～CUSTOM_12在元数据、映射、LTL和测试中无缺失或重复', idSetsOk);

  let mappingOk = mapping.length === 12 && finalItems.length === 12;
  let englishOk = true;
  let interfaceOk = true;
  let titleOk = true;
  const finalMd = read(path.join(customDir, '自建题库_最终12题.md'));
  const ltlMd = read(path.join(specDir, '自建12题_LTL规约.md'));
  const indexMd = read(path.join(specDir, '测试用例索引.md'));

  for (const row of mapping) {
    const item = finalBank[row.bucket] && finalBank[row.bucket][row.index_zero_based];
    const meta = metaById.get(row.id);
    const ltlTask = ltlById.get(row.id);
    const testTask = testById.get(row.id);
    mappingOk = mappingOk && Boolean(item) && Boolean(meta)
      && row.input_path === `${row.bucket}[${row.index_zero_based}].en`
      && meta.difficulty === row.bucket;
    englishOk = englishOk && Boolean(item) && Boolean(meta)
      && meta.en === item.en && shaText(item.en) === row.en_sha256;
    const expectedInterface = (meta.interface || []).map(field => ({
      direction: field.direction, name: field.name, type: field.type
    }));
    interfaceOk = interfaceOk && expectedInterface.length > 0
      && stable(interfaceTriples(item.en)) === stable(expectedInterface);
    const title = row.title_zh;
    const ltlCommentFile = path.join(specDir, '逐题LTL', `${row.id}.ltl`);
    const firstComment = fs.existsSync(ltlCommentFile) ? read(ltlCommentFile).split(/\r?\n/, 1)[0] : '';
    titleOk = titleOk && Boolean(meta) && Boolean(ltlTask) && Boolean(testTask)
      && meta.title_zh === title && meta.zh.startsWith(`# ${title}\n`)
      && ltlTask.title === title && testTask.title === title
      && finalMd.includes(`### ${row.id} ${title}`)
      && ltlMd.includes(`## ${row.id} ${title}`)
      && indexMd.includes(`## ${row.id} ${title}`)
      && (firstComment === `# ${row.id}` || firstComment === `# ${row.id} ${title}`);
  }
  check('题号映射位置和难度分桶正确', mappingOk);
  check('12道英文题面与元数据一致且英文SHA256全部正确', englishOk);
  check('12道接口定义完整且与英文题面逐项一致', interfaceOk);
  check('12道中文标题在元数据、映射、LTL、测试和Markdown中一致', titleOk);

  const ltlCount = ltl.tasks.reduce((sum, task) => sum + task.properties.length, 0);
  check('LTL任务为12道且性质总数为85', ltl.tasks.length === 12 && ltlCount === 85,
    `tasks=${ltl.tasks.length}, properties=${ltlCount}`);
  const scenarioCount = tests.tasks.reduce((sum, task) => sum + task.scenarios.length, 0);
  const scanCount = tests.tasks.reduce((sum, task) =>
    sum + task.scenarios.reduce((count, scenario) => count + scenario.trace.length, 0), 0);
  check('测试任务为12道、场景151组、扫描1313步',
    tests.tasks.length === 12 && scenarioCount === 151 && scanCount === 1313,
    `tasks=${tests.tasks.length}, scenarios=${scenarioCount}, scans=${scanCount}`);

  const auditReference = path.resolve(path.dirname(usageFile), '..', '..', 'docs', 'custom_dataset_audit.md');
  check('使用说明引用的审核报告存在', fs.existsSync(auditReference), path.relative(root, auditReference));
  check('无效的检查与来源记录.json引用已移除', !read(usageFile).includes('检查与来源记录.json'));
  check('审核报告随包交付', fs.existsSync(reportFile), path.relative(root, reportFile));
}

const historicalChecks = [
  '最终英文题库文件与历史版本逐字节一致',
  '12道最终英文题面与历史版本一致',
  '元数据内12道英文题面与历史版本一致',
  '难度分桶与历史版本一致',
  '接口与历史版本一致',
  'LTL公式、观察器、扫描语义和非标题字段与历史版本一致',
  '测试输入、预期输出和非标题字段与历史版本一致',
  '公共20题规约、测试和逐题LTL与历史版本一致',
  '测试索引中的公共20题部分与历史版本一致'
];

const backupCustom = backup && path.join(backup, '自建题');
const backupSpec = backup && path.join(backup, '32题测试与规约');
const validBackup = Boolean(backup && fs.existsSync(backupCustom) && fs.existsSync(backupSpec));

if (!validBackup) {
  const reason = backup
    ? `提供的备份目录无效: ${backup}`
    : '未提供备份目录；如需执行，请使用 --backup <目录>';
  console.log(`历史版本对比未执行：${reason}`);
  for (const name of historicalChecks) skip(name, reason);
} else if (finalBank && metaBank && mapping && ltl && tests) {
  const oldFinalFile = path.join(backupCustom, '自建题库_最终12题.json');
  const oldMetaFile = path.join(backupCustom, '自建题库_溯源与评测资料.json');
  const oldLtlFile = path.join(backupSpec, '自建12题_LTL规约.json');
  const oldTestFile = path.join(backupSpec, '自建12题_测试用例.json');
  try {
    const oldFinalBank = json(oldFinalFile);
    const oldMetaBank = json(oldMetaFile);
    const oldLtl = json(oldLtlFile);
    const oldTests = json(oldTestFile);
    const finalItems = flattenBank(finalBank);
    const metaItems = flattenBank(metaBank);
    const oldFinalItems = flattenBank(oldFinalBank);
    const oldMetaItems = flattenBank(oldMetaBank);
    const metaById = new Map(metaItems.map(item => [item.id, item]));
    const oldMetaById = new Map(oldMetaItems.map(item => [item.id, item]));
    const expectedIds = Array.from({ length: 12 }, (_, index) => `CUSTOM_${String(index + 1).padStart(2, '0')}`);

    check(historicalChecks[0], shaFile(finalFile) === shaFile(oldFinalFile));
    check(historicalChecks[1], stable(finalItems.map(item => item.en)) === stable(oldFinalItems.map(item => item.en)));
    check(historicalChecks[2], expectedIds.every(id => metaById.get(id).en === oldMetaById.get(id).en));
    check(historicalChecks[3], expectedIds.every(id => metaById.get(id).difficulty === oldMetaById.get(id).difficulty));
    check(historicalChecks[4], expectedIds.every(id => stable(metaById.get(id).interface) === stable(oldMetaById.get(id).interface)));
    check(historicalChecks[5], stable(ltl.tasks.map(withoutTitle)) === stable(oldLtl.tasks.map(withoutTitle)));
    check(historicalChecks[6], stable(tests.tasks.map(withoutTitle)) === stable(oldTests.tasks.map(withoutTitle)));

    const publicFiles = [
      '公共20题_LTL规约.json', '公共20题_LTL规约.md', '公共20题_测试用例.json',
      ...Array.from({ length: 20 }, (_, index) => path.join('逐题LTL', `PUBLIC_${String(index + 1).padStart(2, '0')}.ltl`))
    ];
    check(historicalChecks[7], publicFiles.every(relative =>
      shaFile(path.join(specDir, relative)) === shaFile(path.join(backupSpec, relative))));
    const indexMd = read(path.join(specDir, '测试用例索引.md'));
    const oldIndexMd = read(path.join(backupSpec, '测试用例索引.md'));
    check(historicalChecks[8], indexMd.split('## CUSTOM_01')[0] === oldIndexMd.split('## CUSTOM_01')[0]);
  } catch (error) {
    fail('历史版本对比载入', error.message);
  }
}

const passed = results.filter(result => result.status === 'PASS').length;
const failed = results.filter(result => result.status === 'FAIL').length;
const skipped = results.filter(result => result.status === 'SKIP').length;
for (const result of results) {
  console.log(`${result.status}\t${result.name}${result.detail ? `\t${result.detail}` : ''}`);
}
console.log(`SUMMARY\ttotal=${results.length}\tpassed=${passed}\tfailed=${failed}\tskipped=${skipped}`);
if (failed > 0) process.exitCode = 1;
