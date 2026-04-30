import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function readSource(relativePath) {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf8');
}

test('ChatInput 应支持浏览器原生文件拖拽上传，不仅是 react-dnd 站内拖拽', () => {
  const source = readSource('components/chat/ChatInput.tsx');

  assert.match(source, /const \[isDraggingFiles, setIsDraggingFiles\] = useState\(false\);/);
  assert.match(source, /const isNativeFileDrag = useCallback\(\(event: React\.DragEvent<HTMLDivElement>\) => \{/);
  assert.match(source, /const handleNativeDrop = useCallback\(async \(event: React\.DragEvent<HTMLDivElement>\) => \{/);
  assert.match(source, /event\.dataTransfer\.files/);
  assert.match(source, /onDragOver=\{handleNativeDragOver\}/);
  assert.match(source, /onDrop=\{handleNativeDrop\}/);
});

test('useFileUpload 应暴露可复用的 handleFiles 以支持 input 和拖拽两种来源', () => {
  const source = readSource('hooks/useFileUpload.ts');

  assert.match(source, /const handleFiles = useCallback\(async \(selectedFiles: FileList \| File\[\]\) => \{/);
  assert.match(source, /const handleFileSelect = useCallback\(async \(e: React\.ChangeEvent<HTMLInputElement>\) => \{/);
  assert.match(source, /await handleFiles\(selectedFiles\);/);
  assert.match(source, /handleFiles,/);
});
