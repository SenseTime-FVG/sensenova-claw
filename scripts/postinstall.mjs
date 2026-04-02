import { spawnSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const RED = '\x1b[0;31m';
const GREEN = '\x1b[0;32m';
const YELLOW = '\x1b[1;33m';
const RESET = '\x1b[0m';

const currentFile = fileURLToPath(import.meta.url);
export const ROOT_DIR = path.resolve(path.dirname(currentFile), '..');

const INSTALL_GUIDES = {
  uv: [
    'uv (Python 包管理器):',
    '  官方安装指南: https://docs.astral.sh/uv/getting-started/installation/',
  ],
  npm: [
    'npm (Node.js 包管理器):',
    '  安装 Node.js (>= 18): https://nodejs.org/',
  ],
};

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

export function getMissingTools(platform = process.platform, checkCommand = commandExists) {
  return ['uv', 'npm'].filter((tool) => !checkCommand(tool, platform));
}

export function getInstallTasks(rootDir = ROOT_DIR) {
  return [
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
  ];
}

export function printMissingTools(missingTools) {
  console.error('');
  console.error(`${RED}✗ 缺少必要的工具: ${missingTools.join(' ')}${RESET}`);
  console.error('');
  console.error('请按以下指南安装：');
  console.error('');

  for (const tool of missingTools) {
    const lines = INSTALL_GUIDES[tool] ?? [`${tool}:`, '  请安装后重试。'];
    console.error(`${YELLOW}${lines[0]}${RESET}`);
    for (const line of lines.slice(1)) {
      console.error(line);
    }
    console.error('');
  }

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
  rootDir = ROOT_DIR,
  platform = process.platform,
  spawnImpl = spawnSync,
} = {}) {
  const missingTools = getMissingTools(platform, (command, currentPlatform) =>
    commandExists(command, currentPlatform, spawnImpl)
  );

  if (missingTools.length > 0) {
    printMissingTools(missingTools);
    return 1;
  }

  for (const task of getInstallTasks(rootDir)) {
    runTask(task, platform, spawnImpl);
  }

  console.log('');
  console.log(`${GREEN}✔ 所有依赖安装完成${RESET}`);
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
