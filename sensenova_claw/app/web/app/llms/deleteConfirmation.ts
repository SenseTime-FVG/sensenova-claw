export type DeleteTargetType = 'provider' | 'model';

export interface DeleteConfirmationConfig {
  title: string;
  description: string;
  confirmLabel: string;
  persistToConfig: boolean;
}

export function buildDeleteConfirmationConfig(
  targetType: DeleteTargetType,
  targetName: string,
  options?: {
    relatedModelCount?: number;
    editingAll?: boolean;
  },
): DeleteConfirmationConfig {
  const relatedModelCount = options?.relatedModelCount ?? 0;
  const persistToConfig = !Boolean(options?.editingAll);

  if (targetType === 'provider') {
    const suffix = relatedModelCount > 0
      ? `其下关联的 ${relatedModelCount} 个 llm 也会一并删除。`
      : '其下暂时没有关联 llm。';
    return {
      title: '确认删除 provider',
      description: `确定删除 provider “${targetName}” 吗？${suffix}`,
      confirmLabel: '删除 provider',
      persistToConfig,
    };
  }

  return {
    title: '确认删除 llm',
    description: `确定删除 llm “${targetName}” 吗？`,
    confirmLabel: '删除 llm',
    persistToConfig,
  };
}
