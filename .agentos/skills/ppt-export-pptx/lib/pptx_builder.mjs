// PPTX 构建器：将 IR 映射为 pptxgenjs slide 对象
import PptxGenJS from 'pptxgenjs';
import {
  cssColorToHex, isTransparent, parseLinearGradient,
  parseBoxShadow, parseFontFamily, parseBorder, pxToInch,
  extractCssAlpha,
} from './style_parser.mjs';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

// 像素转磅：与坐标使用同一比例（1280px = 10"），px * (10/1280) * 72 = px * 0.5625
function pxToPt(px) {
  return pxToInch(parseFloat(px)) * 72;
}

/**
 * 解析 backgroundImage 中的多层背景，提取 url 和 gradient/color overlay。
 * CSS 多层背景格式：linear-gradient(...), url("...") 或 url("...") 单层。
 * @param {string} bgImage - CSS backgroundImage 计算值
 * @returns {{ imageUrl: string|null, overlayColor: string|null, overlayAlpha: number }}
 */
function parseMultiLayerBackground(bgImage) {
  let imageUrl = null;
  let overlayColor = null;
  let overlayAlpha = 1;

  if (!bgImage || bgImage === 'none') return { imageUrl, overlayColor, overlayAlpha };

  // 提取所有 url(...)
  const urlMatches = [...bgImage.matchAll(/url\(["']?([^"')]+)["']?\)/g)];
  if (urlMatches.length > 0) {
    let imgPath = urlMatches[0][1];
    if (imgPath.startsWith('file://')) imgPath = imgPath.slice(7);
    imageUrl = imgPath;
  }

  // 提取 gradient 层中的 rgba 颜色（用作 overlay）
  // 使用平衡括号提取 linear-gradient(...) 内容（处理嵌套的 rgba()）
  const gradIdx = bgImage.indexOf('linear-gradient(');
  let gradientInner = null;
  if (gradIdx !== -1) {
    const start = gradIdx + 'linear-gradient('.length;
    let depth = 1;
    let end = start;
    for (; end < bgImage.length && depth > 0; end++) {
      if (bgImage[end] === '(') depth++;
      else if (bgImage[end] === ')') depth--;
    }
    gradientInner = bgImage.slice(start, end - 1);
  }
  if (gradientInner) {
    const inner = gradientInner;
    // 提取第一个 rgba() 颜色
    const rgbaMatch = inner.match(/rgba\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)/);
    if (rgbaMatch) {
      const r = Math.round(parseFloat(rgbaMatch[1]));
      const g = Math.round(parseFloat(rgbaMatch[2]));
      const b = Math.round(parseFloat(rgbaMatch[3]));
      overlayAlpha = parseFloat(rgbaMatch[4]);
      overlayColor = [r, g, b].map(n => n.toString(16).padStart(2, '0')).join('').toUpperCase();
    } else {
      // 非 rgba gradient，降级取首个颜色
      const gradient = parseLinearGradient(bgImage);
      if (gradient && gradient.stops.length > 0) {
        overlayColor = gradient.stops[0].color;
        overlayAlpha = 1;
      }
    }
  }

  return { imageUrl, overlayColor, overlayAlpha };
}

/**
 * 从 #bg IR 构建 slide background 配置。
 * 返回 { slideBackground, bgElements[] }：
 * - slideBackground: pptxgenjs slide.background 对象（图片或纯色）
 * - bgElements: 额外的背景层元素（overlay shapes、透明图片等）
 * @param {Object} bgIR - #bg 的 IR 节点
 * @param {string} [bodyBgColor] - body 的背景色（用于 opacity < 1 时的底色）
 * @param {string} [deckDir] - deck 目录路径（用于解析相对图片路径）
 */
export function buildBackground(bgIR, bodyBgColor, deckDir) {
  const result = { slideBackground: null, bgElements: [] };

  // 默认使用 body 背景色（作为 slide 底色）
  const bodyHex = cssColorToHex(bodyBgColor);
  if (bodyHex) {
    result.slideBackground = { fill: bodyHex };
  }

  if (!bgIR || !bgIR.styles) return result.slideBackground ? result : null;

  const { backgroundColor, backgroundImage, opacity } = bgIR.styles;
  const bgOpacity = opacity !== undefined ? parseFloat(opacity) : 1;

  let { imageUrl, overlayColor, overlayAlpha } = parseMultiLayerBackground(backgroundImage);

  // 如果 CSS backgroundImage 没有 url，检查 #bg 的 <img> 子元素
  if (!imageUrl && bgIR.children) {
    const imgChild = bgIR.children.find(c => (c.tag || '').toUpperCase() === 'IMG' && c.src);
    if (imgChild) {
      let imgPath = imgChild.src;
      if (imgPath.startsWith('file://')) imgPath = imgPath.slice(7);
      // 相对路径解析为绝对路径
      if (!imgPath.startsWith('/') && deckDir) {
        imgPath = resolve(deckDir, 'pages', imgPath);
      }
      if (existsSync(imgPath)) {
        imageUrl = imgPath;
      }
    }
  }

  // --- 情况 1：多层背景（图片 + gradient overlay，如 page_01）---
  // 这种情况下 opacity 作用于整个 #bg 元素（通常为 1）
  if (imageUrl && overlayColor) {
    result.slideBackground = { path: imageUrl };
    const transparency = Math.round((1 - overlayAlpha) * 100);
    result.bgElements.push({
      type: 'shape',
      data: {
        x: 0, y: 0, w: 10, h: 5.625,
        fill: { color: overlayColor, transparency },
      }
    });
    return result;
  }

  // --- 情况 2：单图背景 ---
  if (imageUrl) {
    // 远程 URL（http/https）跳过，pptxgenjs 可能无法加载
    const isRemoteUrl = /^https?:\/\//.test(imageUrl);
    if (bgOpacity >= 1) {
      // 完全不透明：直接设为 slide 背景图
      if (!isRemoteUrl) result.slideBackground = { path: imageUrl };
    } else if (!isRemoteUrl) {
      // opacity < 1：图片作为 slide 背景，叠加 body 底色的半透明遮罩
      // transparency = bgOpacity * 100 → 遮罩 (1-bgOpacity) 不透明，透过 bgOpacity 的图片
      result.slideBackground = { path: imageUrl };
      const baseHex = bodyHex || 'FFFFFF';
      const transparency = Math.round(bgOpacity * 100);
      result.bgElements.push({
        type: 'shape',
        data: {
          x: 0, y: 0, w: 10, h: 5.625,
          fill: { color: baseHex, transparency },
        }
      });
    }
    // 远程 URL + opacity < 1：保留 bodyBgColor
    return result;
  }

  // --- 情况 3：仅 gradient（无图片 url）---
  if (backgroundImage && backgroundImage !== 'none') {
    const gradient = parseLinearGradient(backgroundImage);
    if (gradient) {
      result.slideBackground = { fill: gradient.stops[0].color };
      return result;
    }
    // radial/conic gradient 降级
    const colorMatch = backgroundImage.match(/(?:rgb|rgba)\s*\([^)]*\)|#[0-9a-fA-F]{3,8}/);
    if (colorMatch) {
      const hex = cssColorToHex(colorMatch[0]);
      if (hex) {
        result.slideBackground = { fill: hex };
        return result;
      }
    }
  }

  // --- 情况 4：纯色背景 ---
  if (backgroundColor && !isTransparent(backgroundColor)) {
    const hex = cssColorToHex(backgroundColor);
    if (hex) {
      if (bgOpacity < 1 && bgOpacity > 0) {
        // opacity < 1：body 底色 + 半透明 shape
        const baseHex = bodyHex || 'FFFFFF';
        result.slideBackground = { fill: baseHex };
        const transparency = Math.round((1 - bgOpacity) * 100);
        result.bgElements.push({
          type: 'shape',
          data: {
            x: 0, y: 0, w: 10, h: 5.625,
            fill: { color: hex, transparency },
          }
        });
      } else {
        result.slideBackground = { fill: hex };
      }
      return result;
    }
  }

  return result.slideBackground ? result : null;
}

/**
 * 从 IR 文本节点构建 pptxgenjs addText 参数
 */
export function buildTextElement(node) {
  if (!node) return null;

  const text = node.text;
  const textRuns = node.textRuns;

  if (!text && (!textRuns || textRuns.length === 0)) return null;

  const s = node.styles || {};
  const b = node.bounds;

  const options = {
    x: pxToInch(b.x),
    y: pxToInch(b.y),
    w: pxToInch(b.w),
    h: pxToInch(b.h),
    fontSize: pxToPt(parseFloat(s.fontSize) || 16),
    fontFace: parseFontFamily(s.fontFamily),
    color: cssColorToHex(s.color) || '000000',
    bold: parseInt(s.fontWeight) >= 700,
    italic: s.fontStyle === 'italic',
    underline: s.textDecoration?.includes('underline') ? { style: 'sng' } : undefined,
    align: mapTextAlign(s.textAlign),
    valign: mapVerticalAlign(s.verticalAlign),
    autoFit: true,
  };

  // 单行文本检测：如果高度 < 字号 × 2，说明浏览器中只有一行，
  // 设置 wrap: false 避免因字体渲染差异在 PPTX 中意外换行
  const fsPx = parseFloat(s.fontSize) || 16;
  const isSingleLine = !textRuns && b.h < fsPx * 2;
  options.wrap = !isSingleLine;

  // 行高：CSS computed lineHeight 返回 px 值，需要除以 fontSize 得到倍数
  if (s.lineHeight && s.lineHeight !== 'normal') {
    const lhPx = parseFloat(s.lineHeight);
    const fsPx = parseFloat(s.fontSize) || 16;
    if (!isNaN(lhPx) && lhPx > 0 && fsPx > 0) {
      options.lineSpacingMultiple = lhPx / fsPx;
    }
  }

  // 文本 runs（混合格式）
  if (textRuns && textRuns.length > 0) {
    const runs = textRuns.map(run => ({
      text: run.text,
      options: {
        fontSize: pxToPt(run.fontSize || 16),
        fontFace: parseFontFamily(run.fontFamily),
        color: cssColorToHex(run.color) || '000000',
        bold: run.bold,
        italic: run.italic,
        underline: run.underline ? { style: 'sng' } : undefined,
        breakLine: run.isBlock ? true : undefined,
      }
    }));
    return { text: runs, options };
  }

  return { text, options };
}

function mapTextAlign(cssAlign) {
  const map = { left: 'left', center: 'center', right: 'right', justify: 'justify' };
  return map[cssAlign] || 'left';
}

function mapVerticalAlign(cssValign) {
  if (!cssValign) return undefined;
  const map = { top: 'top', middle: 'middle', bottom: 'bottom' };
  return map[cssValign] || undefined;
}

/**
 * 检查节点是否有视觉装饰（背景色、边框、阴影、圆角）
 */
function hasVisualDecoration(node) {
  const s = node.styles || {};
  if (s.backgroundColor && !isTransparent(s.backgroundColor)) return true;
  if (parseBorder(s.borderTop) || parseBorder(s.borderRight) ||
      parseBorder(s.borderBottom) || parseBorder(s.borderLeft)) return true;
  if (parseBoxShadow(s.boxShadow)) return true;
  if (s.borderRadius && parseFloat(s.borderRadius) > 0) return true;
  return false;
}

/**
 * 从 IR 节点构建形状（有装饰的容器）
 */
export function buildShapeElement(node) {
  const s = node.styles || {};
  const b = node.bounds;
  if (!hasVisualDecoration(node)) return null;

  const shape = {
    x: pxToInch(b.x),
    y: pxToInch(b.y),
    w: pxToInch(b.w),
    h: pxToInch(b.h),
  };

  // 背景填充（支持 rgba 透明度 + 元素 opacity）
  const bgColor = cssColorToHex(s.backgroundColor);
  if (bgColor) {
    const bgAlpha = extractCssAlpha(s.backgroundColor);
    const elOpacity = s.opacity !== undefined ? parseFloat(s.opacity) : 1;
    const combinedAlpha = bgAlpha * (isNaN(elOpacity) ? 1 : elOpacity);
    const transparency = Math.round((1 - combinedAlpha) * 100);
    shape.fill = { color: bgColor, transparency: transparency > 0 ? transparency : 0 };
  }

  // 圆角
  const radius = parseFloat(s.borderRadius);
  if (radius > 0) {
    shape.rectRadius = pxToInch(radius);
  }

  // 边框
  const parsedBorders = [
    parseBorder(s.borderTop),
    parseBorder(s.borderRight),
    parseBorder(s.borderBottom),
    parseBorder(s.borderLeft),
  ];
  const visibleBorders = parsedBorders.filter(Boolean);
  if (visibleBorders.length === 4) {
    // 四边都有边框：使用 shape.line（应用到所有边）
    const thickest = visibleBorders.reduce((a, c) => a.width >= c.width ? a : c);
    shape.line = { color: thickest.color, width: pxToPt(thickest.width) };
  }
  // 非对称边框在 flattenIRToElements 中通过 buildBorderLines 处理

  // 阴影
  const shadow = parseBoxShadow(s.boxShadow);
  if (shadow) {
    shape.shadow = {
      type: 'outer',
      blur: shadow.blur * 0.75,
      offset: Math.max(Math.abs(shadow.offsetX), Math.abs(shadow.offsetY)) * 0.75,
      color: shadow.color,
      opacity: shadow.opacity,
    };
  }

  return shape;
}

/**
 * 从 IR 节点构建图片元素
 */
export function buildImageElement(node, deckDir) {
  if (!node.src) return null;
  const b = node.bounds;

  // 解析图片路径
  let imgPath = node.src;
  // 浏览器可能把相对路径解析为 file:// URL，需要还原为文件系统路径
  if (imgPath.startsWith('file://')) {
    imgPath = imgPath.slice(7);
  }
  if (!imgPath.startsWith('/')) {
    imgPath = resolve(deckDir, 'pages', imgPath);
  }

  // 检查文件是否存在
  if (!existsSync(imgPath)) {
    // 尝试从 deck_dir 相对路径解析
    const altPath = resolve(deckDir, imgPath.replace(/^\.\.\//, ''));
    if (existsSync(altPath)) {
      imgPath = altPath;
    } else {
      console.error(`[WARN] 图片不存在: ${node.src}`);
      return null;
    }
  }

  const element = {
    path: imgPath,
    x: pxToInch(b.x),
    y: pxToInch(b.y),
    w: pxToInch(b.w),
    h: pxToInch(b.h),
  };

  // object-fit 处理
  const objectFit = node.styles?.objectFit;
  if (objectFit === 'contain') {
    element.sizing = { type: 'contain', w: pxToInch(b.w), h: pxToInch(b.h) };
  } else if (objectFit === 'cover') {
    element.sizing = { type: 'cover', w: pxToInch(b.w), h: pxToInch(b.h) };
  }

  return element;
}

/**
 * 从 IR 节点构建表格元素
 */
export function buildTableElement(node) {
  if (!node.tableData || node.tableData.length === 0) return null;

  const b = node.bounds;
  const rows = node.tableData.map(row =>
    row.map(cell => ({
      text: cell.text,
      options: {
        fontSize: pxToPt(parseFloat(cell.styles?.fontSize) || 14),
        color: cssColorToHex(cell.styles?.color) || '000000',
        bold: cell.isHeader || parseInt(cell.styles?.fontWeight) >= 700,
        fill: cssColorToHex(cell.styles?.backgroundColor) ? { color: cssColorToHex(cell.styles.backgroundColor) } : undefined,
        align: cell.styles?.textAlign || 'left',
        colspan: cell.colspan > 1 ? cell.colspan : undefined,
        rowspan: cell.rowspan > 1 ? cell.rowspan : undefined,
      }
    }))
  );

  return {
    rows,
    options: {
      x: pxToInch(b.x),
      y: pxToInch(b.y),
      w: pxToInch(b.w),
      colW: pxToInch(b.w) / (rows[0]?.length || 1),
    }
  };
}

/**
 * 从列表节点构建带 bullet 的文本元素
 */
export function buildListElement(node) {
  if (!node.listData || node.listData.length === 0) return null;

  const b = node.bounds;
  const isOrdered = node.listType === 'ordered';

  const runs = node.listData.map((item, idx) => ({
    text: item.text,
    options: {
      fontSize: pxToPt(parseFloat(item.styles?.fontSize) || 16),
      fontFace: parseFontFamily(item.styles?.fontFamily),
      color: cssColorToHex(item.styles?.color) || '000000',
      bold: parseInt(item.styles?.fontWeight) >= 700,
      bullet: isOrdered ? { type: 'number', startAt: idx + 1 } : { code: '2022' }, // • bullet
      breakLine: true,
    }
  }));

  return {
    text: runs,
    options: {
      x: pxToInch(b.x),
      y: pxToInch(b.y),
      w: pxToInch(b.w),
      h: pxToInch(b.h),
      valign: 'top',
    }
  };
}

/**
 * 从 SVG 节点构建图片元素（base64 嵌入）
 */
export function buildSvgElement(node) {
  if (!node.svgContent) return null;
  const b = node.bounds;

  try {
    const svgBase64 = Buffer.from(node.svgContent).toString('base64');
    return {
      data: `data:image/svg+xml;base64,${svgBase64}`,
      x: pxToInch(b.x),
      y: pxToInch(b.y),
      w: pxToInch(b.w),
      h: pxToInch(b.h),
    };
  } catch (err) {
    console.error(`[WARN] SVG 转换失败: ${err.message}`);
    return null;
  }
}

/**
 * 为非对称边框生成独立的线条元素。
 * 仅当 1-3 条边有边框时使用（4 条边由 shape.line 处理）。
 */
function buildBorderLines(node) {
  const s = node.styles || {};
  const b = node.bounds;
  const parsed = [
    parseBorder(s.borderTop),
    parseBorder(s.borderRight),
    parseBorder(s.borderBottom),
    parseBorder(s.borderLeft),
  ];
  const visibleCount = parsed.filter(Boolean).length;
  if (visibleCount === 0 || visibleCount === 4) return [];

  const x = pxToInch(b.x);
  const y = pxToInch(b.y);
  const w = pxToInch(b.w);
  const h = pxToInch(b.h);
  const lines = [];

  // top
  if (parsed[0]) {
    lines.push({ type: 'line', data: {
      x, y, w, h: 0,
      line: { color: parsed[0].color, width: pxToPt(parsed[0].width) },
    }});
  }
  // right
  if (parsed[1]) {
    lines.push({ type: 'line', data: {
      x: x + w, y, w: 0, h,
      line: { color: parsed[1].color, width: pxToPt(parsed[1].width) },
    }});
  }
  // bottom
  if (parsed[2]) {
    lines.push({ type: 'line', data: {
      x, y: y + h, w, h: 0,
      line: { color: parsed[2].color, width: pxToPt(parsed[2].width) },
    }});
  }
  // left
  if (parsed[3]) {
    lines.push({ type: 'line', data: {
      x, y, w: 0, h,
      line: { color: parsed[3].color, width: pxToPt(parsed[3].width) },
    }});
  }

  return lines;
}

/**
 * 递归扁平化 IR 节点，生成 slide 元素列表
 */
export function flattenIRToElements(node, deckDir) {
  const elements = [];
  if (!node) return elements;

  const tag = (node.tag || '').toUpperCase();

  // 容器装饰 → 形状（IMG 不需要容器形状）
  if (hasVisualDecoration(node) && tag !== 'IMG') {
    const shape = buildShapeElement(node);
    if (shape) elements.push({ type: 'shape', data: shape });
    // 非对称边框 → 独立线条
    const borderLines = buildBorderLines(node);
    elements.push(...borderLines);
  }

  // 文本
  if (node.text || (node.textRuns && node.textRuns.length > 0)) {
    const textEl = buildTextElement(node);
    if (textEl) elements.push({ type: 'text', data: textEl });
  }

  // 图片
  if (tag === 'IMG') {
    const imgEl = buildImageElement(node, deckDir);
    if (imgEl) elements.push({ type: 'image', data: imgEl });
  }

  // SVG
  if (tag === 'SVG') {
    const svgEl = buildSvgElement(node);
    if (svgEl) elements.push({ type: 'svg', data: svgEl });
  }

  // 表格
  if (tag === 'TABLE') {
    const tableEl = buildTableElement(node);
    if (tableEl) elements.push({ type: 'table', data: tableEl });
  }

  // 列表
  if (tag === 'UL' || tag === 'OL') {
    const listEl = buildListElement(node);
    if (listEl) elements.push({ type: 'list', data: listEl });
  }

  // 递归子元素
  if (node.children) {
    for (const child of node.children) {
      elements.push(...flattenIRToElements(child, deckDir));
    }
  }

  return elements;
}

/**
 * 从 IR 构建单个 slide
 */
export function buildSlideFromIR(pptx, ir, deckDir) {
  const slide = pptx.addSlide();

  // 1. 背景（支持多层：slideBackground + bgElements overlay）
  if (ir.bg) {
    const bgResult = buildBackground(ir.bg, ir.bodyBgColor, deckDir);
    if (bgResult) {
      if (bgResult.slideBackground) slide.background = bgResult.slideBackground;
      // 添加背景层元素（overlay shapes 等）
      for (const el of bgResult.bgElements) {
        if (el.type === 'shape') {
          slide.addShape(pptx.ShapeType.rect, el.data);
        } else if (el.type === 'image') {
          slide.addImage(el.data);
        }
      }
    }
  } else if (ir.bodyBgColor) {
    // 无 #bg 时，使用 bodyBgColor 作为幻灯片底色
    const bodyHex = cssColorToHex(ir.bodyBgColor);
    if (bodyHex) {
      slide.background = { fill: bodyHex };
    }
  }

  // 2. 页头（#header，通常包含页面标题）
  if (ir.header) {
    const headerElements = flattenIRToElements(ir.header, deckDir);
    for (const el of headerElements) {
      switch (el.type) {
        case 'text':
          slide.addText(el.data.text, el.data.options);
          break;
        case 'shape': {
          const shapeType = el.data.rectRadius ? pptx.ShapeType.roundRect : pptx.ShapeType.rect;
          slide.addShape(shapeType, el.data);
          break;
        }
        case 'line':
          slide.addShape(pptx.ShapeType.line, el.data);
          break;
        case 'image':
          slide.addImage(el.data);
          break;
      }
    }
  }

  // 3. 内容区
  if (ir.ct) {
    const elements = flattenIRToElements(ir.ct, deckDir);
    for (const el of elements) {
      switch (el.type) {
        case 'text':
          slide.addText(el.data.text, el.data.options);
          break;
        case 'image':
          slide.addImage(el.data);
          break;
        case 'shape': {
          const shapeType = el.data.rectRadius ? pptx.ShapeType.roundRect : pptx.ShapeType.rect;
          slide.addShape(shapeType, el.data);
          break;
        }
        case 'line':
          slide.addShape(pptx.ShapeType.line, el.data);
          break;
        case 'svg':
          slide.addImage(el.data);
          break;
        case 'table':
          slide.addTable(el.data.rows, el.data.options);
          break;
        case 'list':
          slide.addText(el.data.text, el.data.options);
          break;
      }
    }
  }

  // 4. 页脚
  if (ir.footer) {
    const footerText = buildTextElement(ir.footer);
    if (footerText) {
      slide.addText(footerText.text, footerText.options);
    }
  }

  return slide;
}

/**
 * 构建完整 PPTX
 * @param {Array<{path: string, ir: object}>} pages - 页面 IR 数组
 * @param {string} deckDir - deck 目录路径
 * @param {string} outputPath - PPTX 输出路径
 */
export async function buildPptx(pages, deckDir, outputPath) {
  const pptx = new PptxGenJS();

  // 设置 16:9 画布（10" × 5.625"）
  pptx.defineLayout({ name: 'HTML_SLIDE', width: 10, height: 5.625 });
  pptx.layout = 'HTML_SLIDE';

  // 尝试读取 storyboard.json 获取标题
  const storyboardPath = resolve(deckDir, 'storyboard.json');
  if (existsSync(storyboardPath)) {
    try {
      const storyboard = JSON.parse(readFileSync(storyboardPath, 'utf-8'));
      if (storyboard.ppt_title) pptx.title = storyboard.ppt_title;
    } catch { /* 非必需 */ }
  }

  // 尝试读取 style-spec.json 获取默认字体
  let defaultFont = null;
  const styleSpecPath = resolve(deckDir, 'style-spec.json');
  if (existsSync(styleSpecPath)) {
    try {
      const styleSpec = JSON.parse(readFileSync(styleSpecPath, 'utf-8'));
      if (styleSpec.typography?.font_family) {
        defaultFont = parseFontFamily(styleSpec.typography.font_family);
      }
    } catch { /* 非必需 */ }
  }

  let successCount = 0;
  let failCount = 0;

  for (const page of pages) {
    if (page.ir) {
      try {
        buildSlideFromIR(pptx, page.ir, deckDir);
        successCount++;
      } catch (err) {
        console.error(`[WARN] 构建 slide 失败: ${page.path} - ${err.message}`);
        // 生成空白 slide 保持页码连续
        pptx.addSlide();
        failCount++;
      }
    } else {
      // IR 为空，生成空白 slide
      pptx.addSlide();
      failCount++;
    }
  }

  await pptx.writeFile({ fileName: outputPath });

  return { successCount, failCount, totalPages: pages.length };
}
