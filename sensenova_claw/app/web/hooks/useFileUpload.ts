'use client';

import { useState, useCallback } from 'react';
import { singleFileFlow, dirUploadFlow, type ProgressCallback } from '@/lib/fileUpload';
import { type UploadProgressItem } from '@/components/chat/UploadProgress';

interface UseFileUploadOptions {
  selectedAgent: string;
  onUploadSuccess: (path: string) => void;
}

export function useFileUpload({ selectedAgent, onUploadSuccess }: UseFileUploadOptions) {
  const [uploadItems, setUploadItems] = useState<UploadProgressItem[]>([]);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    const fileList = Array.from(selectedFiles);
    const firstFile = fileList[0];
    const relPath = (firstFile as File & { webkitRelativePath?: string }).webkitRelativePath;
    const isFolder = Boolean(relPath);

    if (isFolder) {
      // 文件夹上传
      const topFolder = relPath!.split('/')[0];
      const itemId = `upload_${Date.now()}`;
      const totalSize = fileList.reduce((sum, f) => sum + f.size, 0);
      const showProgress = totalSize > 1024 * 1024;

      setUploadItems(prev => [...prev, {
        id: itemId, name: topFolder,
        percent: showProgress ? 0 : null,
        status: 'checking',
      }]);

      try {
        const onProgress: ProgressCallback | undefined = showProgress
          ? (loaded, total) => setUploadItems(prev =>
              prev.map(it => it.id === itemId ? { ...it, percent: Math.round(loaded / total * 100), status: 'uploading' } : it))
          : undefined;

        const result = await dirUploadFlow(topFolder, fileList, selectedAgent, onProgress);
        onUploadSuccess(result.path);
        setUploadItems(prev => prev.map(it => it.id === itemId ? { ...it, status: 'done', percent: 100 } : it));
      } catch (err) {
        setUploadItems(prev => prev.map(it => it.id === itemId
          ? { ...it, status: 'error', error: err instanceof Error ? err.message : '上传失败' } : it));
      }
    } else {
      // 单文件或多文件上传
      for (const file of fileList) {
        const itemId = `upload_${Date.now()}_${file.name}`;
        const showProgress = file.size > 1024 * 1024;

        setUploadItems(prev => [...prev, {
          id: itemId, name: file.name,
          percent: showProgress ? 0 : null,
          status: 'checking',
        }]);

        try {
          const onProgress: ProgressCallback | undefined = showProgress
            ? (loaded, total) => setUploadItems(prev =>
                prev.map(it => it.id === itemId ? { ...it, percent: Math.round(loaded / total * 100), status: 'uploading' } : it))
            : undefined;

          const result = await singleFileFlow(file, selectedAgent, onProgress);
          onUploadSuccess(result.path);
          setUploadItems(prev => prev.map(it => it.id === itemId ? { ...it, status: 'done', percent: 100 } : it));
        } catch (err) {
          setUploadItems(prev => prev.map(it => it.id === itemId
            ? { ...it, status: 'error', error: err instanceof Error ? err.message : '上传失败' } : it));
        }
      }
    }

    // 3秒后清除已完成的进度项
    setTimeout(() => {
      setUploadItems(prev => prev.filter(it => it.status !== 'done'));
    }, 3000);

    // 重置 input value 以允许再次选择相同文件
    e.target.value = '';
  }, [selectedAgent, onUploadSuccess]);

  return {
    uploadItems,
    handleFileSelect,
  };
}
