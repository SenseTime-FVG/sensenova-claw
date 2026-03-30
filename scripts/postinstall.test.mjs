import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';

import {
  getInstallTasks,
  getMissingTools,
  runPostinstall,
  shouldUseShell,
} from './postinstall.mjs';

test('Windows 下启用 shell，其他平台不启用', () => {
  assert.equal(shouldUseShell('win32'), true);
  assert.equal(shouldUseShell('linux'), false);
  assert.equal(shouldUseShell('darwin'), false);
});

test('缺失工具检查会返回所有未通过检查的工具', () => {
  const missing = getMissingTools('win32', (command) => command === 'npm');

  assert.deepEqual(missing, ['uv']);
});

test('安装任务仍覆盖后端、前端和 WhatsApp bridge', () => {
  const rootDir = path.join(path.sep, 'tmp', 'agentos');
  const tasks = getInstallTasks(rootDir);

  assert.deepEqual(
    tasks.map((task) => ({
      title: task.title,
      command: task.command,
      args: task.args,
      cwd: task.cwd,
    })),
    [
      {
        title: '安装 Python 依赖',
        command: 'uv',
        args: ['sync'],
        cwd: rootDir,
      },
      {
        title: '安装前端依赖',
        command: 'npm',
        args: ['install'],
        cwd: path.join(rootDir, 'sensenova_claw', 'app', 'web'),
      },
      {
        title: '安装 WhatsApp bridge 依赖',
        command: 'npm',
        args: ['install'],
        cwd: path.join(rootDir, 'sensenova_claw', 'adapters', 'plugins', 'whatsapp', 'bridge'),
      },
    ]
  );
});

test('runPostinstall 在 Windows 下通过 shell 执行所有检查和安装步骤', () => {
  const rootDir = path.join(path.sep, 'tmp', 'agentos');
  const calls = [];
  const spawnImpl = (command, args, options) => {
    calls.push({
      command,
      args,
      cwd: options.cwd,
      shell: options.shell,
      stdio: options.stdio,
    });
    return { status: 0 };
  };

  const exitCode = runPostinstall({
    rootDir,
    platform: 'win32',
    spawnImpl,
  });

  assert.equal(exitCode, 0);
  assert.deepEqual(
    calls,
    [
      {
        command: 'uv',
        args: ['--version'],
        cwd: undefined,
        shell: true,
        stdio: 'ignore',
      },
      {
        command: 'npm',
        args: ['--version'],
        cwd: undefined,
        shell: true,
        stdio: 'ignore',
      },
      {
        command: 'uv',
        args: ['sync'],
        cwd: rootDir,
        shell: true,
        stdio: 'inherit',
      },
      {
        command: 'npm',
        args: ['install'],
        cwd: path.join(rootDir, 'sensenova_claw', 'app', 'web'),
        shell: true,
        stdio: 'inherit',
      },
      {
        command: 'npm',
        args: ['install'],
        cwd: path.join(rootDir, 'sensenova_claw', 'adapters', 'plugins', 'whatsapp', 'bridge'),
        shell: true,
        stdio: 'inherit',
      },
    ]
  );
});
