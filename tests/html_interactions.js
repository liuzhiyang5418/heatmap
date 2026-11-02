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

const elements = Object.fromEntries(['meta', 'tooltip', 'heatmap', 'tbody'].map(id => [id, new Element('div')]));
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
missing.listeners.mouseenter();
assert.ok(elements.tooltip.textContent.includes('空文件或数据缺失'));
assert.ok(elements.tooltip.textContent.includes('<img data-xss'));
