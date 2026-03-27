import { spawnSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const RED = '\x1b[0;31m';
const GREEN = '\x1b[0;32m';
const YELLOW = '\x1b[1;33m';
const RESET = '\x1b[0m';

const currentFile = fileURLToPath(import.meta.url);
export const APP_DIR = path.resolve(path.dirname(currentFile), '..');
export const WEB_DIR = path.join(APP_DIR, 'web');

export function shouldUseShell(platform = process.platform) {
  return platform === 'win32';
}

export function commandExists(command, platform = process.platform, spawnImpl = spawnSync) {
  const result = spawnImpl(command, ['--version'], {
    shell: shouldUseShell(platform),
    stdio: 'ignore',
    env: process.env,
  });

  return result.status === 0;
}

export function getInstallTasks(webDir = WEB_DIR) {
  return [
    {
      title: '安装 Web 前端依赖',
      command: 'npm',
      args: ['install'],
      cwd: webDir,
    },
  ];
}

export function printMissingTools(missingTools) {
  console.error('');
  console.error(`${RED}✗ 缺少必要的工具: ${missingTools.join(' ')}${RESET}`);
  console.error('');
  console.error(`${YELLOW}npm (Node.js 包管理器):${RESET}`);
  console.error('  安装 Node.js (>= 18): https://nodejs.org/');
  console.error('');
  console.error(`安装完成后重新运行 ${GREEN}npm install${RESET}`);
}

export function runTask(task, platform = process.platform, spawnImpl = spawnSync) {
  console.log('');
  console.log(`${GREEN}▶ ${task.title}...${RESET}`);

  const result = spawnImpl(task.command, task.args, {
    cwd: task.cwd,
    stdio: 'inherit',
    shell: shouldUseShell(platform),
    env: process.env,
  });

  if (result.error) {
    throw new Error(`${task.command} ${task.args.join(' ')} 执行失败: ${result.error.message}`);
  }
  if (result.status !== 0) {
    throw new Error(`${task.command} ${task.args.join(' ')} 执行失败，退出码 ${result.status}`);
  }
}

export function runPostinstall({
  platform = process.platform,
  spawnImpl = spawnSync,
  webDir = WEB_DIR,
} = {}) {
  if (!commandExists('npm', platform, spawnImpl)) {
    printMissingTools(['npm']);
    return 1;
  }

  for (const task of getInstallTasks(webDir)) {
    runTask(task, platform, spawnImpl);
  }

  console.log('');
  console.log(`${GREEN}✔ app Web 依赖安装完成${RESET}`);
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === currentFile) {
  try {
    const exitCode = runPostinstall();
    process.exitCode = exitCode;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('');
    console.error(`${RED}✗ ${message}${RESET}`);
    process.exitCode = 1;
  }
}
