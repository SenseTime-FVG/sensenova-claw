export function getNewProviderValidationError(
  nextNameRaw: string,
  existingNames: string[],
): string {
  const nextName = nextNameRaw.trim().toLowerCase();
  if (!nextName) {
    return 'Provider 名称不能为空';
  }
  if (existingNames.includes(nextName)) {
    return `Provider 名称已存在: ${nextName}`;
  }
  return '';
}

export function getExistingProviderValidationError(
  currentName: string,
  nextNameRaw: string,
  existingNames: string[],
): string {
  const nextName = nextNameRaw.trim().toLowerCase();
  if (!nextName) {
    return 'Provider 名称不能为空';
  }
  if (nextName !== currentName && existingNames.includes(nextName)) {
    return `Provider 名称已存在: ${nextName}`;
  }
  return '';
}
