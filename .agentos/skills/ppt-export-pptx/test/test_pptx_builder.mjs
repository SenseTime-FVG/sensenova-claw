import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { buildBackground, buildTextElement, buildSlideFromIR } from '../lib/pptx_builder.mjs';

describe('buildBackground', () => {
  it('returns solid fill for opaque backgroundColor', () => {
    const bgIR = {
      tag: 'div', id: 'bg',
      bounds: { x: 0, y: 0, w: 1280, h: 720 },
      styles: {
        backgroundColor: 'rgb(26, 35, 126)',
        backgroundImage: 'none',
      },
      children: [],
    };
    const result = buildBackground(bgIR);
    assert.deepEqual(result, { fill: '1A237E' });
  });

  it('returns gradient degraded to first stop color for linear-gradient backgroundImage', () => {
    const bgIR = {
      tag: 'div', id: 'bg',
      bounds: { x: 0, y: 0, w: 1280, h: 720 },
      styles: {
        backgroundColor: 'rgba(0, 0, 0, 0)',
        backgroundImage: 'linear-gradient(135deg, rgb(26, 35, 126) 0%, rgb(13, 18, 64) 100%)',
      },
      children: [],
    };
    const result = buildBackground(bgIR);
    assert.ok(result, 'should return non-null result');
    assert.ok(result.fill, 'should have fill property');
    // pptxgenjs slide.background 不支持渐变，降级为首个颜色停靠点（字符串）
    assert.equal(typeof result.fill, 'string', 'fill should be a hex color string');
    assert.equal(result.fill, '1A237E', 'should use first gradient stop color');
  });

  it('returns null for fully transparent background', () => {
    const bgIR = {
      tag: 'div', id: 'bg',
      bounds: { x: 0, y: 0, w: 1280, h: 720 },
      styles: {
        backgroundColor: 'rgba(0, 0, 0, 0)',
        backgroundImage: 'none',
      },
      children: [],
    };
    const result = buildBackground(bgIR);
    assert.equal(result, null);
  });
});

describe('buildTextElement', () => {
  it('builds text options from IR node with text', () => {
    const node = {
      tag: 'h1',
      bounds: { x: 100, y: 50, w: 400, h: 60 },
      text: '标题文字',
      styles: {
        color: 'rgb(26, 35, 126)',
        fontSize: '48px',
        fontWeight: '700',
        fontFamily: "'PingFang SC', 'Microsoft YaHei', sans-serif",
        fontStyle: 'normal',
        textAlign: 'left',
        lineHeight: 'normal',
        textDecoration: 'none',
        overflow: 'visible',
      },
      children: [],
    };
    const result = buildTextElement(node);
    assert.ok(result, 'should return text element');
    assert.equal(result.text, '标题文字');
    assert.ok(result.options.x !== undefined);
    assert.ok(result.options.y !== undefined);
    assert.ok(result.options.w !== undefined);
    assert.ok(result.options.h !== undefined);
    assert.equal(result.options.fontSize, 36); // 48px * 0.75 = 36pt
    assert.equal(result.options.bold, true);
    assert.equal(result.options.color, '1A237E');
  });

  it('returns null for node without text', () => {
    const node = {
      tag: 'div',
      bounds: { x: 0, y: 0, w: 100, h: 100 },
      styles: {},
      children: [],
    };
    const result = buildTextElement(node);
    assert.equal(result, null);
  });
});
