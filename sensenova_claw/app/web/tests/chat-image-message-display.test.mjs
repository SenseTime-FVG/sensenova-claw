import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function readSource(relativePath) {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf8');
}

test('sendMessage 创建用户消息时应保留图片附件用于消息记录展示', () => {
  const source = readSource('contexts/ws/MessageContext.tsx');

  assert.match(source, /function addMsg\([^)]*attachments\?: ChatAttachmentRef\[\]/s);
  assert.match(source, /addMsg\('user', content \|\| `\[图片\] \$\{attachments\?\.length \|\| 0\}`, attachments\)/);
});

test('MessageBubble 应在用户消息中渲染图片附件预览', () => {
  const source = readSource('components/chat/MessageBubble.tsx');

  assert.match(source, /msg\.attachments\?\.length/);
  assert.match(source, /<img[\s\S]*src=\{attachmentPreviewUrl\(attachment\.path\)\}/);
  assert.match(source, /alt=\{attachment\.name\}/);
});
