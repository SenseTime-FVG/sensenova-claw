/**
 * test_integration.mjs
 * 集成测试：HTML → PPTX 转换（使用真实 Gold Investment deck）
 */

import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, unlinkSync, statSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const TEST_DECK = '/home/wangbo4/.agentos/workdir/default/Gold_Investment_20260318_223444';
const OUTPUT_FILE = resolve(TEST_DECK, 'test_output.pptx');
const SCRIPT = resolve(__dirname, '..', 'html_to_pptx.mjs');

describe('integration: HTML → PPTX', () => {
  before(() => {
    if (existsSync(OUTPUT_FILE)) {
      unlinkSync(OUTPUT_FILE);
    }
  });

  after(() => {
    if (existsSync(OUTPUT_FILE)) {
      unlinkSync(OUTPUT_FILE);
    }
  });

  it('converts Gold_Investment deck to PPTX', () => {
    if (!existsSync(TEST_DECK)) {
      console.log('SKIP: test deck not found at', TEST_DECK);
      return;
    }

    const result = execSync(
      `node ${SCRIPT} --deck-dir ${TEST_DECK} --output test_output.pptx`,
      { encoding: 'utf-8', timeout: 60000 }
    );

    const json = JSON.parse(result.trim());
    assert.equal(json.success, true, 'conversion should succeed');
    assert.equal(json.pages, 9, 'should have 9 pages');
    assert.ok(json.converted > 0, 'should have converted > 0 pages');
    assert.ok(existsSync(OUTPUT_FILE), 'output file should exist');
    assert.ok(statSync(OUTPUT_FILE).size > 0, 'output file should not be empty');
  });

  it('fails gracefully for missing deck_dir', () => {
    let error;
    try {
      execSync(`node ${SCRIPT} --deck-dir /nonexistent/path`, { encoding: 'utf-8' });
    } catch (err) {
      error = err;
    }
    assert.ok(error, 'should have thrown an error');
    assert.ok(error.status !== 0, 'exit code should be non-zero');
  });

  it('fails gracefully for missing --deck-dir argument', () => {
    let error;
    try {
      execSync(`node ${SCRIPT}`, { encoding: 'utf-8' });
    } catch (err) {
      error = err;
    }
    assert.ok(error, 'should have thrown an error');
    assert.ok(error.status !== 0, 'exit code should be non-zero');
  });
});
