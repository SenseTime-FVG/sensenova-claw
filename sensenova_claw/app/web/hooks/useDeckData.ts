'use client';

/**
 * useDeckData —— 从 deck_dir 加载所有 PPT 产物
 *
 * 监听聊天消息中的 write_file 事件来自动刷新。
 * 数据源：workdir/${deckDir}/ 下的 JSON 文件
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { jsonrepair } from 'jsonrepair';
import { authFetch, API_BASE } from '@/lib/authFetch';
import type { Storyboard } from '@/components/ppt/StoryboardPanel';
import type { StyleSpec } from '@/components/ppt/StylePanel';
import type { ReviewReport } from '@/components/ppt/ReviewPanel';
import type { SpeakerNote } from '@/components/ppt/SpeakerNotesPanel';
import { type PipelineStage, DEFAULT_STAGES } from '@/components/ppt/PipelineProgress';
import type { SlideSet } from '@/components/ppt/PPTViewer';
import type { ChatMessage } from '@/lib/chatTypes';

export interface AssetSlot {
  page_id: string;
  page_title: string;
  slot_id: string;
  purpose: string;
  source_caption: string;
  query: string;
  selected: boolean;
  selected_image: {
    title: string;
    image_url: string;
    local_path: string;
    source_page: string;
    source_domain: string;
  } | null;
  rejected_candidates: {
    image_url: string;
    rejection_stage: string;
    reason: string;
  }[];
  status: string;
  reason: string;
}

export interface AssetPlan {
  schema_version: string;
  deck_dir: string;
  slots: AssetSlot[];
}

export interface DeckData {
  deckDir: string | null;
  storyboard: Storyboard | null;
  styleSpec: StyleSpec | null;
  review: ReviewReport | null;
  speakerNotes: SpeakerNote[] | null;
  slideSet: SlideSet | null;
  assetPlan: AssetPlan | null;
  stages: PipelineStage[];
  loading: boolean;
  refresh: () => void;
}

/** 从 workdir 读取 JSON 文件，自动修复 LLM 常见的 JSON 语法错误 */
async function fetchJsonFromWorkdir(deckDir: string, filename: string): Promise<unknown | null> {
  try {
    const path = `${deckDir}/${filename}`;
    const res = await authFetch(`${API_BASE}/api/files/workdir/${path}`);
    if (!res.ok) return null;
    const text = await res.text();
    try {
      return JSON.parse(text);
    } catch {
      // JSON 解析失败，用 jsonrepair 修复（处理未转义引号、尾逗号等）
      console.warn(`[useDeckData] ${filename} JSON 解析失败，尝试修复...`);
      try {
        const repaired = JSON.parse(jsonrepair(text));
        console.info(`[useDeckData] ${filename} JSON 修复成功`);
        return repaired;
      } catch {
        console.error(`[useDeckData] ${filename} JSON 修复失败`);
        return null;
      }
    }
  } catch {
    return null;
  }
}

/** 从消息中检测 deck_dir */
function detectDeckDir(messages: ChatMessage[]): string | null {
  // 从 write_file 工具输出中查找 page_XX.html 路径
  const pageHtmlPattern = /page_\d+\.html/i;
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (!msg.toolInfo || msg.toolInfo.status !== 'completed') continue;

    if (msg.toolInfo.name === 'write_file') {
      const result = msg.toolInfo.result as Record<string, unknown> | undefined;
      const filePath = String(result?.file_path || msg.toolInfo.arguments?.file_path || '');
      const normalized = filePath.replace(/\\/g, '/');

      // 查找 workdir 之后的相对路径
      const marker = '/workdir/';
      const idx = normalized.indexOf(marker);
      if (idx !== -1) {
        const rel = normalized.slice(idx + marker.length);
        const lastSlash = rel.lastIndexOf('/');
        if (lastSlash > 0) {
          // 如果是 page_XX.html，取其父目录的父目录（去掉 pages/）
          const dir = rel.slice(0, lastSlash);
          if (pageHtmlPattern.test(rel) && dir.endsWith('/pages')) {
            return dir.slice(0, -6); // 去掉 /pages
          }
          return dir;
        }
      }
    }
  }

  // 兜底：从 storyboard/task-pack 路径推断
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (!msg.toolInfo) continue;
    const filePath = String(
      (msg.toolInfo.result as Record<string, unknown>)?.file_path ||
      msg.toolInfo.arguments?.file_path || ''
    ).replace(/\\/g, '/');

    for (const artifact of ['storyboard.json', 'task-pack.json', 'style-spec.json']) {
      if (filePath.includes(artifact)) {
        const marker = '/workdir/';
        const idx = filePath.indexOf(marker);
        if (idx !== -1) {
          const rel = filePath.slice(idx + marker.length);
          const lastSlash = rel.lastIndexOf('/');
          if (lastSlash > 0) return rel.slice(0, lastSlash);
        }
      }
    }
  }

  return null;
}

/** 从 workdir 获取幻灯片列表（先查顶层，再查 pages/ 子目录） */
async function fetchSlideSet(deckDir: string): Promise<SlideSet | null> {
  for (const suffix of ['', '/pages']) {
    try {
      const dir = deckDir + suffix;
      const res = await authFetch(`${API_BASE}/api/files/workdir-list?dir=${encodeURIComponent(dir)}`);
      if (!res.ok) continue;
      const data = await res.json();
      const slides = (data.slides || []) as { name: string; path: string }[];
      if (slides.length > 0) {
        return { dir: deckDir, slides };
      }
    } catch {
      // 继续尝试下一个
    }
  }
  return null;
}

/** 推断 pipeline 阶段 */
function inferStages(
  storyboard: Storyboard | null,
  styleSpec: StyleSpec | null,
  review: ReviewReport | null,
  slideSet: SlideSet | null,
  hasTaskPack: boolean,
  hasResearch: boolean,
  hasAssetPlan: boolean,
): PipelineStage[] {
  const stages = DEFAULT_STAGES.map(s => ({ ...s }));

  if (hasTaskPack)  stages[0].status = 'done';
  if (hasResearch)  stages[1].status = 'done';
  if (styleSpec)    stages[2].status = 'done';
  if (storyboard)   stages[3].status = 'done';
  if (hasAssetPlan) stages[4].status = 'done';
  if (slideSet)     stages[5].status = 'done';
  if (review)       stages[6].status = 'done';

  // 如果某个 pending 阶段后面已有 done 阶段，说明该阶段被跳过，也标记为 done
  let lastDone = -1;
  for (let i = stages.length - 1; i >= 0; i--) {
    if (stages[i].status === 'done') { lastDone = i; break; }
  }
  if (lastDone > 0) {
    for (let i = 0; i < lastDone; i++) {
      if (stages[i].status === 'pending') stages[i].status = 'done';
    }
  }

  // 找第一个 pending 标记为 active
  const firstPending = stages.findIndex(s => s.status === 'pending');
  if (firstPending > 0 && stages[firstPending - 1].status === 'done') {
    stages[firstPending].status = 'active';
  }

  return stages;
}

export function useDeckData(messages: ChatMessage[]): DeckData {
  const [deckDir, setDeckDir] = useState<string | null>(null);
  const [storyboard, setStoryboard] = useState<Storyboard | null>(null);
  const [styleSpec, setStyleSpec] = useState<StyleSpec | null>(null);
  const [review, setReview] = useState<ReviewReport | null>(null);
  const [speakerNotes, setSpeakerNotes] = useState<SpeakerNote[] | null>(null);
  const [slideSet, setSlideSet] = useState<SlideSet | null>(null);
  const [hasTaskPack, setHasTaskPack] = useState(false);
  const [hasResearch, setHasResearch] = useState(false);
  const [assetPlan, setAssetPlan] = useState<AssetPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const lastMsgCount = useRef(0);

  // 从消息自动检测 deckDir；会话切换（messages 清空再重建）时重置旧数据
  useEffect(() => {
    const detected = detectDeckDir(messages);
    if (detected !== deckDir) {
      setDeckDir(detected);
      if (!detected) {
        // 新会话尚无产物，清空旧数据
        setStoryboard(null);
        setStyleSpec(null);
        setReview(null);
        setSpeakerNotes(null);
        setSlideSet(null);
        setHasTaskPack(false);
        setHasResearch(false);
        setAssetPlan(null);
        lastMsgCount.current = 0;
      }
    }
  }, [messages, deckDir]);

  const refresh = useCallback(async () => {
    if (!deckDir) return;
    setLoading(true);
    try {
      const [sb, ss, rv, sn, slides, tp, rp, ap] = await Promise.all([
        fetchJsonFromWorkdir(deckDir, 'storyboard.json'),
        fetchJsonFromWorkdir(deckDir, 'style-spec.json'),
        fetchJsonFromWorkdir(deckDir, 'review.json'),
        fetchJsonFromWorkdir(deckDir, 'speaker-notes.json'),
        fetchSlideSet(deckDir),
        fetchJsonFromWorkdir(deckDir, 'task-pack.json'),
        fetchJsonFromWorkdir(deckDir, 'research-pack.json'),
        fetchJsonFromWorkdir(deckDir, 'asset-plan.json'),
      ]);

      // 兼容不同版本的字段名（如 deck_title → ppt_title）
      if (sb && typeof sb === 'object') {
        const raw = sb as Record<string, unknown>;
        if (!raw.ppt_title && raw.deck_title) raw.ppt_title = raw.deck_title;
        if (!raw.mode) raw.mode = 'fast';
      }
      setStoryboard(sb as Storyboard | null);
      setStyleSpec(ss as StyleSpec | null);
      setReview(rv as ReviewReport | null);
      setSpeakerNotes(Array.isArray(sn) ? sn as SpeakerNote[] : null);
      setSlideSet(slides);
      setHasTaskPack(!!tp);
      setHasResearch(!!rp);
      setAssetPlan(ap as AssetPlan | null);
    } catch {
      // 静默
    } finally {
      setLoading(false);
    }
  }, [deckDir]);

  // deckDir 变化时自动刷新
  useEffect(() => { refresh(); }, [refresh]);

  // 新消息到达时自动刷新（仅当消息数变化时）
  useEffect(() => {
    if (messages.length > lastMsgCount.current && deckDir) {
      lastMsgCount.current = messages.length;
      // 延迟一点，等文件写入完成
      const timer = setTimeout(refresh, 1000);
      return () => clearTimeout(timer);
    }
  }, [messages.length, deckDir, refresh]);

  const stages = inferStages(storyboard, styleSpec, review, slideSet, hasTaskPack, hasResearch, !!assetPlan);

  return {
    deckDir,
    storyboard,
    styleSpec,
    review,
    speakerNotes,
    slideSet,
    assetPlan,
    stages,
    loading,
    refresh,
  };
}
