// 文件类型分类工具函数

export type FilePreviewType =
  | 'ppt-folder'   // PPT 文件夹（含 page_*.html）
  | 'html'         // HTML 文件
  | 'text'         // 纯文本 / 代码文件
  | 'markdown'     // Markdown
  | 'image'        // 图片
  | 'pdf'          // PDF
  | 'system'       // 需要系统应用打开的文件（docx, pptx 等）
  | 'binary'       // 不可预览的二进制文件
  | 'unknown';     // 未知类型（fallback 尝试纯文本）

const TEXT_EXTENSIONS = new Set([
  '.txt', '.log', '.json', '.yaml', '.yml', '.xml', '.csv', '.ini', '.conf', '.cfg',
  '.sh', '.bat', '.ps1', '.py', '.js', '.ts', '.tsx', '.jsx', '.css', '.scss', '.less',
  '.sql', '.rs', '.go', '.java', '.c', '.cpp', '.h', '.hpp', '.toml', '.env',
  '.properties', '.gitignore', '.dockerignore', '.editorconfig', '.prettierrc',
  '.vue', '.svelte', '.rb', '.php', '.swift', '.kt', '.scala', '.lua', '.r',
  '.makefile', '.cmake', '.gradle', '.sbt',
]);

const IMAGE_EXTENSIONS = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.ico',
]);

const SYSTEM_EXTENSIONS = new Set([
  '.docx', '.pptx', '.xlsx', '.doc', '.xls',
]);

const BINARY_EXTENSIONS = new Set([
  '.exe', '.dll', '.so', '.dylib', '.bin',
  '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',
  '.msi', '.dmg', '.iso',
  '.woff', '.woff2', '.ttf', '.otf', '.eot',
  '.mp3', '.mp4', '.avi', '.mkv', '.mov', '.wav', '.flac',
  '.o', '.obj', '.class', '.pyc', '.pyd',
]);

/** 获取文件扩展名（小写） */
function getExtension(filename: string): string {
  const lastDot = filename.lastIndexOf('.');
  if (lastDot === -1) return '';
  return filename.slice(lastDot).toLowerCase();
}

/** 根据文件扩展名判断预览类型 */
export function getFilePreviewType(filename: string): FilePreviewType {
  const ext = getExtension(filename);

  if (ext === '.html' || ext === '.htm') return 'html';
  if (ext === '.md' || ext === '.markdown') return 'markdown';
  if (ext === '.pdf') return 'pdf';
  if (IMAGE_EXTENSIONS.has(ext)) return 'image';
  if (TEXT_EXTENSIONS.has(ext)) return 'text';
  if (SYSTEM_EXTENSIONS.has(ext)) return 'system';
  if (BINARY_EXTENSIONS.has(ext)) return 'binary';
  return 'unknown';
}

/** 文件是否可在前端预览 */
export function isPreviewable(filename: string): boolean {
  const type = getFilePreviewType(filename);
  return type !== 'system' && type !== 'binary';
}

/** 检查子节点列表是否为 PPT 文件夹 */
export function isPPTFolder(children: { name: string }[]): boolean {
  return children.some(c => /^page_\d+\.html$/i.test(c.name));
}

/** 根据扩展名猜测语法高亮语言 */
export function guessLanguage(filename: string): string | undefined {
  const ext = getExtension(filename);
  const map: Record<string, string> = {
    '.js': 'javascript', '.jsx': 'javascript',
    '.ts': 'typescript', '.tsx': 'typescript',
    '.py': 'python', '.rb': 'ruby', '.go': 'go', '.rs': 'rust',
    '.java': 'java', '.c': 'c', '.cpp': 'cpp', '.h': 'c', '.hpp': 'cpp',
    '.css': 'css', '.scss': 'scss', '.less': 'less',
    '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml',
    '.xml': 'xml', '.html': 'html', '.htm': 'html',
    '.sql': 'sql', '.sh': 'bash', '.bat': 'dos',
    '.toml': 'toml', '.ini': 'ini',
    '.php': 'php', '.swift': 'swift', '.kt': 'kotlin',
    '.scala': 'scala', '.lua': 'lua', '.r': 'r',
    '.vue': 'xml', '.svelte': 'xml',
    '.md': 'markdown', '.markdown': 'markdown',
  };
  return map[ext];
}
