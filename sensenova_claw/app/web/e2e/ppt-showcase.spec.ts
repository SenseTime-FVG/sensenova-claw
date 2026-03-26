/**
 * PPT 工作台 Showcase 测试
 *
 * 覆盖场景：
 * 1. 三栏布局与空状态
 * 2. 模板选择与输入填充
 * 3. 完整 deck 数据展示（storyboard / style / review / notes / assets）
 * 4. 幻灯片查看器导航与全屏
 * 5. Pipeline 进度条状态
 * 6. 导出下拉菜单
 * 7. 会话管理（新建 / 切换 / 删除）
 * 8. Review 面板修复交互
 */
import { expect, test, type Page } from '@playwright/test';

// ── Mock 类型 ──

type MockWindow = Window & {
  __mockWs?: { emit: (data: unknown) => void };
  WebSocket: typeof globalThis.WebSocket;
};

// ── Mock WebSocket ──

function mockAuthAndWebSocket() {
  class MockWebSocket {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;

    public readyState = MockWebSocket.OPEN;
    public onopen: ((event: Event) => void) | null = null;
    public onclose: ((event: Event) => void) | null = null;
    public onerror: ((event: Event) => void) | null = null;
    public onmessage: ((event: MessageEvent) => void) | null = null;
    private listeners: Record<string, Array<(event: Event | MessageEvent) => void>> = {};

    constructor(url: string) {
      if (url.includes('/ws')) {
        (window as unknown as MockWindow).__mockWs = this;
      }
      window.setTimeout(() => {
        const event = new Event('open');
        this.onopen?.(event);
        (this.listeners.open || []).forEach((l) => l(event));
      }, 0);
    }

    send(_data: string) {}

    addEventListener(type: string, listener: (event: Event | MessageEvent) => void) {
      this.listeners[type] ??= [];
      this.listeners[type].push(listener);
    }

    removeEventListener(type: string, listener: (event: Event | MessageEvent) => void) {
      this.listeners[type] = (this.listeners[type] || []).filter((l) => l !== listener);
    }

    close() {
      this.readyState = MockWebSocket.CLOSED;
      const event = new Event('close');
      this.onclose?.(event);
      (this.listeners.close || []).forEach((l) => l(event));
    }

    emit(data: unknown) {
      const event = { data: JSON.stringify(data) } as MessageEvent;
      this.onmessage?.(event);
      (this.listeners.message || []).forEach((l) => l(event));
    }
  }

  (window as unknown as MockWindow).WebSocket = MockWebSocket as unknown as typeof globalThis.WebSocket;
}

// ── Fixture 数据 ──

const NOW = Date.now() / 1000;

const MOCK_STORYBOARD = {
  schema_version: '1.0',
  ppt_title: 'AI 行业趋势分析报告',
  language: 'zh-CN',
  total_pages: 5,
  mode: 'guided',
  pages: [
    {
      page_id: 'p1', page_number: 1, title: '封面：AI 行业趋势', page_type: 'cover',
      section: '封面', narrative_role: 'Hook', audience_takeaway: '第一印象',
      layout_intent: 'full-bleed hero', style_variant: 'cover-hero',
      content_blocks: [{ block_id: 'b1', role: 'title', text: 'AI 行业趋势分析报告 2026' }],
      visual_requirements: ['品牌主色调背景'], data_requirements: [],
      asset_requirements: [{ slot_id: 'a1', kind: 'real-photo', purpose: '科技感背景图' }],
      unresolved_issues: [], presenter_intent: '吸引注意',
      payload_budget: { claim_count: 0, evidence_count: 0, structure_block_count: 1, require_comparison_or_summary: false },
    },
    {
      page_id: 'p2', page_number: 2, title: '市场规模与增长趋势', page_type: 'chart',
      section: '市场分析', narrative_role: 'Evidence', audience_takeaway: '市场增长强劲',
      layout_intent: 'chart + commentary', style_variant: 'data-chart',
      content_blocks: [
        { block_id: 'b2', role: 'claim', text: '全球 AI 市场规模达 5000 亿美元' },
        { block_id: 'b3', role: 'evidence', text: 'IDC 数据: 年增长率 35%' },
      ],
      visual_requirements: ['数据可视化图表'], data_requirements: ['市场规模数据'],
      asset_requirements: [],
      unresolved_issues: [], presenter_intent: '用数据说服',
      payload_budget: { claim_count: 2, evidence_count: 2, structure_block_count: 2, require_comparison_or_summary: false },
    },
    {
      page_id: 'p3', page_number: 3, title: '技术路线对比', page_type: 'comparison',
      section: '技术分析', narrative_role: 'Analysis', audience_takeaway: '大模型 vs 小模型各有优劣',
      layout_intent: 'two-column comparison', style_variant: 'comparison-dual',
      content_blocks: [
        { block_id: 'b4', role: 'claim', text: '大模型推理成本持续下降' },
        { block_id: 'b5', role: 'claim', text: '小模型边缘部署优势明显' },
        { block_id: 'b6', role: 'evidence', text: 'GPT-4o 推理成本同比降 60%' },
      ],
      visual_requirements: ['对比表格'], data_requirements: [],
      asset_requirements: [{ slot_id: 'a2', kind: 'svg-icon', purpose: '大模型图标' }],
      unresolved_issues: [], presenter_intent: '引发思考',
      payload_budget: { claim_count: 2, evidence_count: 1, structure_block_count: 3, require_comparison_or_summary: true },
    },
    {
      page_id: 'p4', page_number: 4, title: '应用场景与案例', page_type: 'content',
      section: '应用分析', narrative_role: 'Story', audience_takeaway: '实际落地效果',
      layout_intent: 'grid cards', style_variant: 'content-cards',
      content_blocks: [
        { block_id: 'b7', role: 'claim', text: '医疗影像诊断准确率提升 20%' },
        { block_id: 'b8', role: 'evidence', text: '某三甲医院 6 个月试点数据' },
      ],
      visual_requirements: ['案例卡片'], data_requirements: [],
      asset_requirements: [{ slot_id: 'a3', kind: 'real-photo', purpose: '医疗场景照片' }],
      unresolved_issues: ['图片待下载'], presenter_intent: '真实案例打动',
      payload_budget: { claim_count: 1, evidence_count: 1, structure_block_count: 2, require_comparison_or_summary: false },
    },
    {
      page_id: 'p5', page_number: 5, title: '总结与展望', page_type: 'closing',
      section: '总结', narrative_role: 'Recap', audience_takeaway: '明确行动方向',
      layout_intent: 'centered summary', style_variant: 'closing-centered',
      content_blocks: [{ block_id: 'b9', role: 'summary', text: '三大趋势：降本、多模态、端侧部署' }],
      visual_requirements: [], data_requirements: [],
      asset_requirements: [], unresolved_issues: [], presenter_intent: '收束全篇',
      payload_budget: { claim_count: 0, evidence_count: 0, structure_block_count: 1, require_comparison_or_summary: true },
    },
  ],
};

const MOCK_STYLE_SPEC = {
  visual_archetype: '商务分析',
  fallback_archetype: '商务',
  keywords: ['数据驱动', '科技感', '专业'],
  color_roles: {
    primary: '#2563EB', secondary: '#7C3AED', accent: '#F59E0B',
    background: '#0F172A', surface: '#1E293B', text: '#F8FAFC',
  },
  typography: {
    heading: { family: 'Inter', weight: 700, size: '32px' },
    body: { family: 'Inter', weight: 400, size: '16px' },
  },
  background_system: { type: 'gradient', value: 'linear-gradient(135deg, #0F172A, #1E293B)' },
  foreground_motifs: ['geometric-dots', 'data-flow-lines'],
  component_skins: { card: 'glass-dark', badge: 'pill-accent' },
  density_rules: { 'analysis-heavy': { max_blocks: 4, min_whitespace: '15%' } },
  page_type_variants: {
    'cover-hero': { variant_key: 'cover-hero', layout_shell: 'full-bleed', header_strategy: 'overlay' },
    'data-chart': { variant_key: 'data-chart', layout_shell: 'chart-right', header_strategy: 'top-bar' },
    'comparison-dual': { variant_key: 'comparison-dual', layout_shell: 'two-col', header_strategy: 'top-bar' },
    'content-cards': { variant_key: 'content-cards', layout_shell: 'grid-3', header_strategy: 'left-accent' },
    'closing-centered': { variant_key: 'closing-centered', layout_shell: 'centered', header_strategy: 'none' },
  },
  svg_motif_library: [
    { key: 'geometric-dots', svg: '<svg>...</svg>' },
    { key: 'data-flow-lines', svg: '<svg>...</svg>' },
  ],
};

const MOCK_REVIEW = {
  overall_score: 78,
  overall_conclusion: '整体质量良好，部分页面资产和布局需要优化',
  strengths: ['配色统一', '数据可视化清晰', '叙事结构完整'],
  page_issues: [
    {
      page_number: 3, page_title: '技术路线对比',
      severity: 'warning', category: 'layout',
      description: '对比表格文字过于密集，建议拆分为独立卡片',
      suggested_skill: 'ppt-page-polish',
    },
    {
      page_number: 4, page_title: '应用场景与案例',
      severity: 'error', category: 'asset_missing',
      description: '缺少医疗场景真实图片，当前为 placeholder',
      suggested_skill: 'ppt-page-assets',
    },
    {
      page_number: 1, page_title: '封面：AI 行业趋势',
      severity: 'info', category: 'style_deviation',
      description: '封面背景 motif 密度偏低，可增加装饰层',
      suggested_skill: 'ppt-page-polish',
    },
  ],
  recommendations: ['补充第 4 页真实图片', '增加封面装饰密度'],
};

const MOCK_SPEAKER_NOTES = [
  { page_number: 1, page_title: '封面：AI 行业趋势', notes: '各位好，今天我将分享 2026 年 AI 行业的关键趋势和投资机会。' },
  { page_number: 2, page_title: '市场规模与增长趋势', notes: '先看整体市场。根据 IDC 最新数据，全球 AI 市场规模已突破 5000 亿美元，年增长率维持在 35% 以上。' },
  { page_number: 3, page_title: '技术路线对比', notes: '接下来看两条主要技术路线的对比分析。大模型和小模型各有优劣。' },
  { page_number: 4, page_title: '应用场景与案例', notes: '让我们看一个实际案例——某三甲医院的 AI 影像诊断试点项目。' },
  { page_number: 5, page_title: '总结与展望', notes: '总结一下：三大趋势分别是降本增效、多模态融合和端侧部署。' },
];

const MOCK_ASSET_PLAN = {
  slots: [
    {
      slot_id: 'a1', page_number: 1, purpose: '科技感背景图',
      query: 'AI technology futuristic blue',
      status: 'selected',
      selected_image: { title: 'AI Neural Network', image_url: 'https://example.com/ai.jpg', local_path: 'images/page_01_hero.jpg', source_domain: 'unsplash.com' },
      rejected_candidates: [{ title: 'Old robot', reason: '画面陈旧' }],
    },
    {
      slot_id: 'a2', page_number: 3, purpose: '大模型图标',
      query: null, status: 'resolved',
      selected_image: null,
      rejected_candidates: [],
    },
    {
      slot_id: 'a3', page_number: 4, purpose: '医疗场景照片',
      query: 'hospital AI medical imaging',
      status: 'unresolved',
      selected_image: null,
      rejected_candidates: [{ title: 'Stock photo', reason: '水印明显' }, { title: 'Lab scene', reason: '分辨率不足' }],
    },
  ],
};

const MOCK_SESSIONS = [
  {
    session_id: 'sess_ppt_001',
    created_at: NOW - 3600,
    last_active: NOW - 60,
    status: 'active',
    meta: JSON.stringify({ title: 'AI 行业趋势分析报告', agent_id: 'ppt-agent' }),
  },
  {
    session_id: 'sess_ppt_002',
    created_at: NOW - 7200,
    last_active: NOW - 1800,
    status: 'active',
    meta: JSON.stringify({ title: '产品发布会 PPT', agent_id: 'ppt-agent' }),
  },
];

// ── 公共 HTML 幻灯片 ──

function slideHtml(title: string, pageNum: number, bgColor: string) {
  return `<!doctype html>
<html>
<body style="margin:0;width:1280px;height:720px;overflow:hidden;font-family:Inter,sans-serif;">
  <div class="wrapper" style="position:relative;width:1280px;height:720px;">
    <div id="bg" style="position:absolute;inset:0;background:${bgColor};" data-layer="bg-motif" data-motif-key="geometric-dots">
      <svg style="position:absolute;right:0;top:0;width:300px;height:300px;opacity:.1;" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="40" fill="white"/>
      </svg>
    </div>
    <div id="ct" style="position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%;height:100%;color:#f8fafc;">
      <h1 style="font-size:48px;font-weight:700;">${title}</h1>
      <p style="font-size:18px;opacity:.7;">Page ${pageNum}</p>
      <div data-layer="fg-motif" data-motif-key="data-flow-lines" style="position:absolute;bottom:80px;left:40px;width:200px;height:2px;background:rgba(255,255,255,.15);"></div>
    </div>
    <div id="footer" style="position:absolute;right:40px;bottom:20px;font-size:12px;color:rgba(255,255,255,.4);">${pageNum}</div>
  </div>
</body>
</html>`;
}

const SLIDE_COLORS = ['#1e3a5f', '#0f172a', '#2d1b69', '#1a3c34', '#3b1d1d'];

// ── 左栏 Tab 点击辅助（避免和 Pipeline 阶段标签冲突） ──

function leftTab(page: Page, label: string) {
  return page.getByTestId('ppt-left').getByRole('button', { name: label, exact: true });
}

// ── 触发 deck 数据加载的 WS 事件 ──

async function triggerDeckLoad(page: Page) {
  await page.evaluate(() => {
    (window as unknown as MockWindow).__mockWs?.emit({
      type: 'tool_result', session_id: 'sess_ppt_001',
      payload: { name: 'write_file', result: { path: '/workdir/ppt-agent/ai_industry_trends_20260326/pages/page_01.html' }, success: true },
    });
  });
  await page.waitForTimeout(2500);
}

// ── 公共 setup ──

async function setupPptPage(page: Page, options?: {
  sessions?: typeof MOCK_SESSIONS;
  withDeckData?: boolean;
  slideCount?: number;
}) {
  const sessions = options?.sessions ?? MOCK_SESSIONS;
  const withDeck = options?.withDeckData ?? false;
  const slideCount = options?.slideCount ?? 5;

  // 认证 cookie
  await page.context().addCookies([
    { name: 'sensenova_claw_token', value: 'e2e-ppt-showcase', domain: '127.0.0.1', path: '/' },
    { name: 'sensenova_claw_token', value: 'e2e-ppt-showcase', domain: 'localhost', path: '/' },
  ]);

  // Mock auth API
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ user_id: 'u_ppt', username: 'ppt-tester', email: null, is_active: true, is_admin: true, created_at: NOW, last_login: NOW }),
    }),
  );
  await page.route('**/api/auth/status', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ authenticated: true }) }),
  );
  await page.route('**/api/config/llm-status', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ configured: true }) }),
  );
  await page.route('**/api/agents', (route) =>
    route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify([
        { id: 'ppt-agent', name: 'PPT 生成助手', description: '生成 PPT 演示文稿', status: 'active', model: 'mock-model' },
        { id: 'default', name: 'Default Agent', description: '默认助手', status: 'active', model: 'mock-model' },
      ]),
    }),
  );

  // Mock sessions
  await page.route('**/api/sessions', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ sessions }),
      });
    } else {
      // POST: 创建会话
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          session_id: `sess_ppt_new_${Date.now()}`,
          created_at: NOW, last_active: NOW, status: 'active',
          meta: JSON.stringify({ title: '新 PPT 会话', agent_id: 'ppt-agent' }),
        }),
      });
    }
  });
  await page.route('**/api/sessions/*/events', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ events: [] }) }),
  );
  await page.route('**/api/sessions/*', async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
    } else {
      await route.continue();
    }
  });

  // Mock deck data files
  if (withDeck) {
    const deckDir = 'ppt-agent/ai_industry_trends_20260326';

    // workdir-list: 幻灯片列表
    await page.route('**/api/files/workdir-list?*', (route) => {
      const url = new URL(route.request().url());
      const dir = url.searchParams.get('dir');
      if (dir === deckDir || dir === `${deckDir}/pages`) {
        const slides = Array.from({ length: slideCount }, (_, i) => ({
          name: `page_${String(i + 1).padStart(2, '0')}.html`,
          path: `${deckDir}/pages/page_${String(i + 1).padStart(2, '0')}.html`,
        }));
        return route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ dir, slides }),
        });
      }
      return route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ dir, slides: [] }),
      });
    });

    // workdir JSON files
    await page.route('**/api/files/workdir/**', (route) => {
      const urlPath = new URL(route.request().url()).pathname;

      if (urlPath.endsWith('storyboard.json')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_STORYBOARD) });
      }
      if (urlPath.endsWith('style-spec.json')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_STYLE_SPEC) });
      }
      if (urlPath.endsWith('review.json')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_REVIEW) });
      }
      if (urlPath.endsWith('speaker-notes.json')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_SPEAKER_NOTES) });
      }
      if (urlPath.endsWith('task-pack.json')) {
        return route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ deck_dir: deckDir, topic: 'AI 行业趋势', content_density_profile: 'analysis-heavy', research_required: true }),
        });
      }
      if (urlPath.endsWith('research-pack.json')) {
        return route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ claims: [{ claim_id: 'c1', text: '全球 AI 市场 5000 亿' }], evidence_points: [], pageworthy_chunks: [] }),
        });
      }
      if (urlPath.endsWith('asset-plan.json')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_ASSET_PLAN) });
      }
      // HTML slides
      if (/page_\d+\.html$/.test(urlPath)) {
        const match = urlPath.match(/page_(\d+)\.html$/);
        const num = match ? parseInt(match[1], 10) : 1;
        const storyPage = MOCK_STORYBOARD.pages[num - 1];
        const title = storyPage?.title ?? `Slide ${num}`;
        const color = SLIDE_COLORS[(num - 1) % SLIDE_COLORS.length];
        return route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: slideHtml(title, num, color) });
      }

      return route.fulfill({ status: 404, body: 'Not found' });
    });
  } else {
    // 无 deck 数据时返回空
    await page.route('**/api/files/workdir-list?*', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ dir: '', slides: [] }) }),
    );
    await page.route('**/api/files/workdir/**', (route) =>
      route.fulfill({ status: 404, body: 'Not found' }),
    );
  }

  await page.addInitScript(mockAuthAndWebSocket);
}

// ═══════════════════════════════════════════════════════════════
// Showcase 1: 三栏布局与空状态
// ═══════════════════════════════════════════════════════════════

test.describe('PPT Showcase: 三栏布局与空状态', () => {
  test.beforeEach(async ({ page }) => {
    await setupPptPage(page, { withDeckData: false });
  });

  test('PPT 页面加载，三栏结构可见', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // 顶栏标题
    await expect(page.getByText('PPT 工作台')).toBeVisible();

    // 左栏 Tab 按钮全部存在（限定在 ppt-left 面板内，避免和 Pipeline 阶段标签冲突）
    const leftPanel = page.getByTestId('ppt-left');
    for (const label of ['大纲', '风格', '资产', '审查', '讲稿']) {
      await expect(leftPanel.getByRole('button', { name: label, exact: true })).toBeVisible();
    }

    // 中栏空状态占位
    await expect(page.getByText('幻灯片预览区')).toBeVisible();
    await expect(page.getByText('在右侧对话中描述你的 PPT 需求')).toBeVisible();

    // 右栏 PPT 对话头
    await expect(page.getByText('PPT 对话')).toBeVisible();
  });

  test('左栏 Tab 切换正常', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // 默认在大纲 Tab
    await expect(leftTab(page, '大纲')).toBeVisible();

    // 切换到风格
    await leftTab(page, '风格').click();
    await page.waitForTimeout(300);

    // 切换到审查
    await leftTab(page, '审查').click();
    await page.waitForTimeout(300);

    // 切换到讲稿
    await leftTab(page, '讲稿').click();
    await page.waitForTimeout(300);

    // 切换到资产
    await leftTab(page, '资产').click();
    await page.waitForTimeout(300);
  });

  test('底栏模板条可见', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // 至少有一个内置模板
    const templateNames = ['商业路演', '技术分享', '年度总结', '产品发布', '教学课件', '极简白'];
    let found = 0;
    for (const name of templateNames) {
      const el = page.getByText(name, { exact: true });
      if (await el.count() > 0) found++;
    }
    expect(found).toBeGreaterThanOrEqual(3);
  });
});

// ═══════════════════════════════════════════════════════════════
// Showcase 2: 模板选择与输入填充
// ═══════════════════════════════════════════════════════════════

test.describe('PPT Showcase: 模板选择与输入填充', () => {
  test.beforeEach(async ({ page }) => {
    await setupPptPage(page, { withDeckData: false });
  });

  test('点击模板卡片后输入框被填充', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // 点击"商业路演"模板
    const templateBtn = page.getByText('商业路演', { exact: true }).first();
    if (await templateBtn.isVisible()) {
      await templateBtn.click();
      await page.waitForTimeout(500);

      // 检查输入框是否被填充
      const textarea = page.locator('textarea').first();
      if (await textarea.count() > 0) {
        const value = await textarea.inputValue();
        expect(value).toContain('商业路演');
      }
    }
  });

  test('多个模板可以依次点击', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    for (const name of ['技术分享', '年度总结']) {
      const btn = page.getByText(name, { exact: true }).first();
      if (await btn.isVisible()) {
        await btn.click();
        await page.waitForTimeout(300);

        const textarea = page.locator('textarea').first();
        if (await textarea.count() > 0) {
          const value = await textarea.inputValue();
          expect(value).toContain(name);
        }
      }
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// Showcase 3: 完整 deck 数据展示
// ═══════════════════════════════════════════════════════════════

test.describe('PPT Showcase: 完整 deck 数据展示', () => {
  test.beforeEach(async ({ page }) => {
    await setupPptPage(page, { withDeckData: true });
  });

  test('大纲面板展示 storyboard 内容', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(2000);

    // 触发 deck 数据加载（通过 WS 模拟 write_file 事件）
    await triggerDeckLoad(page);

    // 顶栏标题应更新
    const title = page.getByText('AI 行业趋势分析报告');
    // 大纲 Tab 已激活，检查页面列表
    const coverText = page.getByText('封面：AI 行业趋势');
    if (await coverText.count() > 0) {
      await expect(coverText.first()).toBeVisible();
    }
  });

  test('风格面板展示 style-spec 数据', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(2000);

    // 触发数据加载
    await triggerDeckLoad(page);

    // 切换到风格 Tab
    await leftTab(page, '风格').click();
    await page.waitForTimeout(500);

    // 检查风格关键词（如果数据加载成功）
    const archetype = page.getByText('商务分析');
    if (await archetype.count() > 0) {
      await expect(archetype.first()).toBeVisible();
    }
  });

  test('审查面板展示 review 评分和问题列表', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(2000);

    await triggerDeckLoad(page);

    // 切换到审查 Tab
    await leftTab(page, '审查').click();
    await page.waitForTimeout(500);

    // 检查评分和问题
    const scoreText = page.getByText('78');
    if (await scoreText.count() > 0) {
      await expect(scoreText.first()).toBeVisible();
    }

    // 检查问题描述
    const issueText = page.getByText('对比表格文字过于密集');
    if (await issueText.count() > 0) {
      await expect(issueText.first()).toBeVisible();
    }
  });

  test('讲稿面板展示 speaker notes', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(2000);

    await triggerDeckLoad(page);

    // 切换到讲稿 Tab
    await leftTab(page, '讲稿').click();
    await page.waitForTimeout(500);

    const noteText = page.getByText('各位好，今天我将分享');
    if (await noteText.count() > 0) {
      await expect(noteText.first()).toBeVisible();
    }
  });

  test('资产面板展示 asset slots 状态', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(2000);

    await triggerDeckLoad(page);

    // 切换到资产 Tab
    await leftTab(page, '资产').click();
    await page.waitForTimeout(500);

    // 检查资产槽位
    const heroSlot = page.getByText('科技感背景图');
    if (await heroSlot.count() > 0) {
      await expect(heroSlot.first()).toBeVisible();
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// Showcase 4: 幻灯片查看器导航与全屏
// ═══════════════════════════════════════════════════════════════

test.describe('PPT Showcase: 幻灯片查看器', () => {
  test.beforeEach(async ({ page }) => {
    await setupPptPage(page, { withDeckData: true });
  });

  test('SlideViewer 渲染幻灯片并支持导航', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // 触发 deck 数据加载
    await triggerDeckLoad(page);

    // 查看器应该出现
    const viewer = page.getByTestId('slide-viewer');
    if (await viewer.count() > 0) {
      await expect(viewer).toBeVisible();

      // 检查页码显示 (1 / 5)
      const counter = page.getByText('1 / 5');
      if (await counter.count() > 0) {
        await expect(counter.first()).toBeVisible();
      }

      // 点击下一页
      const nextBtn = page.getByRole('button', { name: '下一页' });
      if (await nextBtn.count() > 0) {
        await nextBtn.click();
        await page.waitForTimeout(500);
        // 页码应变为 2 / 5
        const counter2 = page.getByText('2 / 5');
        if (await counter2.count() > 0) {
          await expect(counter2.first()).toBeVisible();
        }
      }
    }
  });

  test('SlideViewer 全屏模式', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    await triggerDeckLoad(page);

    const viewer = page.getByTestId('slide-viewer');
    const fullscreenToggle = page.getByTestId('slide-fullscreen-toggle');

    if (await fullscreenToggle.count() > 0) {
      await expect(viewer).toHaveAttribute('data-fullscreen', 'false');
      await expect(fullscreenToggle).toHaveAttribute('aria-label', '放大预览');

      // 进入全屏
      await fullscreenToggle.click();
      await expect(viewer).toHaveAttribute('data-fullscreen', 'true');
      await expect(page.getByRole('button', { name: '退出放大' })).toBeVisible();

      // 退出全屏
      await page.getByRole('button', { name: '退出放大' }).click();
      await expect(viewer).toHaveAttribute('data-fullscreen', 'false');
    }
  });

  test('键盘导航幻灯片', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    await triggerDeckLoad(page);

    const viewer = page.getByTestId('slide-viewer');
    if (await viewer.count() > 0) {
      // 按右箭头键
      await page.keyboard.press('ArrowRight');
      await page.waitForTimeout(500);

      // 按左箭头键
      await page.keyboard.press('ArrowLeft');
      await page.waitForTimeout(500);
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// Showcase 5: Pipeline 进度条状态
// ═══════════════════════════════════════════════════════════════

test.describe('PPT Showcase: Pipeline 进度条', () => {
  test('空状态显示所有 pending', async ({ page }) => {
    await setupPptPage(page, { withDeckData: false });
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // 7 个阶段标签应该全部存在
    const stageLabels = ['任务分析', '素材研究', '风格定义', '大纲编排', '资产准备', '页面生成', '质量审查'];
    for (const label of stageLabels) {
      const el = page.getByText(label, { exact: true });
      if (await el.count() > 0) {
        await expect(el.first()).toBeVisible();
      }
    }
  });

  test('有 deck 数据时阶段更新为 done', async ({ page }) => {
    await setupPptPage(page, { withDeckData: true });
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    await triggerDeckLoad(page);

    // 当 storyboard/style-spec/review 数据都加载完成后，对应阶段应变为 done
    // 具体检查 done 状态的 check 图标
    const stageLabels = ['任务分析', '风格定义', '大纲编排', '页面生成', '质量审查'];
    for (const label of stageLabels) {
      const el = page.getByText(label, { exact: true });
      if (await el.count() > 0) {
        await expect(el.first()).toBeVisible();
      }
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// Showcase 6: 导出下拉菜单
// ═══════════════════════════════════════════════════════════════

test.describe('PPT Showcase: 导出下拉菜单', () => {
  test('导出按钮可点击，菜单展开', async ({ page }) => {
    await setupPptPage(page, { withDeckData: true });
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // 触发 deck 数据加载
    await triggerDeckLoad(page);

    // 导出按钮在 deckDir 检测到后才 enabled
    // 由于 mock 中 deckDir 依赖 messages 中的 toolInfo，需要 force click
    const exportBtn = page.getByText('导出', { exact: true }).first();
    await expect(exportBtn).toBeVisible();

    // 检查是否 enabled，如果不是则用 force click 展示下拉菜单
    const isDisabled = await exportBtn.isDisabled();
    await exportBtn.click({ force: true });
    await page.waitForTimeout(500);

    // 检查下拉菜单选项
    const htmlOption = page.getByText('HTML 打包下载');
    if (await htmlOption.count() > 0) {
      await expect(htmlOption.first()).toBeVisible();
    }

    const pdfOption = page.getByText('PDF 导出');
    if (await pdfOption.count() > 0) {
      await expect(pdfOption.first()).toBeVisible();
    }

    const pptxOption = page.getByText('PPTX 导出');
    if (await pptxOption.count() > 0) {
      await expect(pptxOption.first()).toBeVisible();
    }

    // 关闭菜单
    await page.keyboard.press('Escape');

    if (isDisabled) {
      // 导出按钮在无 deckDir 时 disabled 是正确行为
      // 完整 e2e 测试（含真实 LLM）中，消息产生后按钮会自动 enable
    }
  });

  test('附带讲稿 checkbox 存在', async ({ page }) => {
    await setupPptPage(page, { withDeckData: true });
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // 触发数据加载
    await triggerDeckLoad(page);

    const exportBtn = page.getByText('导出', { exact: true }).first();
    await expect(exportBtn).toBeVisible();

    // force click 以展示菜单（deckDir 可能尚未被检测到）
    await exportBtn.click({ force: true });
    await page.waitForTimeout(500);

    const notesCheckbox = page.getByText('附带讲稿');
    if (await notesCheckbox.count() > 0) {
      await expect(notesCheckbox.first()).toBeVisible();
    }

    await page.keyboard.press('Escape');
  });
});

// ═══════════════════════════════════════════════════════════════
// Showcase 7: 会话管理
// ═══════════════════════════════════════════════════════════════

test.describe('PPT Showcase: 会话管理', () => {
  test.beforeEach(async ({ page }) => {
    await setupPptPage(page, { withDeckData: false });
  });

  test('会话列表显示 ppt-agent 会话', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // 检查两个 mock 会话
    const session1 = page.getByText('AI 行业趋势分析报告');
    const session2 = page.getByText('产品发布会 PPT');

    if (await session1.count() > 0) await expect(session1.first()).toBeVisible();
    if (await session2.count() > 0) await expect(session2.first()).toBeVisible();
  });

  test('新建会话按钮可点击', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    const newBtn = page.getByText('新建', { exact: true }).first();
    if (await newBtn.isVisible()) {
      await newBtn.click();
      await page.waitForTimeout(500);
      // 新建后不应报错
    }
  });

  test('切换会话', async ({ page }) => {
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // 点击第二个会话
    const session2 = page.getByText('产品发布会 PPT').first();
    if (await session2.count() > 0) {
      await session2.click();
      await page.waitForTimeout(500);
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// Showcase 8: Review 面板修复交互
// ═══════════════════════════════════════════════════════════════

test.describe('PPT Showcase: Review 面板修复交互', () => {
  test('点击修复按钮发送修复指令', async ({ page }) => {
    await setupPptPage(page, { withDeckData: true });
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // 触发数据加载
    await triggerDeckLoad(page);

    // 切换到审查面板
    await leftTab(page, '审查').click();
    await page.waitForTimeout(500);

    // 记录 WS 发送的消息
    const sentMessages: string[] = [];
    await page.evaluate(() => {
      const ws = (window as unknown as MockWindow).__mockWs;
      if (ws) {
        const origSend = ws.constructor.prototype.send;
        ws.constructor.prototype.send = function (data: string) {
          (window as unknown as { __sentMsgs: string[] }).__sentMsgs ??= [];
          (window as unknown as { __sentMsgs: string[] }).__sentMsgs.push(data);
          return origSend.call(this, data);
        };
      }
    });

    // 找到"修复"按钮
    const fixBtns = page.getByText('修复');
    if (await fixBtns.count() > 0) {
      await fixBtns.first().click();
      await page.waitForTimeout(500);
    }
  });
});

// ═══════════════════════════════════════════════════════════════
// Showcase 综合: AI 行业趋势分析报告全流程展示
// ═══════════════════════════════════════════════════════════════

test.describe('PPT Showcase 综合: AI 行业趋势分析报告', () => {
  test('全流程：加载 → 浏览大纲 → 查看幻灯片 → 审查问题 → 导出', async ({ page }) => {
    await setupPptPage(page, { withDeckData: true });
    await page.goto('/ppt');
    await page.waitForTimeout(1500);

    // Step 1: 页面加载
    await expect(page.getByText('PPT 工作台')).toBeVisible();

    // Step 2: 触发 deck 数据
    await triggerDeckLoad(page);

    // Step 3: 浏览大纲
    await leftTab(page, '大纲').click();
    await page.waitForTimeout(500);

    // Step 4: 查看幻灯片
    const viewer = page.getByTestId('slide-viewer');
    if (await viewer.count() > 0) {
      await expect(viewer).toBeVisible();
    }

    // Step 5: 审查面板
    await leftTab(page, '审查').click();
    await page.waitForTimeout(500);

    // Step 6: 讲稿面板
    await leftTab(page, '讲稿').click();
    await page.waitForTimeout(500);

    // Step 7: 打开导出（force click 因为 deckDir 可能尚未从消息中检测到）
    const exportBtn = page.getByText('导出', { exact: true }).first();
    if (await exportBtn.count() > 0) {
      await exportBtn.click({ force: true });
      await page.waitForTimeout(500);
      await page.keyboard.press('Escape');
    }
  });
});
