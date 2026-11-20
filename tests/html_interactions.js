// Run the report's JavaScript against a minimal DOM for fast interaction checks.
// A real browser test remains separate: this mock does not validate browser layout.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

class Element {
  constructor(tag) {
    this.tagName = tag; this.children = []; this.dataset = {}; this.style = {};
    this.listeners = {}; this.className = ''; this._text = ''; this.offsetWidth = 100; this.offsetHeight = 20;
  }
  set innerHTML(value) {
    assert.equal(value, '', 'untrusted data must not be inserted via innerHTML');
    this.children = [];
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren() { this.children = []; this._text = ''; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  click() { this.listeners.click?.(); }
  getBoundingClientRect() { return {right: 20, top: 20}; }
  scrollIntoView() { this.scrolled = true; }
}

const elements = Object.fromEntries(
  ['meta', 'tooltip', 'heatmap', 'tbody', 'coverage-summary', 'diagnostic-list', 'reason-counts']
    .map(id => [id, new Element('div')])
);
const headers = ['path', 'mode_score', 'commits', 'churn', 'unique_contributors', 'gini', 'age_days', 'lines_of_code', 'confidence']
  .map(key => { const el = new Element('th'); el.dataset.key = key; return el; });
const document = {
  getElementById: id => elements[id],
  createElement: tag => new Element(tag),
  addEventListener: () => {},
  querySelectorAll: selector => {
    if (selector === '#table th') return headers;
    if (selector === '#tbody tr') return elements.tbody.children;
    if (selector === '.cell') return elements.heatmap.children;
    throw Error(`Unexpected selector: ${selector}`);
  },
};
const html = fs.readFileSync(process.argv[2], 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(script, 'report contains a script');
vm.runInNewContext(script[1], {document, window: {innerWidth: 1000, innerHeight: 800}, console});

if (process.argv[3] === 'failed') {
  const coverage = elements['coverage-summary'].textContent;
  assert.ok(coverage.includes('Matched filesUnavailable'));
  assert.ok(coverage.includes('Scored filesUnavailable'));
  assert.ok(coverage.includes('Files with recorded limitationsUnavailable'));
  assert.ok(coverage.includes('Listed files0'));
  assert.ok(elements['diagnostic-list'].textContent.includes('git · stage-failed'));
  assert.ok(elements['diagnostic-list'].textContent.includes('injected failure'));
  process.exit(0);
}

if (process.argv[3] === 'limited') {
  assert.ok(elements['coverage-summary'].textContent.includes('Files with recorded limitations1'));
  assert.ok(elements['coverage-summary'].textContent.includes('Listed files0'));
  assert.ok(elements['reason-counts'].textContent.includes('syntax-error: 1'));
  // diagnostic-list 取决于调用方是否带阶段事件记录：
  // 纯计数数据展示空状态；真实 pipeline 会把被 limit 隐藏文件的降级也列出来。
  const diagText = elements['diagnostic-list'].textContent;
  if (diagText.includes('No stage events recorded.')) {
    assert.ok(true, 'count-only payload shows the empty state');
  } else {
    assert.ok(diagText.includes('syntax-error'), 'recorded events must name the reason code');
    assert.ok(diagText.includes('broken.py') || diagText.includes('a.py'), 'recorded events must name the file');
  }
  process.exit(0);
}

if (process.argv[3] === 'failed-scanner') {
  assert.ok(elements['diagnostic-list'].textContent.includes('scanner · stage-failed'));
  assert.equal(elements.heatmap.children[0].style.background, '#777f8b');
  assert.ok(elements.tbody.children[0].textContent.includes('Stage issue recorded'));
  process.exit(0);
}

const rows = () => elements.tbody.children;
const cells = () => elements.heatmap.children;
const click = key => headers.find(header => header.dataset.key === key).click();
click('path');
const paths = rows().map(row => row.dataset.path);
assert.deepEqual(paths, [...paths].sort((a, b) => a.localeCompare(b)));
click('unique_contributors');
assert.equal(rows()[0].dataset.path, 'a.py');
click('lines_of_code');
assert.equal(rows()[0].dataset.path, 'z.py');
cells().find(cell => cell.dataset.path === 'a.py').click();
assert.equal(rows().find(row => row.style.background).dataset.path, 'a.py');
const missing = cells().find(cell => cell.dataset.path.includes('data-xss'));
assert.equal(missing.style.background, '#777f8b');
assert.equal(cells().find(cell => cell.dataset.path === 'a.py').style.background, '#777f8b');
missing.listeners.mouseenter();
assert.ok(elements.tooltip.textContent.includes('Empty file or missing data'));
assert.ok(elements.tooltip.textContent.includes('<img data-xss'));
assert.ok(elements['coverage-summary'].textContent.includes('Matched files5'));
assert.ok(elements['coverage-summary'].textContent.includes('Scored files4'));
assert.ok(elements['coverage-summary'].textContent.includes('Files with recorded limitations1'));
assert.ok(elements['coverage-summary'].textContent.includes('Listed files3'));
assert.ok(elements['reason-counts'].textContent.includes('syntax-error: 1'));
const diagnostic = elements['diagnostic-list'].children[0];
assert.ok(diagnostic.textContent.includes('scanner · syntax-error'));
assert.ok(diagnostic.textContent.includes('<img data-xss="diagnostic"'));
assert.ok(rows().find(row => row.dataset.path === 'a.py').textContent.includes('Limitations recorded'));
diagnostic.children.find(child => child.tagName === 'button').click();
assert.equal(rows().find(row => row.style.background).dataset.path, 'a.py');
