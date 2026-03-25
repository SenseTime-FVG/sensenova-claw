/**
 * test_style_parser.mjs
 * CSS 样式解析工具函数的测试套件
 * 使用 node:test 和 node:assert/strict
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
  cssColorToHex,
  isTransparent,
  pxToInch,
  parseLinearGradient,
  parseBoxShadow,
  parseFontFamily,
  parseBorder,
} from '../lib/style_parser.mjs';

// ---------------------------------------------------------------------------
// cssColorToHex
// ---------------------------------------------------------------------------
describe('cssColorToHex', () => {
  it('converts rgb() to uppercase hex without #', () => {
    assert.equal(cssColorToHex('rgb(26, 35, 126)'), '1A237E');
  });

  it('converts rgba() ignoring alpha (non-transparent)', () => {
    assert.equal(cssColorToHex('rgba(212, 175, 55, 0.6)'), 'D4AF37');
  });

  it('converts named color white', () => {
    assert.equal(cssColorToHex('white'), 'FFFFFF');
  });

  it('converts named color black', () => {
    assert.equal(cssColorToHex('black'), '000000');
  });

  it('converts 6-digit hex (strips #, uppercases)', () => {
    assert.equal(cssColorToHex('#1A237E'), '1A237E');
  });

  it('converts 3-digit hex to 6-digit uppercase', () => {
    assert.equal(cssColorToHex('#fff'), 'FFFFFF');
  });

  it('returns null for transparent keyword', () => {
    assert.equal(cssColorToHex('transparent'), null);
  });

  it('returns null for rgba(0, 0, 0, 0)', () => {
    assert.equal(cssColorToHex('rgba(0, 0, 0, 0)'), null);
  });
});

// ---------------------------------------------------------------------------
// isTransparent
// ---------------------------------------------------------------------------
describe('isTransparent', () => {
  it('returns true for "transparent"', () => {
    assert.equal(isTransparent('transparent'), true);
  });

  it('returns true for rgba(0, 0, 0, 0)', () => {
    assert.equal(isTransparent('rgba(0, 0, 0, 0)'), true);
  });

  it('returns false for rgb(255, 0, 0)', () => {
    assert.equal(isTransparent('rgb(255, 0, 0)'), false);
  });

  it('returns false for #FF0000', () => {
    assert.equal(isTransparent('#FF0000'), false);
  });
});

// ---------------------------------------------------------------------------
// pxToInch
// ---------------------------------------------------------------------------
describe('pxToInch', () => {
  it('1280px equals 10 inches', () => {
    assert.equal(pxToInch(1280), 10);
  });

  it('720px equals 5.625 inches', () => {
    assert.equal(pxToInch(720), 5.625);
  });

  it('0px equals 0 inches', () => {
    assert.equal(pxToInch(0), 0);
  });
});

// ---------------------------------------------------------------------------
// parseLinearGradient
// ---------------------------------------------------------------------------
describe('parseLinearGradient', () => {
  it('parses hex color stops with degree angle', () => {
    const result = parseLinearGradient('linear-gradient(135deg, #1A237E 0%, #0D1240 100%)');
    assert.equal(result.type, 'linear');
    assert.equal(result.angle, 135);
    assert.equal(result.stops.length, 2);
    assert.equal(result.stops[0].position, 0);
    assert.equal(result.stops[0].color, '1A237E');
    assert.equal(result.stops[1].position, 100);
    assert.equal(result.stops[1].color, '0D1240');
  });

  it('parses rgb() color stops with 180deg', () => {
    const result = parseLinearGradient(
      'linear-gradient(180deg, rgb(255, 255, 255) 0%, rgb(0, 0, 0) 100%)'
    );
    assert.equal(result.angle, 180);
    assert.equal(result.stops[0].color, 'FFFFFF');
    assert.equal(result.stops[1].color, '000000');
  });

  it('returns null for radial-gradient', () => {
    assert.equal(parseLinearGradient('radial-gradient(circle, red, blue)'), null);
  });

  it('returns null for "none"', () => {
    assert.equal(parseLinearGradient('none'), null);
  });

  it('returns null for empty string', () => {
    assert.equal(parseLinearGradient(''), null);
  });
});

// ---------------------------------------------------------------------------
// parseBoxShadow
// ---------------------------------------------------------------------------
describe('parseBoxShadow', () => {
  it('parses outer box-shadow with rgba color', () => {
    const result = parseBoxShadow('0px 10px 30px rgba(0, 0, 0, 0.08)');
    assert.equal(result.type, 'outer');
    assert.equal(result.offsetX, 0);
    assert.equal(result.offsetY, 10);
    assert.equal(result.blur, 30);
    assert.equal(result.color, '000000');
    assert.equal(result.opacity, 0.08);
  });

  it('returns null for "none"', () => {
    assert.equal(parseBoxShadow('none'), null);
  });

  it('returns null for empty string', () => {
    assert.equal(parseBoxShadow(''), null);
  });
});

// ---------------------------------------------------------------------------
// parseFontFamily
// ---------------------------------------------------------------------------
describe('parseFontFamily', () => {
  it('extracts first non-generic font from list with single quotes', () => {
    assert.equal(
      parseFontFamily("'PingFang SC', 'Microsoft YaHei', sans-serif"),
      'PingFang SC'
    );
  });

  it('extracts first font from list with double quotes', () => {
    assert.equal(parseFontFamily('"Arial Black", Arial'), 'Arial Black');
  });

  it('maps generic sans-serif to Arial', () => {
    assert.equal(parseFontFamily('sans-serif'), 'Arial');
  });

  it('maps generic serif to Times New Roman', () => {
    assert.equal(parseFontFamily('serif'), 'Times New Roman');
  });

  it('maps generic monospace to Courier New', () => {
    assert.equal(parseFontFamily('monospace'), 'Courier New');
  });
});

// ---------------------------------------------------------------------------
// parseBorder
// ---------------------------------------------------------------------------
describe('parseBorder', () => {
  it('parses border with rgb() color', () => {
    const result = parseBorder('1px solid rgb(238, 238, 238)');
    assert.equal(result.width, 1);
    assert.equal(result.style, 'solid');
    assert.equal(result.color, 'EEEEEE');
  });

  it('parses border with hex color and larger width', () => {
    const result = parseBorder('8px solid #D4AF37');
    assert.equal(result.width, 8);
    assert.equal(result.style, 'solid');
    assert.equal(result.color, 'D4AF37');
  });

  it('returns null for "none"', () => {
    assert.equal(parseBorder('none'), null);
  });

  it('returns null for "0px none"', () => {
    assert.equal(parseBorder('0px none'), null);
  });
});
