#!/usr/bin/env node
// HTML → PPTX 转换器 CLI
// 用法: node html_to_pptx.mjs --deck-dir <path> [--output <filename>]

import { existsSync, readdirSync, statSync } from 'node:fs';
import { resolve, basename } from 'node:path';
import { extractPages } from './lib/dom_extractor.mjs';
import { buildPptx } from './lib/pptx_builder.mjs';

function parseArgs(args) {
  const result = { deckDir: null, output: null };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--deck-dir' && args[i + 1]) {
      result.deckDir = resolve(args[i + 1]);
      i++;
    } else if (args[i] === '--output' && args[i + 1]) {
      result.output = args[i + 1];
      i++;
    }
  }
  return result;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));

  // 前置检查 1: deck_dir 必须存在
  if (!args.deckDir) {
    console.error('错误: 必须指定 --deck-dir 参数');
    process.exit(1);
  }
  if (!existsSync(args.deckDir)) {
    console.error(`错误: deck_dir 不存在: ${args.deckDir}`);
    process.exit(1);
  }

  // 前置检查 2: pages/ 目录必须存在且有 HTML 文件
  const pagesDir = resolve(args.deckDir, 'pages');
  if (!existsSync(pagesDir)) {
    console.error(`错误: pages/ 目录不存在: ${pagesDir}`);
    process.exit(1);
  }

  const htmlFiles = readdirSync(pagesDir)
    .filter(f => /^page_\d+\.html$/.test(f))
    .sort()
    .map(f => resolve(pagesDir, f));

  if (htmlFiles.length === 0) {
    console.error(`错误: pages/ 目录中没有 page_*.html 文件`);
    process.exit(1);
  }

  console.error(`正在处理 ${htmlFiles.length} 个 HTML 页面...`);

  // DOM 提取
  console.error('步骤 1/2: 提取 DOM...');
  const pages = await extractPages(htmlFiles);

  // PPTX 构建：默认文件名与 deck_dir 目录名一致
  const outputFilename = args.output || (basename(args.deckDir) + '.pptx');
  const outputPath = resolve(args.deckDir, outputFilename);
  console.error('步骤 2/2: 生成 PPTX...');
  const result = await buildPptx(pages, args.deckDir, outputPath);

  // 输出验证
  if (!existsSync(outputPath)) {
    console.error('错误: PPTX 文件未生成');
    process.exit(1);
  }

  const fileSize = statSync(outputPath).size;
  if (fileSize === 0) {
    console.error('错误: PPTX 文件大小为 0');
    process.exit(1);
  }

  // 成功输出（stdout）
  const sizeKB = (fileSize / 1024).toFixed(1);
  console.log(JSON.stringify({
    success: true,
    output: outputPath,
    pages: result.totalPages,
    converted: result.successCount,
    failed: result.failCount,
    fileSize: `${sizeKB} KB`,
  }));

  if (result.failCount > 0) {
    console.error(`警告: ${result.failCount} 个页面转换失败`);
  }

  process.exit(0);
}

main().catch(err => {
  console.error(`致命错误: ${err.message}`);
  process.exit(1);
});
