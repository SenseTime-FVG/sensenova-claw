export function shouldSubmitInlineRename(params: {
  key: string;
  isComposing?: boolean;
  nativeIsComposing?: boolean;
  keyCode?: number;
}): boolean {
  if (params.key !== 'Enter') {
    return false;
  }
  if (params.isComposing || params.nativeIsComposing) {
    return false;
  }
  // 中文输入法确认阶段常见 keyCode=229，此时不应提交。
  if (params.keyCode === 229) {
    return false;
  }
  return true;
}
