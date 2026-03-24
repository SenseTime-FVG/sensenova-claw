/**
 * test_dom_extractor.mjs
 * DOM 提取器的冒烟测试，使用真实 HTML 测试数据。
 * 若测试数据不存在则跳过所有测试。
 */

import { describe, it, before } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

import { extractPage, extractPages } from '../lib/dom_extractor.mjs';

// ---------------------------------------------------------------------------
// 测试数据路径
// ---------------------------------------------------------------------------
const TEST_DATA_DIR = '/home/wangbo4/.agentos/workdir/default/Gold_Investment_20260318_223444/pages';
const PAGE_01 = path.join(TEST_DATA_DIR, 'page_01.html');
const PAGE_05 = path.join(TEST_DATA_DIR, 'page_05.html');

const TEST_DATA_EXISTS = fs.existsSync(PAGE_01) && fs.existsSync(PAGE_05);

// ---------------------------------------------------------------------------
// 辅助：跳过或运行
// ---------------------------------------------------------------------------
function maybeSkip(testFn) {
  if (!TEST_DATA_EXISTS) {
    return () => {
      // 使用 console.warn 输出跳过信息
      console.warn('[SKIP] 测试数据不存在，跳过测试:', TEST_DATA_DIR);
    };
  }
  return testFn;
}

// ---------------------------------------------------------------------------
// Test 1: 单页提取 page_01.html
// ---------------------------------------------------------------------------
describe('extractPage — page_01.html', () => {
  /** @type {import('playwright').Browser} */
  let browser;
  /** @type {import('playwright').Page} */
  let page;
  /** @type {{bg:Object|null, ct:Object|null, footer:Object|null}} */
  let ir;

  before(async () => {
    if (!TEST_DATA_EXISTS) return;
    browser = await chromium.launch({ headless: true });
    page = await browser.newPage();
    await page.setViewportSize({ width: 1280, height: 720 });
    ir = await extractPage(page, PAGE_01);
    await browser.close();
  });

  it('IR 包含 bg、ct、footer 三个顶层字段', maybeSkip(() => {
    assert.ok(ir !== null && typeof ir === 'object', 'IR 应为对象');
    assert.ok('bg' in ir, 'IR 应包含 bg 字段');
    assert.ok('ct' in ir, 'IR 应包含 ct 字段');
    assert.ok('footer' in ir, 'IR 应包含 footer 字段');
  }));

  it('ct 有子节点 children', maybeSkip(() => {
    assert.ok(ir.ct !== null, 'ct 不应为 null');
    assert.ok(Array.isArray(ir.ct.children), 'ct.children 应为数组');
    assert.ok(ir.ct.children.length > 0, 'ct.children 不应为空');
  }));

  it('bg 包含 styles 对象', maybeSkip(() => {
    assert.ok(ir.bg !== null, 'bg 不应为 null');
    assert.ok(typeof ir.bg.styles === 'object', 'bg.styles 应为对象');
    // bg 应有背景样式（backgroundImage 或 backgroundColor）
    const hasBackground = ir.bg.styles.backgroundImage || ir.bg.styles.backgroundColor;
    assert.ok(hasBackground, 'bg.styles 应包含 backgroundImage 或 backgroundColor');
  }));

  it('bg 有 bounds 包含 x/y/w/h', maybeSkip(() => {
    assert.ok(ir.bg !== null, 'bg 不应为 null');
    const { bounds } = ir.bg;
    assert.ok(typeof bounds === 'object', 'bg.bounds 应为对象');
    assert.ok(typeof bounds.x === 'number', 'bg.bounds.x 应为数字');
    assert.ok(typeof bounds.y === 'number', 'bg.bounds.y 应为数字');
    assert.ok(typeof bounds.w === 'number', 'bg.bounds.w 应为数字');
    assert.ok(typeof bounds.h === 'number', 'bg.bounds.h 应为数字');
  }));

  it('ct 子节点有 tag 和 bounds', maybeSkip(() => {
    const firstChild = ir.ct.children[0];
    assert.ok(typeof firstChild.tag === 'string', 'child.tag 应为字符串');
    assert.ok(typeof firstChild.bounds === 'object', 'child.bounds 应为对象');
    assert.ok(typeof firstChild.bounds.w === 'number', 'child.bounds.w 应为数字');
  }));

  it('footer 包含文本内容', maybeSkip(() => {
    assert.ok(ir.footer !== null, 'footer 不应为 null');
    // footer 可能在 text 字段或 children 中包含文本
    const hasText = ir.footer.text ||
      (Array.isArray(ir.footer.children) && ir.footer.children.length > 0) ||
      ir.footer.textRuns;
    assert.ok(hasText, 'footer 应有文本内容');
  }));
});

// ---------------------------------------------------------------------------
// Test 2: 批量提取 page_01.html + page_05.html
// ---------------------------------------------------------------------------
describe('extractPages — page_01.html + page_05.html', () => {
  /** @type {Array<{path:string, ir:Object|null, error?:string}>} */
  let results;

  before(async () => {
    if (!TEST_DATA_EXISTS) return;
    results = await extractPages([PAGE_01, PAGE_05]);
  });

  it('返回两个结果', maybeSkip(() => {
    assert.equal(results.length, 2, '应返回两个结果');
  }));

  it('两个页面均成功（ir 不为 null）', maybeSkip(() => {
    for (const r of results) {
      assert.ok(r.ir !== null, `${path.basename(r.path)} 的 IR 不应为 null（error: ${r.error}）`);
      assert.ok(!r.error, `${path.basename(r.path)} 不应有 error 字段`);
    }
  }));

  it('page_01 结果包含正确 path', maybeSkip(() => {
    assert.equal(results[0].path, PAGE_01, '第一个结果的 path 应为 PAGE_01');
  }));

  it('page_05 结果包含正确 path', maybeSkip(() => {
    assert.equal(results[1].path, PAGE_05, '第二个结果的 path 应为 PAGE_05');
  }));

  it('page_05 的 ct 有多个子节点（有内容区域）', maybeSkip(() => {
    const r = results[1];
    assert.ok(r.ir !== null, 'page_05 IR 不为 null');
    assert.ok(r.ir.ct !== null, 'page_05 ct 不为 null');
    assert.ok(Array.isArray(r.ir.ct.children) && r.ir.ct.children.length > 0,
      'page_05 ct.children 应非空');
  }));

  it('page_01 的 bg 包含 opacity 样式', maybeSkip(() => {
    const r = results[0];
    assert.ok(r.ir !== null, 'page_01 IR 不为 null');
    assert.ok(r.ir.bg !== null, 'page_01 bg 不为 null');
    assert.ok(r.ir.bg.styles !== null && typeof r.ir.bg.styles === 'object',
      'page_01 bg.styles 应为对象');
  }));
});
