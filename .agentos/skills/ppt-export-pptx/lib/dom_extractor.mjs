/**
 * dom_extractor.mjs
 * 基于 Playwright 的 DOM 提取模块。
 * 将 HTML 幻灯片页面解析为中间表示（IR），供 PPTX builder 使用。
 */

import { chromium } from 'playwright';
import path from 'node:path';

// ---------------------------------------------------------------------------
// 浏览器端执行的 DOM 提取脚本
// 通过 page.evaluate() 注入到页面中运行
// ---------------------------------------------------------------------------

/**
 * 在浏览器中执行的提取函数（字符串形式注入）。
 * 不可引用外部模块或闭包变量。
 */
const BROWSER_EXTRACT_FN = () => {
  // CSS 属性列表（kebab-case），用于 getPropertyValue
  const CSS_PROPS = [
    'color', 'font-size', 'font-weight', 'font-family', 'font-style',
    'background-color', 'background-image',
    'border-radius', 'box-shadow',
    'border-top', 'border-right', 'border-bottom', 'border-left',
    'opacity', 'text-align', 'line-height', 'letter-spacing',
    'text-decoration', 'display', 'overflow',
    'object-fit', 'vertical-align',
    'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
  ];

  // kebab-case → camelCase 转换（用于返回对象的 key）
  function kebabToCamel(str) {
    return str.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
  }

  /**
   * 提取元素的计算样式，返回 camelCase key 的对象。
   * @param {Element} el
   * @returns {Object}
   */
  function extractStyles(el) {
    const cs = window.getComputedStyle(el);
    const styles = {};
    for (const prop of CSS_PROPS) {
      const val = cs.getPropertyValue(prop);
      if (val) {
        styles[kebabToCamel(prop)] = val;
      }
    }
    return styles;
  }

  /**
   * 提取元素的边界框（相对于 .wrapper 左上角）。
   * @param {Element} el
   * @param {DOMRect} wrapperRect
   * @returns {{x:number, y:number, w:number, h:number}}
   */
  function extractBounds(el, wrapperRect) {
    const r = el.getBoundingClientRect();
    return {
      x: r.left - wrapperRect.left,
      y: r.top - wrapperRect.top,
      w: r.width,
      h: r.height,
    };
  }

  /**
   * 提取表格数据。
   * @param {HTMLTableElement} table
   * @returns {Array<Array<{text:string, isHeader:boolean, colspan:number, rowspan:number, styles:Object}>>}
   */
  function extractTableData(table) {
    const rows = [];
    for (const tr of table.rows) {
      const cells = [];
      for (const cell of tr.cells) {
        cells.push({
          text: cell.innerText || '',
          isHeader: cell.tagName === 'TH',
          colspan: cell.colSpan || 1,
          rowspan: cell.rowSpan || 1,
          styles: extractStyles(cell),
        });
      }
      rows.push(cells);
    }
    return rows;
  }

  /**
   * 提取列表数据。
   * @param {HTMLUListElement|HTMLOListElement} listEl
   * @returns {Array<{text:string, styles:Object}>}
   */
  function extractListData(listEl) {
    const items = [];
    for (const li of listEl.querySelectorAll(':scope > li')) {
      items.push({
        text: li.innerText || '',
        styles: extractStyles(li),
      });
    }
    return items;
  }

  /**
   * 检测元素的子节点中是否存在混合内容（文本节点 + 元素节点）。
   * @param {Element} el
   * @returns {boolean}
   */
  function hasMixedContent(el) {
    let hasText = false;
    let hasElement = false;
    for (const child of el.childNodes) {
      if (child.nodeType === 3 && child.textContent.trim()) {
        hasText = true;
      } else if (child.nodeType === 1) {
        hasElement = true;
      }
    }
    return hasText && hasElement;
  }

  /**
   * 提取混合内容的 textRuns 数组。
   * @param {Element} el
   * @returns {Array<{text:string, bold:boolean, italic:boolean, fontSize:string, color:string, fontFamily:string, underline:boolean}>}
   */
  function extractTextRuns(el) {
    const runs = [];

    function walk(node) {
      if (node.nodeType === 3) {
        // 纯文本节点
        const text = node.textContent;
        if (text) {
          // 获取父元素的样式作为该文本节点的样式
          const parent = node.parentElement || el;
          const cs = window.getComputedStyle(parent);
          runs.push({
            text,
            bold: cs.getPropertyValue('font-weight') >= 600 || cs.getPropertyValue('font-weight') === 'bold',
            italic: cs.getPropertyValue('font-style') === 'italic',
            fontSize: cs.getPropertyValue('font-size'),
            color: cs.getPropertyValue('color'),
            fontFamily: cs.getPropertyValue('font-family'),
            underline: cs.getPropertyValue('text-decoration').includes('underline'),
          });
        }
      } else if (node.nodeType === 1) {
        const cs = window.getComputedStyle(node);
        // 跳过 display:none 的元素
        if (cs.getPropertyValue('display') === 'none') return;

        const text = node.innerText || '';
        if (!text) return;

        runs.push({
          text,
          bold: cs.getPropertyValue('font-weight') >= 600 || cs.getPropertyValue('font-weight') === 'bold',
          italic: cs.getPropertyValue('font-style') === 'italic',
          fontSize: cs.getPropertyValue('font-size'),
          color: cs.getPropertyValue('color'),
          fontFamily: cs.getPropertyValue('font-family'),
          underline: cs.getPropertyValue('text-decoration').includes('underline'),
        });
      }
    }

    for (const child of el.childNodes) {
      walk(child);
    }

    return runs;
  }

  /**
   * 判断节点是否应跳过。
   * @param {Element} el
   * @param {CSSStyleDeclaration} cs
   * @returns {boolean}
   */
  function shouldSkip(el, cs) {
    if (el.nodeType !== 1) return true;
    if (cs.getPropertyValue('display') === 'none') return true;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0 && el.children.length === 0) return true;
    return false;
  }

  /**
   * 递归提取单个 DOM 元素为 IR 节点。
   * @param {Element} el
   * @param {DOMRect} wrapperRect
   * @returns {Object|null}
   */
  function extractNode(el, wrapperRect) {
    if (el.nodeType !== 1) return null;

    const cs = window.getComputedStyle(el);
    if (shouldSkip(el, cs)) return null;

    const tag = el.tagName.toUpperCase();
    const node = {
      tag,
      id: el.id || undefined,
      className: el.className || undefined,
      bounds: extractBounds(el, wrapperRect),
      styles: extractStyles(el),
      children: [],
    };

    // --- 特殊元素处理 ---

    // IMG: 提取 src 和自然尺寸
    if (tag === 'IMG') {
      node.src = el.getAttribute('src') || undefined;
      node.naturalWidth = el.naturalWidth;
      node.naturalHeight = el.naturalHeight;
      return node;
    }

    // SVG: 提取 outerHTML，不递归子节点
    if (tag === 'SVG') {
      node.svgContent = el.outerHTML;
      return node;
    }

    // TABLE: 提取 tableData，不递归子节点
    if (tag === 'TABLE') {
      node.tableData = extractTableData(el);
      return node;
    }

    // UL/OL: 提取 listData，不递归子节点
    if (tag === 'UL' || tag === 'OL') {
      node.listData = extractListData(el);
      node.listType = tag === 'OL' ? 'ordered' : 'unordered';
      return node;
    }

    // 混合内容 → textRuns
    if (hasMixedContent(el)) {
      node.textRuns = extractTextRuns(el);
      return node;
    }

    // 叶子文本节点
    const childElements = Array.from(el.childNodes).filter(n => n.nodeType === 1);
    if (childElements.length === 0) {
      const text = el.innerText || el.textContent || '';
      if (text.trim()) {
        node.text = text;
      }
      return node;
    }

    // 递归子节点
    for (const child of el.children) {
      const childNode = extractNode(child, wrapperRect);
      if (childNode !== null) {
        node.children.push(childNode);
      }
    }

    return node;
  }

  // ---------------------------------------------------------------------------
  // 主提取逻辑
  // ---------------------------------------------------------------------------
  const wrapper = document.querySelector('.wrapper');
  if (!wrapper) {
    return { error: 'No .wrapper element found' };
  }

  const wrapperRect = wrapper.getBoundingClientRect();

  // 提取背景 (#bg)
  const bgEl = document.getElementById('bg');
  const bg = bgEl ? extractNode(bgEl, wrapperRect) : null;

  // 提取内容区 (#ct)
  const ctEl = document.getElementById('ct');
  const ct = ctEl ? extractNode(ctEl, wrapperRect) : null;

  // 提取页脚 (#footer)
  const footerEl = document.getElementById('footer');
  const footer = footerEl ? extractNode(footerEl, wrapperRect) : null;

  return { bg, ct, footer };
};

// ---------------------------------------------------------------------------
// extractPage — 从单个 HTML 文件提取 IR
// ---------------------------------------------------------------------------

/**
 * 使用已有的 Playwright page 对象提取单个 HTML 文件的 IR。
 * @param {import('playwright').Page} page - Playwright page 对象
 * @param {string} htmlPath - HTML 文件的绝对路径
 * @returns {Promise<{bg:Object|null, ct:Object|null, footer:Object|null}>}
 */
export async function extractPage(page, htmlPath) {
  // 转换为 file:// URL
  const fileUrl = htmlPath.startsWith('file://')
    ? htmlPath
    : `file://${path.resolve(htmlPath)}`;

  await page.goto(fileUrl, { waitUntil: 'load' });

  // 等待 300ms 让动态样式完全计算完成
  await page.waitForTimeout(300);

  // 在浏览器中执行提取脚本
  const ir = await page.evaluate(BROWSER_EXTRACT_FN);

  return ir;
}

// ---------------------------------------------------------------------------
// extractPages — 批量提取多个 HTML 文件
// ---------------------------------------------------------------------------

/**
 * 批量提取多个 HTML 文件的 IR。
 * 自动启动/关闭浏览器。
 * @param {string[]} htmlPaths - HTML 文件路径数组
 * @returns {Promise<Array<{path:string, ir:Object|null, error?:string}>>}
 */
export async function extractPages(htmlPaths) {
  const browser = await chromium.launch({ headless: true });
  const results = [];

  try {
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1280, height: 720 });

    for (const htmlPath of htmlPaths) {
      try {
        const ir = await extractPage(page, htmlPath);
        results.push({ path: htmlPath, ir });
      } catch (err) {
        process.stderr.write(`[dom_extractor] Failed to extract ${htmlPath}: ${err.message}\n`);
        results.push({ path: htmlPath, ir: null, error: err.message });
      }
    }
  } finally {
    await browser.close();
  }

  return results;
}
