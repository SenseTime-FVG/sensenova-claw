// PPTX 构建器：将 IR 映射为 pptxgenjs slide 对象
import PptxGenJS from 'pptxgenjs';
import {
  cssColorToHex, isTransparent, parseLinearGradient, parseRadialGradient,
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
 * 从 CSS filter 中提取 brightness 值。
 * @param {string} filterStr - 如 "brightness(0.4) saturate(1.2)"
 * @returns {number|null} - brightness 值（0-1），未找到返回 null
 */
function parseBrightness(filterStr) {
  if (!filterStr) return null;
  const m = filterStr.match(/brightness\(\s*([\d.]+)\s*\)/);
  if (m) return parseFloat(m[1]);
  return null;
}

/**
 * 从 CSS text-shadow 中提取阴影参数。
 * @param {string} textShadow - 如 "3px 3px 5px rgba(0,0,0,0.5)"
 * @returns {Object|null}
 */
function parseTextShadow(textShadow) {
  if (!textShadow || textShadow === 'none') return null;
  // 格式: offsetX offsetY blur? color
  // 先提取颜色
  const rgbaMatch = textShadow.match(/rgba?\s*\([^)]*\)/i);
  const colorStr = rgbaMatch ? rgbaMatch[0] : null;
  const rest = (colorStr ? textShadow.replace(colorStr, '') : textShadow).trim();
  const nums = rest.match(/-?[\d.]+/g);
  if (!nums || nums.length < 2) return null;

  const offsetX = parseFloat(nums[0]);
  const offsetY = parseFloat(nums[1]);
  const blur = nums.length >= 3 ? parseFloat(nums[2]) : 0;
  const color = colorStr ? cssColorToHex(colorStr) : '000000';
  const opacity = colorStr ? extractCssAlpha(colorStr) : 1;

  return {
    type: 'outer',
    blur: pxToPt(blur),
    offset: pxToPt(Math.max(Math.abs(offsetX), Math.abs(offsetY))),
    angle: Math.round(Math.atan2(offsetY, offsetX) * 180 / Math.PI + 90) % 360,
    color: color || '000000',
    opacity,
  };
}

/**
 * 从 CSS transform 中提取旋转角度（deg）。
 * 支持 rotate(Xdeg) 和 matrix() 形式。
 * @param {string} transformStr - 如 "rotate(-2deg)" 或 "matrix(...)"
 * @returns {number|null} - 旋转角度（度），未找到返回 null
 */
function parseRotation(transformStr) {
  if (!transformStr || transformStr === 'none') return null;
  // rotate(Xdeg)
  const rotateMatch = transformStr.match(/rotate\(\s*(-?[\d.]+)deg\s*\)/);
  if (rotateMatch) return parseFloat(rotateMatch[1]);
  // matrix(a,b,c,d,tx,ty) → angle = atan2(b, a)
  const matrixMatch = transformStr.match(/matrix\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)/);
  if (matrixMatch) {
    const a = parseFloat(matrixMatch[1]);
    const b = parseFloat(matrixMatch[2]);
    const angle = Math.round(Math.atan2(b, a) * 180 / Math.PI);
    if (angle !== 0) return angle;
  }
  return null;
}

/**
 * 将 CSS border-style 映射为 pptxgenjs dashType。
 * @param {string} style - solid/dashed/dotted/double 等
 * @returns {string} pptxgenjs dashType
 */
function mapBorderDashType(style) {
  const map = {
    solid: 'solid',
    dashed: 'dash',
    dotted: 'dot',
    double: 'solid', // pptxgenjs 不支持 double，退化为 solid
  };
  return map[style] || 'solid';
}

/**
 * 归一化渐变 stops：确保每个 stop 都有 position（0-100），pptxgenjs 要求。
 */
function normalizeGradientStops(stops) {
  return stops.map((s, i) => ({
    color: s.color,
    position: s.position !== undefined ? s.position : Math.round(i * 100 / Math.max(stops.length - 1, 1)),
  }));
}

/**
 * 解析 mask-image gradient，保留透明色 stop（与 parseLinearGradient 不同，不跳过 alpha=0）。
 * @param {string} cssValue - 如 "linear-gradient(to left, rgb(0,0,0) 70%, rgba(0,0,0,0))"
 * @returns {{direction: string|null, stops: Array<{position?:number, rawColor:string}>}|null}
 */
function parseMaskGradient(cssValue) {
  if (!cssValue) return null;
  const trimmed = cssValue.trim();
  if (!/^linear-gradient\s*\(/i.test(trimmed)) return null;
  const inner = trimmed.replace(/^linear-gradient\s*\(\s*/i, '').replace(/\s*\)$/, '');
  let safeInner = inner.replace(/rgba?\s*\([^)]*\)/gi, m => m.replace(/,/g, '§'));
  const parts = safeInner.split(',').map(p => p.replace(/§/g, ',').trim());
  if (parts.length < 2) return null;

  let direction = null;
  let stopParts = parts;
  const firstPart = parts[0].trim();
  if (/^to\s+/i.test(firstPart)) {
    direction = firstPart.toLowerCase();
    stopParts = parts.slice(1);
  } else if (/^-?[\d.]+deg$/i.test(firstPart)) {
    direction = firstPart;
    stopParts = parts.slice(1);
  }

  const stops = [];
  for (const part of stopParts) {
    const p = part.trim();
    if (!p) continue;
    const posMatch = p.match(/^(.*?)\s+([\d.]+)%\s*$/);
    if (posMatch) {
      stops.push({ position: parseFloat(posMatch[2]), rawColor: posMatch[1].trim() });
    } else {
      stops.push({ rawColor: p });
    }
  }
  if (stops.length === 0) return null;
  // 自动补位：如果没有 position，均匀分配
  for (let i = 0; i < stops.length; i++) {
    if (stops[i].position === undefined) {
      stops[i].position = Math.round(i * 100 / Math.max(stops.length - 1, 1));
    }
  }
  return { direction, stops };
}

/**
 * CSS 渐变方向 → SVG linearGradient x1/y1/x2/y2 映射。
 * @param {string} direction - 如 "to left", "to right", "135deg"
 * @returns {{ x1: string, y1: string, x2: string, y2: string }}
 */
function gradientDirectionToSvg(direction) {
  const dirMap = {
    'to right':  { x1: '0%', y1: '0%', x2: '100%', y2: '0%' },
    'to left':   { x1: '100%', y1: '0%', x2: '0%', y2: '0%' },
    'to bottom': { x1: '0%', y1: '0%', x2: '0%', y2: '100%' },
    'to top':    { x1: '0%', y1: '100%', x2: '0%', y2: '0%' },
    'to bottom right': { x1: '0%', y1: '0%', x2: '100%', y2: '100%' },
    'to top left':     { x1: '100%', y1: '100%', x2: '0%', y2: '0%' },
  };
  if (dirMap[direction]) return dirMap[direction];
  // 角度 → 近似方向
  const deg = parseFloat(direction);
  if (!isNaN(deg)) {
    const rad = (deg - 90) * Math.PI / 180; // CSS 角度：0deg = to top
    return {
      x1: `${Math.round(50 - Math.cos(rad) * 50)}%`,
      y1: `${Math.round(50 + Math.sin(rad) * 50)}%`,
      x2: `${Math.round(50 + Math.cos(rad) * 50)}%`,
      y2: `${Math.round(50 - Math.sin(rad) * 50)}%`,
    };
  }
  return dirMap['to right']; // 默认
}

/**
 * 为带有 mask-image 的图片生成模拟 mask 的 SVG overlay。
 * mask-image 中 alpha=1 的区域是可见的，alpha=0 是透明的。
 * 我们用背景色填充 alpha=0 的区域来模拟遮罩效果。
 * @param {Object} maskGrad - parseLinearGradient 解析的结果
 * @param {string} bgColor - 背景色 hex（如 'F1F8E9'）
 * @param {number} w - 宽度（像素）
 * @param {number} h - 高度（像素）
 * @returns {string} SVG data URI
 */
function buildMaskOverlaySvg(maskGrad, bgColor, w, h) {
  const dir = gradientDirectionToSvg(maskGrad.direction || 'to right');
  // mask gradient 中 alpha=0 表示「隐藏」→ overlay 需要不透明
  // mask gradient 中 alpha=1 表示「可见」→ overlay 需要透明
  // 所以 overlay stop opacity = 1 - mask_alpha
  const stops = maskGrad.stops.map(s => {
    // 解析 mask stop 的 alpha（mask stop 颜色通常是 rgba(0,0,0, alpha)）
    const alphaMatch = s.rawColor && s.rawColor.match(/rgba\([^)]*,\s*([\d.]+)\s*\)/);
    const maskAlpha = alphaMatch ? parseFloat(alphaMatch[1]) : 1;
    const overlayOpacity = (1 - maskAlpha).toFixed(2);
    const pos = s.position !== undefined ? s.position : '';
    return `<stop offset="${pos}%" stop-color="#${bgColor}" stop-opacity="${overlayOpacity}"/>`;
  }).join('\n      ');

  return `data:image/svg+xml;base64,${Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <defs>
      <linearGradient id="mask" x1="${dir.x1}" y1="${dir.y1}" x2="${dir.x2}" y2="${dir.y2}">
      ${stops}
      </linearGradient>
    </defs>
    <rect width="${w}" height="${h}" fill="url(#mask)"/>
  </svg>`).toString('base64')}`;
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
  let bgOpacity = opacity !== undefined ? parseFloat(opacity) : 1;

  let { imageUrl, overlayColor, overlayAlpha } = parseMultiLayerBackground(backgroundImage);
  let imageFromCss = !!imageUrl; // 标记图片来源：CSS backgroundImage 还是 <img> 子元素

  // 如果 CSS backgroundImage 没有 url，检查 #bg 的 <img> 子元素
  // 仅当图片覆盖 ≥ 90% 的幻灯片面积时，才提升为 slide background
  let imgChildFilter = null;
  if (!imageUrl && bgIR.children) {
    const imgChild = bgIR.children.find(c => {
      if ((c.tag || '').toUpperCase() !== 'IMG' || !c.src) return false;
      // 检查图片是否覆盖整个幻灯片
      const b = c.bounds;
      if (!b) return false;
      const slideCoverage = (b.w * b.h) / (1280 * 720);
      return slideCoverage >= 0.9;
    });
    if (imgChild) {
      let imgPath = imgChild.src;
      if (imgPath.startsWith('file://')) imgPath = imgPath.slice(7);
      // 相对路径解析为绝对路径
      if (!imgPath.startsWith('/') && deckDir) {
        imgPath = resolve(deckDir, 'pages', imgPath);
      }
      if (existsSync(imgPath)) {
        imageUrl = imgPath;
        // 保存 img 子元素的 filter 和 opacity 属性
        imgChildFilter = imgChild.styles?.filter || null;
        // img 子元素的 opacity（如 opacity: 0.5 暗化效果）
        const imgOpacity = imgChild.styles?.opacity !== undefined
          ? parseFloat(imgChild.styles.opacity) : 1;
        if (imgOpacity < 1 && bgOpacity >= 1) {
          // 将 img 的 opacity 合并到 #bg 的 opacity 处理中
          bgOpacity = imgOpacity;
        }
      }
    }
  }

  // --- 情况 1：多层背景（图片 + gradient overlay，如 page_01）---
  // 仅当图片和 gradient 都来自同一个 CSS background 属性时才叠加 overlay
  // 如果图片来自 <img> 子元素，CSS gradient 是 #bg 的独立背景，不作为 overlay
  if (imageUrl && overlayColor && imageFromCss) {
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
      if (!isRemoteUrl) {
        result.slideBackground = { path: imageUrl };
        // filter: brightness() → 黑色半透明遮罩模拟暗化效果
        const brightness = parseBrightness(imgChildFilter || bgIR.styles?.filter);
        if (brightness !== null && brightness < 1) {
          const overlayOpacity = Math.round((1 - brightness) * 100);
          result.bgElements.push({
            type: 'shape',
            data: {
              x: 0, y: 0, w: 10, h: 5.625,
              fill: { color: '000000', transparency: 100 - overlayOpacity },
            }
          });
        }
      }
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
  // 注意：pptxgenjs v3.x 的 ShapeFillProps 不支持 gradient fill，
  // 只能降级为纯色。取第一个 stop 颜色作为最佳近似。
  if (backgroundImage && backgroundImage !== 'none') {
    const linearGrad = parseLinearGradient(backgroundImage);
    if (linearGrad && linearGrad.stops.length > 0) {
      result.slideBackground = { fill: linearGrad.stops[0].color };
      return result;
    }
    const radialGrad = parseRadialGradient(backgroundImage);
    if (radialGrad && radialGrad.stops.length > 0) {
      result.slideBackground = { fill: radialGrad.stops[0].color };
      return result;
    }
    // 其他 gradient 类型降级：取第一个颜色
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
 * 获取文本颜色。处理渐变文字效果（-webkit-background-clip: text）：
 * 当 text-fill-color 为 transparent 时，从 backgroundImage gradient 提取首个颜色。
 */
function getTextColor(s) {
  // 检测渐变文字：-webkit-text-fill-color: transparent + backgroundImage gradient
  const fillColor = s.WebkitTextFillColor || s.webkitTextFillColor || '';
  if (fillColor === 'transparent' || fillColor === 'rgba(0, 0, 0, 0)') {
    if (s.backgroundImage && s.backgroundImage.includes('gradient')) {
      const grad = parseLinearGradient(s.backgroundImage) || parseRadialGradient(s.backgroundImage);
      if (grad && grad.stops.length > 0) {
        return grad.stops[0].color;
      }
    }
  }
  return cssColorToHex(s.color) || '000000';
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
    color: getTextColor(s),
    bold: parseInt(s.fontWeight) >= 700,
    italic: s.fontStyle === 'italic',
    underline: s.textDecoration?.includes('underline') ? { style: 'sng' } : undefined,
    align: mapTextAlign(s.textAlign),
    valign: mapVerticalAlign(s.verticalAlign),
    autoFit: true,
  };

  // transform: rotate() → pptxgenjs rotate
  const textRotation = parseRotation(s.transform);
  if (textRotation !== null) {
    options.rotate = textRotation;
  }

  // letter-spacing → charSpacing（单位：磅 pt）
  if (s.letterSpacing && s.letterSpacing !== 'normal' && s.letterSpacing !== '0px') {
    const lsPx = parseFloat(s.letterSpacing);
    if (!isNaN(lsPx) && lsPx !== 0) {
      options.charSpacing = pxToPt(lsPx);
    }
  }

  // 单行文本检测：如果高度 < 字号 × 2，说明浏览器中只有一行，
  // 设置 wrap: false 避免因字体渲染差异在 PPTX 中意外换行
  const fsPx = parseFloat(s.fontSize) || 16;
  const isSingleLine = !textRuns && b.h < fsPx * 2;
  options.wrap = !isSingleLine;

  // padding → pptxgenjs margin（文本框内边距）
  // 仅当节点自身有 text 或 textRuns 时设置（叶子文本节点的 padding 决定文本位置）
  const padTop = parseFloat(s.paddingTop) || 0;
  const padRight = parseFloat(s.paddingRight) || 0;
  const padBottom = parseFloat(s.paddingBottom) || 0;
  const padLeft = parseFloat(s.paddingLeft) || 0;
  if (padTop > 0 || padRight > 0 || padBottom > 0 || padLeft > 0) {
    options.margin = [
      pxToPt(padTop), pxToPt(padRight), pxToPt(padBottom), pxToPt(padLeft),
    ];
  }

  // text-shadow → pptxgenjs shadow
  if (s.textShadow) {
    const shadow = parseTextShadow(s.textShadow);
    if (shadow) options.shadow = shadow;
  }

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
/**
 * 检测元素是否使用了 -webkit-background-clip: text（渐变文字效果）
 */
function isGradientText(node) {
  const s = node.styles || {};
  const clip = s.WebkitBackgroundClip || s.backgroundClip || '';
  return clip === 'text';
}

function hasVisualDecoration(node) {
  const s = node.styles || {};
  // 渐变文字的 backgroundImage 不作为容器装饰
  if (isGradientText(node)) return false;
  if (s.backgroundColor && !isTransparent(s.backgroundColor)) return true;
  // backgroundImage gradient（如 overlay div 用 linear-gradient 作背景）
  if (s.backgroundImage && s.backgroundImage !== 'none' &&
      (s.backgroundImage.includes('gradient') || s.backgroundImage.includes('url('))) return true;
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
  } else if (s.backgroundImage && s.backgroundImage !== 'none' && s.backgroundImage.includes('gradient')) {
    // backgroundImage 渐变降级：解析 gradient 取最不透明的颜色
    const grad = parseLinearGradient(s.backgroundImage) || parseRadialGradient(s.backgroundImage);
    if (grad && grad.stops.length > 0) {
      shape.fill = { color: grad.stops[0].color };
    }
    // 尝试从所有 rgba() 中找最不透明的颜色（跳过 transparent/alpha=0）
    const allRgba = [...s.backgroundImage.matchAll(/rgba\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)/g)];
    let bestMatch = null;
    let bestAlpha = 0;
    for (const m of allRgba) {
      const a = parseFloat(m[4]);
      if (a > bestAlpha) {
        bestAlpha = a;
        bestMatch = m;
      }
    }
    if (bestMatch && bestAlpha > 0) {
      const r = Math.round(parseFloat(bestMatch[1]));
      const g = Math.round(parseFloat(bestMatch[2]));
      const b2 = Math.round(parseFloat(bestMatch[3]));
      const hex = [r, g, b2].map(n => n.toString(16).padStart(2, '0')).join('').toUpperCase();
      const transparency = Math.round((1 - bestAlpha) * 100);
      shape.fill = { color: hex, transparency };
    } else if (!shape.fill) {
      // 纯 rgb gradient（无 rgba）：取第一个非透明 stop
      const rgbMatch = s.backgroundImage.match(/rgb\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)/);
      if (rgbMatch) {
        const r = Math.round(parseFloat(rgbMatch[1]));
        const g = Math.round(parseFloat(rgbMatch[2]));
        const b2 = Math.round(parseFloat(rgbMatch[3]));
        shape.fill = { color: [r, g, b2].map(n => n.toString(16).padStart(2, '0')).join('').toUpperCase() };
      }
    }
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
    shape.line = buildLineOptions(thickest, s);
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

  // transform: rotate()
  const shapeRotation = parseRotation(s.transform);
  if (shapeRotation !== null) {
    shape.rotate = shapeRotation;
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

  const displayW = pxToInch(b.w);
  const displayH = pxToInch(b.h);

  const element = {
    path: imgPath,
    x: pxToInch(b.x),
    y: pxToInch(b.y),
    w: displayW,
    h: displayH,
  };

  // object-fit: cover/contain 修正：
  // pptxgenjs 的 sizing bug：它用 element.w/h（显示尺寸）而非图片原始尺寸来算裁剪
  // 解法：把原始尺寸传给 w/h，把显示尺寸传给 sizing.w/h
  // sizing 计算后会将 w/h 覆盖回显示尺寸
  const objectFit = node.styles?.objectFit;
  const natW = node.naturalWidth;
  const natH = node.naturalHeight;
  if (natW && natH && natW > 0 && natH > 0) {
    if (objectFit === 'cover') {
      element.w = natW / 96; // 原始尺寸（单位不影响，只用于比例计算）
      element.h = natH / 96;
      element.sizing = { type: 'cover', w: displayW, h: displayH };
    } else if (objectFit === 'contain') {
      element.w = natW / 96;
      element.h = natH / 96;
      element.sizing = { type: 'contain', w: displayW, h: displayH };
    }
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
    row.map(cell => {
      const cellOpts = {
        fontSize: pxToPt(parseFloat(cell.styles?.fontSize) || 14),
        color: cssColorToHex(cell.styles?.color) || '000000',
        bold: cell.isHeader || parseInt(cell.styles?.fontWeight) >= 700,
        align: cell.styles?.textAlign || 'center',
        colspan: cell.colspan > 1 ? cell.colspan : undefined,
        rowspan: cell.rowspan > 1 ? cell.rowspan : undefined,
        valign: 'middle',
      };
      // 单元格背景色（含 rgba 透明度）
      const bgHex = cssColorToHex(cell.styles?.backgroundColor);
      if (bgHex && !isTransparent(cell.styles?.backgroundColor)) {
        const alpha = extractCssAlpha(cell.styles.backgroundColor);
        cellOpts.fill = { color: bgHex, transparency: alpha < 1 ? Math.round((1 - alpha) * 100) : 0 };
      }
      // 单元格边框
      const border = parseBorder(cell.styles?.borderBottom);
      if (border) {
        cellOpts.border = { type: mapBorderDashType(border.style), color: border.color, pt: pxToPt(border.width) };
      }
      return { text: cell.text, options: cellOpts };
    })
  );

  // 计算行高：使用第一个单元格的 padding 估算
  const firstCell = node.tableData[0]?.[0];
  const cellPadding = firstCell?.styles?.padding ? parseFloat(firstCell.styles.padding) : 15;
  const rowH = pxToInch(cellPadding * 2 + (parseFloat(firstCell?.styles?.fontSize) || 14) * 1.4);

  return {
    rows,
    options: {
      x: pxToInch(b.x),
      y: pxToInch(b.y),
      w: pxToInch(b.w),
      colW: pxToInch(b.w) / (rows[0]?.length || 1),
      rowH,
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

  const runs = node.listData.map((item, idx) => {
    // 确定 bullet 样式：优先使用 CSS ::before 伪元素中的自定义字符（如 ✓）
    let bullet;
    if (isOrdered) {
      bullet = { type: 'number', startAt: idx + 1 };
    } else if (item.bulletChar) {
      // 自定义 bullet 字符：用 Unicode code point
      bullet = { code: item.bulletChar.codePointAt(0).toString(16).toUpperCase() };
    } else {
      bullet = { code: '2022' }; // 默认 • bullet
    }

    return {
      text: item.text,
      options: {
        fontSize: pxToPt(parseFloat(item.styles?.fontSize) || 16),
        fontFace: parseFontFamily(item.styles?.fontFamily),
        color: cssColorToHex(item.styles?.color) || '000000',
        bold: parseInt(item.styles?.fontWeight) >= 700,
        bullet,
        breakLine: true,
      }
    };
  });

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
 * 从 parseBorder 结果构建 pptxgenjs line 选项，含 dashType 和透明度。
 * @param {Object} border - parseBorder 返回的 {width, style, color}
 * @param {Object} styles - 节点原始 styles（用于提取边框原始 rgba alpha）
 */
function buildLineOptions(border, styles) {
  const line = {
    color: border.color,
    width: pxToPt(border.width),
    dashType: mapBorderDashType(border.style),
  };
  // 边框颜色含透明度时（如 rgba(255,255,255,0.1)），提取 alpha 设为 transparency
  // parseBorder 从 borderTop/Right/Bottom/Left computed value 中提取颜色
  // 但 computed value 的颜色部分可能是 rgba(...)，alpha 需要从原始值提取
  // 这里简化：如果 border.color 对应的原始 rgba alpha < 1，设置透明度
  if (styles) {
    for (const key of ['borderTop', 'borderRight', 'borderBottom', 'borderLeft']) {
      if (!styles[key]) continue;
      const rgbaMatch = styles[key].match(/rgba\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*,\s*([\d.]+)\s*\)/);
      if (rgbaMatch) {
        const alpha = parseFloat(rgbaMatch[1]);
        if (alpha < 1) {
          line.transparency = Math.round((1 - alpha) * 100);
          break;
        }
      }
    }
  }
  return line;
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

  if (parsed[0]) lines.push({ type: 'line', data: { x, y, w, h: 0, line: buildLineOptions(parsed[0], s) }});
  if (parsed[1]) lines.push({ type: 'line', data: { x: x + w, y, w: 0, h, line: buildLineOptions(parsed[1], s) }});
  if (parsed[2]) lines.push({ type: 'line', data: { x, y: y + h, w, h: 0, line: buildLineOptions(parsed[2], s) }});
  if (parsed[3]) lines.push({ type: 'line', data: { x, y, w: 0, h, line: buildLineOptions(parsed[3], s) }});

  return lines;
}

/**
 * 递归扁平化 IR 节点，生成 slide 元素列表
 */
export function flattenIRToElements(node, deckDir, parentBorderRadius = 0, parentBgColor = null) {
  const elements = [];
  if (!node) return elements;

  const tag = (node.tag || '').toUpperCase();
  const s = node.styles || {};

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
    if (imgEl) {
      // 父容器有 overflow:hidden + borderRadius → 图片圆角（使用 patched pptxgenjs 的 roundRect）
      if (parentBorderRadius > 0) {
        imgEl._prstGeom = 'roundRect';
        // roundRect 的 adj 值：corner radius / min(w,h) * 50000（OOXML 单位）
        const minDim = Math.min(imgEl.sizing?.w || imgEl.w, imgEl.sizing?.h || imgEl.h);
        const adj = Math.min(Math.round(pxToInch(parentBorderRadius) / minDim * 50000), 16667);
        imgEl._avLst = `<a:gd name="adj" fmla="val ${adj}"/>`;
      }
      elements.push({ type: 'image', data: imgEl });
      // 显示尺寸（object-fit workaround 会改 imgEl.w/h 为原始尺寸）
      const displayW = imgEl.sizing ? imgEl.sizing.w : imgEl.w;
      const displayH = imgEl.sizing ? imgEl.sizing.h : imgEl.h;
      // 图片 opacity < 1 → 叠加黑色半透明遮罩模拟暗化
      const imgOpacity = s.opacity !== undefined ? parseFloat(s.opacity) : 1;
      if (imgOpacity < 1 && imgOpacity > 0) {
        elements.push({
          type: 'shape',
          data: {
            x: imgEl.x, y: imgEl.y, w: displayW, h: displayH,
            fill: { color: '000000', transparency: Math.round(imgOpacity * 100) },
            ...(parentBorderRadius > 0 ? { rectRadius: pxToInch(parentBorderRadius) } : {}),
          }
        });
      }
      // mask-image: linear-gradient(...) → SVG 渐变蒙版模拟
      const maskImage = s.WebkitMaskImage || s.webkitMaskImage || s.maskImage;
      if (maskImage && maskImage !== 'none' && maskImage.includes('linear-gradient')) {
        const maskGrad = parseMaskGradient(maskImage);
        if (maskGrad && maskGrad.stops.length >= 2) {
          const bgColor = parentBgColor || 'FFFFFF';
          const pxW = Math.round(displayW / 10 * 1280);
          const pxH = Math.round(displayH / 10 * 1280);
          const svgDataUri = buildMaskOverlaySvg(maskGrad, bgColor, pxW, pxH);
          elements.push({
            type: 'image',
            data: {
              data: svgDataUri,
              x: imgEl.x, y: imgEl.y, w: displayW, h: displayH,
            }
          });
        }
      }
    }
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

  // 递归子元素（传递当前节点的 borderRadius 和背景色给子元素）
  const currentRadius = (s.overflow === 'hidden' && parseFloat(s.borderRadius) > 0) ? parseFloat(s.borderRadius) : 0;
  // 传递背景色给子元素（用于 mask-image 模拟蒙版的底色）
  const currentBgHex = (s.backgroundColor && !isTransparent(s.backgroundColor))
    ? cssColorToHex(s.backgroundColor) : null;
  const effectiveBgColor = currentBgHex || parentBgColor;
  if (node.children) {
    for (const child of node.children) {
      elements.push(...flattenIRToElements(child, deckDir, currentRadius || parentBorderRadius, effectiveBgColor));
    }
  }

  return elements;
}

/**
 * 从 IR 构建单个 slide
 */
export function buildSlideFromIR(pptx, ir, deckDir) {
  const slide = pptx.addSlide();
  // 预先计算 body 背景色 hex，用于 mask-image 蒙版模拟
  const bodyBgHex = cssColorToHex(ir.bodyBgColor) || 'FFFFFF';

  // 1. 背景（支持多层：slideBackground + bgElements overlay + #bg 子元素）
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
    // 渲染 #bg 的子元素（装饰层：mesh-gradient、grid-overlay、SVG motif 等）
    if (ir.bg.children && ir.bg.children.length > 0) {
      for (const child of ir.bg.children) {
        const bgChildElements = flattenIRToElements(child, deckDir, 0, bodyBgHex);
        for (const el of bgChildElements) {
          switch (el.type) {
            case 'shape': {
              const shapeType = el.data.rectRadius ? pptx.ShapeType.roundRect : pptx.ShapeType.rect;
              slide.addShape(shapeType, el.data);
              break;
            }
            case 'text':
              slide.addText(el.data.text, el.data.options);
              break;
            case 'image':
              slide.addImage(el.data);
              break;
            case 'svg':
              slide.addImage(el.data);
              break;
          }
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

  // 2. 遮罩层（.wrapper 中的 overlay 元素，如半透明渐变遮罩）
  if (ir.overlays && ir.overlays.length > 0) {
    for (const overlay of ir.overlays) {
      const overlayElements = flattenIRToElements(overlay, deckDir, 0, bodyBgHex);
      for (const el of overlayElements) {
        switch (el.type) {
          case 'shape': {
            const shapeType = el.data.rectRadius ? pptx.ShapeType.roundRect : pptx.ShapeType.rect;
            slide.addShape(shapeType, el.data);
            break;
          }
          case 'text':
            slide.addText(el.data.text, el.data.options);
            break;
          case 'image':
            slide.addImage(el.data);
            break;
        }
      }
    }
  }

  // 2.5. rest 层（.wrapper 中非已知 ID 的非绝对定位子元素，如 .header class）
  if (ir.rest && ir.rest.length > 0) {
    for (const restNode of ir.rest) {
      const restElements = flattenIRToElements(restNode, deckDir, 0, bodyBgHex);
      for (const el of restElements) {
        switch (el.type) {
          case 'shape': {
            const shapeType = el.data.rectRadius ? pptx.ShapeType.roundRect : pptx.ShapeType.rect;
            slide.addShape(shapeType, el.data);
            break;
          }
          case 'text':
            slide.addText(el.data.text, el.data.options);
            break;
          case 'image':
            slide.addImage(el.data);
            break;
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
  }

  // 3. 页头（#header，通常包含页面标题）
  if (ir.header) {
    const headerElements = flattenIRToElements(ir.header, deckDir, 0, bodyBgHex);
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

  // 4. 内容区
  if (ir.ct) {
    const elements = flattenIRToElements(ir.ct, deckDir, 0, bodyBgHex);
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

  // 5. 页脚（与页头/内容区一样完整处理子元素）
  if (ir.footer) {
    const footerElements = flattenIRToElements(ir.footer, deckDir, 0, bodyBgHex);
    if (footerElements.length > 0) {
      for (const el of footerElements) {
        switch (el.type) {
          case 'text':
            slide.addText(el.data.text, el.data.options);
            break;
          case 'shape': {
            const shapeType = el.data.rectRadius ? pptx.ShapeType.roundRect : pptx.ShapeType.rect;
            slide.addShape(shapeType, el.data);
            break;
          }
          case 'image':
            slide.addImage(el.data);
            break;
          case 'line':
            slide.addShape(pptx.ShapeType.line, el.data);
            break;
          case 'svg':
            slide.addImage(el.data);
            break;
        }
      }
    } else {
      // 回退：如果 flattenIRToElements 为空（纯文本 footer），直接构建文本
      const footerText = buildTextElement(ir.footer);
      if (footerText) {
        slide.addText(footerText.text, footerText.options);
      }
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
