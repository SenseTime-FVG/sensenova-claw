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

function ensureReviewArtifact(deckDir) {
  const reviewMd = resolve(deckDir, 'review.md');
  const reviewJson = resolve(deckDir, 'review.json');
  const hasReviewMd = existsSync(reviewMd);
  const hasReviewJson = existsSync(reviewJson);

  if (!hasReviewMd && !hasReviewJson) {
    throw new Error('缺少 review 工件：必须先生成 review.md 或 review.json，才能继续导出');
  }

  let isBlocked = false;

  if (hasReviewJson) {
    const review = readJsonIfExists(reviewJson);
    const markers = [
      review?.status,
      review?.result,
      review?.decision,
      review?.summary,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    if (/(block|blocked|fail|failed|reject|rejected|needs-fix|needs_fix)/.test(markers)) {
      isBlocked = true;
    }
  }

  if (hasReviewMd && !isBlocked) {
    const reviewText = readFileSync(reviewMd, 'utf-8');
    if (
      /status:\s*(block|blocked|fail|failed|reject|rejected)/i.test(reviewText) ||
      /阻塞|不可交付|不能直接交付/.test(reviewText)
    ) {
      isBlocked = true;
    }
  }

  if (isBlocked) {
    throw new Error('review 标记为阻塞，必须先修复 review 中的问题，不能继续导出');
  }
}

function parseTag(tag) {
  const closeMatch = /^<\s*\/\s*([a-zA-Z0-9:-]+)/.exec(tag);
  if (closeMatch) {
    return {
      type: 'close',
      name: closeMatch[1].toLowerCase(),
    };
  }

  const openMatch = /^<\s*([a-zA-Z0-9:-]+)/.exec(tag);
  if (!openMatch) {
    return null;
  }

  const idMatch = /\bid\s*=\s*(?:"([^"]+)"|'([^']+)')/.exec(tag);
  const classMatch = /\bclass\s*=\s*(?:"([^"]+)"|'([^']+)')/.exec(tag);
  return {
    type: 'open',
    name: openMatch[1].toLowerCase(),
    id: idMatch?.[1] || idMatch?.[2] || '',
    classList: (classMatch?.[1] || classMatch?.[2] || '')
      .split(/\s+/)
      .filter(Boolean),
    selfClosing: /\/\s*>$/.test(tag),
  };
}

function inspectTitlePlacement(html) {
  const tags = html.match(/<[^>]+>/g) || [];
  const stack = [];
  let titleInsideCt = false;
  let titleInsideHeader = false;
  let misplacedHeaderWithTitle = false;

  for (const tag of tags) {
    const parsed = parseTag(tag);
    if (!parsed) {
      continue;
    }

    if (parsed.type === 'close') {
      for (let i = stack.length - 1; i >= 0; i--) {
        const node = stack[i];
        stack.pop();
        if (node.name === parsed.name) {
          break;
        }
      }
      continue;
    }

    const insideCt = stack.some(node => node.id === 'ct');
    const insideHeader = stack.some(node => node.id === 'header');
    const insideLooseHeader = stack.some(
      node => node.id !== 'header' && node.classList.includes('header'),
    );
    const isHeading = /^h[1-6]$/.test(parsed.name);

    if (isHeading) {
      if (insideCt) {
        titleInsideCt = true;
      }
      if (insideHeader) {
        titleInsideHeader = true;
      }
      if (!insideCt && !insideHeader && insideLooseHeader) {
        misplacedHeaderWithTitle = true;
      }
    }

    if (!parsed.selfClosing) {
      stack.push(parsed);
    }
  }

  return {
    titleInsideCt,
    titleInsideHeader,
    misplacedHeaderWithTitle,
  };
}

function shouldRequireVisibleTitle(variant) {
  const strategy = String(variant?.header_strategy || '').toLowerCase();
  if (!strategy) {
    return false;
  }
  return !/(hidden|none|no-header|no_header|titleless)/.test(strategy);
}

function ensureVisibleTitles(deckDir, htmlFiles) {
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
    if (!shouldRequireVisibleTitle(variant)) {
      continue;
    }

    const html = readFileSync(htmlFile, 'utf-8');
    const titleCheck = inspectTitlePlacement(html);

    if (titleCheck.misplacedHeaderWithTitle) {
      errors.push(
        `${fileName} 的标题落在错误层级：不要把 .header 放在 #bg 和 #ct 之间；可见标题必须放在 #ct 内或单独的 #header 内`,
      );
      continue;
    }

    if (!titleCheck.titleInsideCt && !titleCheck.titleInsideHeader) {
      errors.push(
        `${fileName} 缺少可见标题：可见标题必须放在 #ct 内或单独的 #header 内，避免只在源码里存在却被内容层盖住`,
      );
    }
  }

  if (errors.length > 0) {
    throw new Error(`页面标题层级校验失败:\n- ${errors.join('\n- ')}`);
  }
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
  ensureVisibleTitles(deckDir, htmlFiles);

  return {
    pagesDir,
    htmlFiles,
  };
}
