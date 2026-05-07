export function getNewModelValidationError(
  nextNameRaw: string,
  existingNames: string[],
): string {
  const nextName = nextNameRaw.trim();
  if (!nextName) {
    return 'LLM 名称不能为空';
  }
  if (existingNames.includes(nextName)) {
    return `LLM 名称已存在: ${nextName}`;
  }
  return '';
}

export function getExistingModelValidationError(
  currentName: string,
  nextNameRaw: string,
  existingNames: string[],
): string {
  const nextName = nextNameRaw.trim();
  if (!nextName) {
    return 'LLM 名称不能为空';
  }
  if (nextName !== currentName && existingNames.includes(nextName)) {
    return `LLM 名称已存在: ${nextName}`;
  }
  return '';
}
