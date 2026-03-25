import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function readJsonIfExists(filePath) {
  if (!existsSync(filePath)) {
    return null;
  }
  return JSON.parse(readFileSync(filePath, 'utf-8'));
}

function collectMotifMarkers(html) {
  const markers = {
    'bg-motif': new Set(),
    'fg-motif': new Set(),
  };
  const tags = html.match(/<[^>]+>/g) || [];
  for (const tag of tags) {
    const layerMatch = /data-layer\s*=\s*(?:"([^"]+)"|'([^']+)')/.exec(tag);
    const motifMatch = /data-motif-key\s*=\s*(?:"([^"]+)"|'([^']+)')/.exec(tag);
    const layer = layerMatch?.[1] || layerMatch?.[2];
    const motifKey = motifMatch?.[1] || motifMatch?.[2];
    if (!layer || !motifKey) {
      continue;
    }
    if (layer === 'bg-motif' || layer === 'fg-motif') {
      markers[layer].add(motifKey);
    }
  }
  return markers;
}

function ensureDecorativeMarkers(deckDir, htmlFiles) {
  const styleSpec = readJsonIfExists(resolve(deckDir, 'style-spec.json'));
  const storyboard = readJsonIfExists(resolve(deckDir, 'storyboard.json'));
  if (!styleSpec || !storyboard) {
    return;
  }

  const variants = new Map(
    (styleSpec.page_type_variants || []).map(variant => [variant.variant_key, variant]),
  );
  const pages = new Map(
    (storyboard.pages || []).map(page => [Number(page.page_number), page]),
  );
  const errors = [];

  for (const htmlFile of htmlFiles) {
    const fileName = htmlFile.split('/').pop() || '';
    const pageNumber = Number((/page_(\d+)\.html$/.exec(fileName) || [])[1]);
    const page = pages.get(pageNumber);
    if (!page) {
      continue;
    }
    const variant = variants.get(page.style_variant);
    if (!variant) {
      continue;
    }

    const html = readFileSync(htmlFile, 'utf-8');
    const markers = collectMotifMarkers(html);
    const checks = [
      ['bg-motif', variant.background_motif_recipe || []],
      ['fg-motif', variant.foreground_motif_recipe || []],
    ];

    for (const [layer, recipe] of checks) {
      if (!Array.isArray(recipe) || recipe.length === 0) {
        continue;
      }
      if (markers[layer].size === 0) {
        errors.push(
          `${fileName} 缺少 ${layer} 标记；请按 recipe 落地元素并写上 data-layer="${layer}" / data-motif-key`,
        );
        continue;
      }
      for (const item of recipe) {
        const motifKey = item?.motif_key;
        if (!motifKey) {
          continue;
        }
        if (!markers[layer].has(motifKey)) {
          errors.push(
            `${fileName} 缺少 data-layer="${layer}" data-motif-key="${motifKey}"，无法证明已按 recipe 落地`,
          );
        }
      }
    }
  }

  if (errors.length > 0) {
    throw new Error(`页面装饰层校验失败:\n- ${errors.join('\n- ')}`);
  }
}

export function ensureDeckPreconditions(deckDir) {
  if (!deckDir) {
    throw new Error('必须指定 --deck-dir 参数');
  }
  if (!existsSync(deckDir)) {
    throw new Error(`deck_dir 不存在: ${deckDir}`);
  }

  const pagesDir = resolve(deckDir, 'pages');
  if (!existsSync(pagesDir)) {
    throw new Error(`pages/ 目录不存在: ${pagesDir}`);
  }

  const htmlFiles = readdirSync(pagesDir)
    .filter(f => /^page_\d+\.html$/.test(f))
    .sort()
    .map(f => resolve(pagesDir, f));

  if (htmlFiles.length === 0) {
    throw new Error('pages/ 目录中没有 page_*.html 文件');
  }

  ensureDecorativeMarkers(deckDir, htmlFiles);

  return {
    pagesDir,
    htmlFiles,
  };
}
