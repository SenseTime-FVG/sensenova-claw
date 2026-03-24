/**
 * 文件上传工具：SHA-256 计算、存在性检查、上传（含进度）
 */
import { authFetch, API_BASE } from './authFetch';

/** 单文件检查结果 */
export interface FileCheckResult {
  exists: boolean;
  path: string;
  need_hash: boolean;
}

/** 文件夹检查结果 */
export interface DirCheckResult {
  exists: boolean;
  path: string;
  need_hash: boolean;
}

/** 上传进度回调 */
export type ProgressCallback = (loaded: number, total: number) => void;

/** 上传结果 */
export interface UploadResult {
  name: string;
  path: string;
  size: number;
}

// ---------- SHA-256 ----------

/** 文件大小上限（100MB），超过此大小跳过哈希计算直接上传 */
const MAX_HASH_SIZE = 100 * 1024 * 1024;

/** 计算文件的 SHA-256 哈希（Web Crypto API）。超过 100MB 返回 null。 */
export async function computeSHA256(file: File): Promise<string | null> {
  if (file.size > MAX_HASH_SIZE) return null;
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

// ---------- 检查接口 ----------

/** 检查单个文件是否已存在于 agent workdir */
export async function checkFile(
  name: string, size: number, agentId: string, hash?: string,
): Promise<FileCheckResult> {
  const resp = await authFetch(`${API_BASE}/api/files/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, size, agent_id: agentId, hash }),
  });
  if (!resp.ok) throw new Error(`文件检查失败: ${resp.status}`);
  return resp.json();
}

/** 检查文件夹是否已完整存在于 agent workdir */
export async function checkDir(
  folderName: string,
  files: { rel_path: string; size: number; hash?: string }[],
  agentId: string,
): Promise<DirCheckResult> {
  const resp = await authFetch(`${API_BASE}/api/files/check-dir`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_name: folderName, files, agent_id: agentId }),
  });
  if (!resp.ok) throw new Error(`文件夹检查失败: ${resp.status}`);
  return resp.json();
}

// ---------- 上传 ----------

const PROGRESS_THRESHOLD = 1024 * 1024; // 1MB

/** 上传文件到 agent workdir，>1MB 时通过 onProgress 回调进度 */
export function uploadFiles(
  files: { file: File; filename: string }[],
  agentId: string,
  onProgress?: ProgressCallback,
): Promise<UploadResult[]> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('agent_id', agentId);
    let totalSize = 0;
    for (const { file, filename } of files) {
      formData.append('files', file, filename);
      totalSize += file.size;
    }

    // 小文件用 fetch，大文件用 XMLHttpRequest 获取进度
    if (totalSize <= PROGRESS_THRESHOLD || !onProgress) {
      authFetch(`${API_BASE}/api/files/upload`, {
        method: 'POST',
        body: formData,
      })
        .then(resp => resp.json())
        .then(data => resolve(data.uploaded || []))
        .catch(reject);
      return;
    }

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/api/files/upload`);
    xhr.withCredentials = true;

    // 从 cookie 读取 token
    const tokenMatch = document.cookie.match(/(?:^|; )sensenova_claw_token=([^;]*)/);
    if (tokenMatch) {
      xhr.setRequestHeader('Authorization', `Bearer ${decodeURIComponent(tokenMatch[1])}`);
    }

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(e.loaded, e.total);
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText);
          resolve(data.uploaded || []);
        } catch {
          reject(new Error('上传响应解析失败'));
        }
      } else {
        reject(new Error(`上传失败: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error('上传网络错误'));
    xhr.send(formData);
  });
}

// ---------- 编排：单文件去重+上传 ----------

export interface FileUploadFlowResult {
  path: string;           // 绝对路径
  uploaded: boolean;       // true=新上传，false=已存在
}

/** 单文件去重+上传流程 */
export async function singleFileFlow(
  file: File,
  agentId: string,
  onProgress?: ProgressCallback,
): Promise<FileUploadFlowResult> {
  // 1. 检查 name + size
  const check1 = await checkFile(file.name, file.size, agentId);
  if (check1.exists) {
    return { path: check1.path, uploaded: false };
  }

  // 2. 如果 need_hash，计算 SHA-256 再检查
  if (check1.need_hash) {
    const hash = await computeSHA256(file);
    if (hash) {
      const check2 = await checkFile(file.name, file.size, agentId, hash);
      if (check2.exists) {
        return { path: check2.path, uploaded: false };
      }
    }
  }

  // 3. 上传
  const results = await uploadFiles(
    [{ file, filename: file.name }],
    agentId,
    onProgress,
  );
  if (results.length === 0) throw new Error('上传返回空结果');
  return { path: results[0].path, uploaded: true };
}

// ---------- 编排：文件夹去重+上传 ----------

export interface DirUploadFlowResult {
  path: string;           // 文件夹绝对路径
  uploaded: boolean;
}

/** 文件夹去重+上传流程 */
export async function dirUploadFlow(
  folderName: string,
  files: File[],
  agentId: string,
  onProgress?: ProgressCallback,
): Promise<DirUploadFlowResult> {
  // 构造文件列表（包含相对路径和大小）
  const fileItems = files.map(f => {
    const relPath = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
    // 去掉顶层文件夹名前缀，因为 check-dir 已经有 folder_name
    const parts = relPath.split('/');
    const withoutTop = parts.slice(1).join('/');
    return { rel_path: withoutTop || f.name, size: f.size, file: f };
  });

  // 1. 检查 name + size
  const check1 = await checkDir(
    folderName,
    fileItems.map(f => ({ rel_path: f.rel_path, size: f.size })),
    agentId,
  );
  if (check1.exists) {
    return { path: check1.path, uploaded: false };
  }

  // 2. 如果 need_hash，计算所有文件 SHA-256 再检查
  if (check1.need_hash) {
    const itemsWithHash: { rel_path: string; size: number; hash?: string }[] = [];
    let allHashed = true;
    for (const f of fileItems) {
      const hash = await computeSHA256(f.file);
      if (!hash) { allHashed = false; break; }
      itemsWithHash.push({ rel_path: f.rel_path, size: f.size, hash });
    }
    if (allHashed && itemsWithHash.length === fileItems.length) {
      const check2 = await checkDir(folderName, itemsWithHash, agentId);
      if (check2.exists) {
        return { path: check2.path, uploaded: false };
      }
    }
  }

  // 3. 整个文件夹重新上传
  const uploadItems = files.map(f => {
    const relPath = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
    return { file: f, filename: relPath };
  });
  const results = await uploadFiles(uploadItems, agentId, onProgress);
  if (results.length === 0) throw new Error('上传返回空结果');

  // 从第一个上传结果推算文件夹绝对路径
  const firstPath = results[0].path;
  const folderIdx = firstPath.lastIndexOf(`/${folderName}/`);
  const folderPath = folderIdx >= 0
    ? firstPath.substring(0, folderIdx + folderName.length + 1)
    : firstPath.substring(0, firstPath.lastIndexOf('/'));

  return { path: folderPath, uploaded: true };
}
