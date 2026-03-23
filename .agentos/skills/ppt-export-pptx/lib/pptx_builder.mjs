// PPTX 构建器：将 IR 映射为 pptxgenjs slide 对象
import PptxGenJS from 'pptxgenjs';
import {
  cssColorToHex, isTransparent, parseLinearGradient,
  parseBoxShadow, parseFontFamily, parseBorder, pxToInch,
} from './style_parser.mjs';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

// 像素转磅（CSS px = 0.75pt）
function pxToPt(px) {
  return parseFloat(px) * 0.75;
}

/**
 * 从 #bg IR 构建 slide background 配置
 */
export function buildBackground(bgIR) {
  if (!bgIR || !bgIR.styles) return null;

  const { backgroundColor, backgroundImage } = bgIR.styles;

  // 优先渐变
  if (backgroundImage && backgroundImage !== 'none') {
    const gradient = parseLinearGradient(backgroundImage);
    if (gradient) {
      // pptxgenjs slide.background 不支持渐变，降级为首个颜色停靠点
      return { fill: gradient.stops[0].color };
    }
    // radial/conic gradient 降级：尝试提取颜色
    const colorMatch = backgroundImage.match(/(?:rgb|rgba|#)\([^)]*\)|#[0-9a-fA-F]{3,8}/);
    if (colorMatch) {
      const hex = cssColorToHex(colorMatch[0]);
      if (hex) return { fill: hex };
    }
    // 背景图片 url(...)
    const urlMatch = backgroundImage.match(/url\(["']?([^"')]+)["']?\)/);
    if (urlMatch) {
      return { path: urlMatch[1] };
    }
  }

  // 纯色背景
  if (backgroundColor && !isTransparent(backgroundColor)) {
    const hex = cssColorToHex(backgroundColor);
    if (hex) return { fill: hex };
  }

  return null;
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
    autoFit: s.overflow === 'hidden' ? false : true,
    wrap: true,
  };

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

  // 背景填充
  const bgColor = cssColorToHex(s.backgroundColor);
  if (bgColor) shape.fill = { color: bgColor };

  // 圆角
  const radius = parseFloat(s.borderRadius);
  if (radius > 0) {
    shape.rectRadius = pxToInch(radius);
  }

  // 边框（取最粗的边）
  const borders = [s.borderTop, s.borderRight, s.borderBottom, s.borderLeft]
    .map(parseBorder)
    .filter(Boolean);
  if (borders.length > 0) {
    const thickest = borders.reduce((a, c) => a.width >= c.width ? a : c);
    shape.line = { color: thickest.color, width: thickest.width * 0.75 }; // px to pt
  }

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
 * 递归扁平化 IR 节点，生成 slide 元素列表
 */
export function flattenIRToElements(node, deckDir) {
  const elements = [];
  if (!node) return elements;

  // 容器装饰 → 形状
  if (hasVisualDecoration(node) && node.tag !== 'img') {
    const shape = buildShapeElement(node);
    if (shape) elements.push({ type: 'shape', data: shape });
  }

  // 文本
  if (node.text || (node.textRuns && node.textRuns.length > 0)) {
    const textEl = buildTextElement(node);
    if (textEl) elements.push({ type: 'text', data: textEl });
  }

  // 图片
  if (node.tag === 'img') {
    const imgEl = buildImageElement(node, deckDir);
    if (imgEl) elements.push({ type: 'image', data: imgEl });
  }

  // SVG
  if (node.tag === 'svg') {
    const svgEl = buildSvgElement(node);
    if (svgEl) elements.push({ type: 'svg', data: svgEl });
  }

  // 表格
  if (node.tag === 'table') {
    const tableEl = buildTableElement(node);
    if (tableEl) elements.push({ type: 'table', data: tableEl });
  }

  // 列表
  if (node.tag === 'ul' || node.tag === 'ol') {
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

  // 1. 背景
  if (ir.bg) {
    const bg = buildBackground(ir.bg);
    if (bg) slide.background = bg;
  }

  // 2. 内容区
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

  // 3. 页脚
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
