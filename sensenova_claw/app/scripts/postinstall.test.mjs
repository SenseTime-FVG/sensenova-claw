import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';

import {
  getInstallTasks,
  runPostinstall,
  shouldUseShell,
} from './postinstall.mjs';

test('Windows 下启用 shell，其他平台不启用', () => {
  assert.equal(shouldUseShell('win32'), true);
  assert.equal(shouldUseShell('linux'), false);
  assert.equal(shouldUseShell('darwin'), false);
});

test('安装任务只覆盖 app/web 前端依赖', () => {
  const webDir = path.join(path.sep, 'tmp', 'agentos', 'sensenova_claw', 'app', 'web');
  const tasks = getInstallTasks(webDir);

  assert.deepEqual(tasks, [
    {
      title: '安装 Web 前端依赖',
      command: 'npm',
      args: ['install'],
      cwd: webDir,
    },
  ]);
});

test('runPostinstall 在 Windows 下通过 shell 执行 npm 检查和安装', () => {
  const webDir = path.join(path.sep, 'tmp', 'agentos', 'sensenova_claw', 'app', 'web');
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
    platform: 'win32',
    spawnImpl,
    webDir,
  });

  assert.equal(exitCode, 0);
  assert.deepEqual(calls, [
    {
      command: 'npm',
      args: ['--version'],
      cwd: undefined,
      shell: true,
      stdio: 'ignore',
    },
    {
      command: 'npm',
      args: ['install'],
      cwd: webDir,
      shell: true,
      stdio: 'inherit',
    },
  ]);
});
