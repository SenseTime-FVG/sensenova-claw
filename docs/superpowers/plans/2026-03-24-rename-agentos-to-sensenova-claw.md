# Rename sensenova-claw → sensenova-claw Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename all "sensenova-claw" references to "sensenova-claw" (or `sensenova_claw` for Python identifiers) across the entire codebase.

**Architecture:** One-shot bulk rename — directory renames first, then string replacements ordered by length (longest first) to avoid substring collisions, with `.py` files using underscore variant and all other files using hyphen variant.

**Tech Stack:** git mv, sed, grep, Python, npm

**Spec:** `docs/superpowers/specs/2026-03-24-rename-sensenova-claw-to-sensenova-claw-design.md`

---

### Task 1: Create feature branch

**Files:** None

- [ ] **Step 1: Create and checkout feature branch**

```bash
git checkout -b feat/rename-sensenova-claw
```

- [ ] **Step 2: Verify clean state**

```bash
git status
```

Expected: clean working tree on `feat/rename-sensenova-claw`

---

### Task 2: Directory renames and deletions

**Files:**
- Rename: `sensenova_claw/` → `sensenova_claw/`
- Rename: `.sensenova-claw/` → `.sensenova-claw/`
- Delete: `docs_raw/`

- [ ] **Step 1: Rename main Python package directory**

```bash
git mv sensenova_claw/ sensenova_claw/
```

- [ ] **Step 2: Rename runtime config directory**

```bash
git mv .sensenova-claw/ .sensenova-claw/
```

- [ ] **Step 3: Delete docs_raw directory**

```bash
rm -rf docs_raw/
git add -A docs_raw/
```

- [ ] **Step 4: Commit directory renames**

```bash
git add -A
git commit -m "refactor: rename sensenova_claw/ to sensenova_claw/, .sensenova-claw/ to .sensenova-claw/, delete docs_raw/"
```

---

### Task 3: Batch string replacement — Phase 2a (precise rules, all files)

This task applies the first 21 replacement rules from the spec. Each rule targets a specific string and replaces it globally across all text files. Rules are applied in length-descending order.

**Files:** All text files (`.py`, `.ts`, `.tsx`, `.yml`, `.yaml`, `.json`, `.sh`, `.ps1`, `.bat`, `.md`, `.toml`, `.cfg`, `.gitignore`) excluding `uv.lock`, `package-lock.json`, `node_modules/`, `.git/`

- [ ] **Step 1: Run batch replacement script**

Create and execute a shell script that applies all Phase 2a rules using `find` + `sed`. The script must:
- Target text file extensions listed above **plus extensionless dotfiles** (`.gitignore`)
- Exclude `uv.lock`, `package-lock.json`, `node_modules/`, `.git/`, `.venv/`
- Apply rules in this exact order (longest match first):

```bash
#!/bin/bash
set -e

# Find all target files (excluding lock files and binary dirs)
# NOTE: includes .gitignore (extensionless dotfile)
find . \( -path ./node_modules -o -path ./.git -o -path ./.venv \) -prune -o \
  \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.yml" -o -name "*.yaml" \
     -o -name "*.json" -o -name "*.sh" -o -name "*.ps1" -o -name "*.bat" -o -name "*.md" \
     -o -name "*.toml" -o -name "*.cfg" -o -name "*.mjs" -o -name "*.txt" \
     -o -name ".gitignore" \) \
  ! -name "uv.lock" ! -name "package-lock.json" -print0 | \
xargs -0 sed -i \
  -e 's/SENSENOVA_CLAW_REPO_BRANCH/SENSENOVA_CLAW_REPO_BRANCH/g' \
  -e 's/SENSENOVA_CLAW_REPO_URL/SENSENOVA_CLAW_REPO_URL/g' \
  -e 's/SENSENOVA_CLAW_REPO_REF/SENSENOVA_CLAW_REPO_REF/g' \
  -e 's/SENSENOVA_CLAW_DEBUG_LLM/SENSENOVA_CLAW_DEBUG_LLM/g' \
  -e 's/SENSENOVA_CLAW_TOKEN/SENSENOVA_CLAW_TOKEN/g' \
  -e 's/SENSENOVA_CLAW_HOME/SENSENOVA_CLAW_HOME/g' \
  -e 's/sensenova_claw_frontend/sensenova_claw_frontend/g' \
  -e 's/sensenova_claw_token/sensenova_claw_token/g' \
  -e 's/sensenova_claw_home/sensenova_claw_home/g' \
  -e 's/sensenova-claw-whatsapp-bridge/sensenova-claw-whatsapp-bridge/g' \
  -e 's/sensenova-claw-frontend/sensenova-claw-frontend/g' \
  -e 's/#sensenova-claw-workdir:/#sensenova-claw-workdir:/g' \
  -e 's/#sensenova-claw-file:/#sensenova-claw-file:/g' \
  -e 's/sensenova-claw:open-slide-preview/sensenova-claw:open-slide-preview/g' \
  -e 's/from sensenova_claw/from sensenova_claw/g' \
  -e 's/import sensenova_claw/import sensenova_claw/g' \
  -e 's/sensenova-claw\.app\.main/sensenova_claw.app.main/g' \
  -e 's/sensenova-claw\.app\.gateway/sensenova_claw.app.gateway/g' \
  -e 's|sensenova_claw/|sensenova_claw/|g' \
  -e 's/\.sensenova-claw/.sensenova-claw/g' \
  -e 's/sensenova-claw\.db/sensenova-claw.db/g' \
  -e 's/Sensenova-Claw/Sensenova-Claw/g'
```

**关键新增规则**: `s|sensenova_claw/|sensenova_claw/|g` 在 `.sensenova-claw` 规则之前执行，确保所有文件系统路径（如 `sensenova_claw/app/web`、`sensenova_claw/adapters/plugins/`）统一替换为 `sensenova_claw/`（下划线），而非被 Phase 2b 的兜底规则错误替换为 `sensenova-claw/`（连字符）。

- [ ] **Step 2: Verify Phase 2a replacements**

```bash
# Check that specific known patterns were replaced
grep -rn "SENSENOVA_CLAW_HOME" --include="*.py" --include="*.sh" --include="*.ps1" . | grep -v node_modules | grep -v .venv | grep -v .git
```

Expected: no results (all replaced)

- [ ] **Step 3: Commit Phase 2a**

```bash
git add -A
git commit -m "refactor: apply Phase 2a string replacements (precise rules)"
```

---

### Task 4: Batch string replacement — Phase 2b (catch-all, file-type split)

**Files:** Same file set as Task 3, but only files still containing `sensenova-claw` after Phase 2a.

- [ ] **Step 1: Replace remaining `sensenova-claw` in .py files with underscore variant**

```bash
find . \( -path ./node_modules -o -path ./.git -o -path ./.venv \) -prune -o \
  -name "*.py" ! -name "uv.lock" -print0 | \
xargs -0 sed -i 's/sensenova_claw/sensenova_claw/g'
```

- [ ] **Step 2: Replace remaining `sensenova-claw` in all other text files with hyphen variant**

```bash
find . \( -path ./node_modules -o -path ./.git -o -path ./.venv \) -prune -o \
  \( -name "*.ts" -o -name "*.tsx" -o -name "*.yml" -o -name "*.yaml" \
     -o -name "*.json" -o -name "*.sh" -o -name "*.ps1" -o -name "*.bat" -o -name "*.md" \
     -o -name "*.toml" -o -name "*.cfg" -o -name "*.mjs" -o -name "*.txt" \
     -o -name ".gitignore" \) \
  ! -name "uv.lock" ! -name "package-lock.json" -print0 | \
xargs -0 sed -i 's/sensenova_claw/sensenova-claw/g'
```

- [ ] **Step 3: Verify no `sensenova-claw` remains in target files**

```bash
grep -ri "sensenova-claw" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.yml" --include="*.yaml" --include="*.json" --include="*.sh" --include="*.ps1" --include="*.bat" --include="*.md" --include="*.toml" . | grep -v node_modules | grep -v .venv | grep -v .git | grep -v uv.lock | grep -v package-lock.json
# Also check .gitignore specifically
grep -n "sensenova-claw" .gitignore
```

Expected: no results

- [ ] **Step 4: Critical safety check — no hyphens in Python identifiers**

```bash
grep -rn "sensenova-claw" --include="*.py" . | grep -v node_modules | grep -v .venv | grep -v .git
```

Review output: lines containing `sensenova-claw` in .py files should only appear inside **strings** (quotes), **comments** (#), or **URLs**. If any appear as bare identifiers (variable names, function names, class attributes), they are bugs and must be fixed to use `sensenova_claw`.

- [ ] **Step 5: Verify no hyphenated filesystem paths**

```bash
# Check for sensenova-claw/ (hyphenated with trailing slash) — these are likely broken filesystem paths
# The correct filesystem path is sensenova_claw/ (underscore)
grep -rn "sensenova-claw/" --include="*.json" --include="*.sh" --include="*.bat" --include="*.toml" --include="*.yml" --include="*.yaml" --include="*.md" --include="*.cfg" . | grep -v node_modules | grep -v .venv | grep -v .git
grep -n "sensenova-claw/" .gitignore
```

If any results appear, they are filesystem paths that should use `sensenova_claw/` (underscore). Fix them. Note: `sensenova-claw/` in URLs (like `github.com/SenseTime-FVG/sensenova-claw/`) is correct.

- [ ] **Step 6: Commit Phase 2b**

```bash
git add -A
git commit -m "refactor: apply Phase 2b catch-all string replacements"
```

---

### Task 5: Manual fixes for special files

After batch replacement, some files need manual review and correction because they have mixed contexts (e.g., pyproject.toml has both Python module paths with underscores and package name with hyphens).

**Files:**
- Modify: `pyproject.toml`
- Modify: `package.json` (root)
- Modify: `sensenova_claw/app/web/package.json`
- Modify: `sensenova_claw/adapters/plugins/whatsapp/bridge/package.json`
- Modify: `.gitignore`
- Modify: `scripts/postinstall.sh`
- Modify: `scripts/dev.sh`
- Modify: `scripts/dev.bat`
- Modify: `scripts/auto_update.sh`
- Modify: `config_example.yml`

- [ ] **Step 1: Verify and fix pyproject.toml**

Expected final state:
```toml
[project]
name = "sensenova-claw"
version = "0.5.0"
description = "Sensenova-Claw - 基于事件驱动架构的 AI Agent 平台"

[project.scripts]
sensenova-claw = "sensenova_claw.app.main:main"
```

Check that `sensenova_claw.app.main:main` uses underscore (Python module path). Fix if needed.

- [ ] **Step 2: Verify and fix root package.json**

Expected final state for scripts:
```json
{
  "name": "sensenova-claw",
  "scripts": {
    "dev": "uv run python3 -m sensenova_claw.app.main run",
    "dev:server": "uv run python3 -m sensenova_claw.app.main run --no-frontend",
    "dev:web": "cd sensenova_claw/app/web && npm run dev",
    "test:web:e2e": "cd sensenova_claw/app/web && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright test"
  }
}
```

Note: `sensenova_claw.app.main` must use underscore (Python module), but directory path `sensenova_claw/app/web` also uses underscore (filesystem matches Python package dir).

- [ ] **Step 3: Verify .gitignore paths**

Expected:
```
sensenova_claw/app/web/.next/
sensenova_claw/app/web/dist/
sensenova_claw/app/web/test-results/
sensenova_claw/app/web/playwright-report/
.sensenova-claw/workdir/
.sensenova-claw/token
.sensenova-claw/agents/*/sessions/
```

Note: The `.gitignore` file is not a `.py` file, so the Phase 2b catch-all would have replaced `sensenova-claw` with `sensenova-claw` (hyphen). But the actual directory on disk is `sensenova_claw/` (underscore, because it's a Python package). Fix any `sensenova-claw/app/web` references to `sensenova_claw/app/web`.

- [ ] **Step 4: Verify frontend and whatsapp bridge package.json**

- `sensenova_claw/app/web/package.json`: `"name": "sensenova-claw-frontend"`
- `sensenova_claw/adapters/plugins/whatsapp/bridge/package.json`: `"name": "sensenova-claw-whatsapp-bridge"`

- [ ] **Step 5: Verify shell scripts have correct filesystem paths**

Check that these scripts use `sensenova_claw/` (underscore) for filesystem paths, not `sensenova-claw/` (hyphen):

```bash
grep -n "sensenova" scripts/postinstall.sh scripts/dev.sh scripts/dev.bat scripts/auto_update.sh
```

Key paths to verify:
- `cd "$ROOT_DIR/sensenova_claw/app/web"` (not `sensenova-claw/app/web`)
- `npm install --prefix sensenova_claw/adapters/plugins/whatsapp/bridge`
- `uvicorn sensenova_claw.app.gateway.main:app` (Python module, underscore)

- [ ] **Step 6: Verify config_example.yml filesystem paths**

```bash
grep -n "sensenova" config_example.yml
```

Check that `sensenova_claw/adapters/plugins/whatsapp/bridge/src/index.mjs` uses underscore (filesystem path).

- [ ] **Step 7: Final sweep for any remaining broken filesystem paths**

```bash
# Comprehensive check across ALL file types
grep -rn "sensenova-claw/" --include="*.json" --include="*.sh" --include="*.bat" --include="*.toml" --include="*.yml" --include="*.yaml" --include="*.md" --include="*.cfg" . | grep -v node_modules | grep -v .venv | grep -v .git
grep -n "sensenova-claw/" .gitignore
```

Review each match: filesystem paths pointing to the Python package directory must be `sensenova_claw/` (underscore). URLs like `github.com/SenseTime-FVG/sensenova-claw/` are correct with hyphen.

- [ ] **Step 8: Commit manual fixes**

```bash
git add -A
git commit -m "refactor: manual fixes for special files after batch replacement"
```

---

### Task 6: Fix Python file hyphen leaks

After Phase 2b, some `.py` files may contain `sensenova-claw` in string contexts where it's correct (e.g., `prog="sensenova-claw"`, `service_name="sensenova-claw"`, display strings). But Phase 2b rule 22 replaced ALL `sensenova-claw` in `.py` files with `sensenova_claw` (underscore), so strings that should have hyphens need manual correction.

**Files:**
- Modify: `sensenova_claw/app/main.py` (line ~294: argparse prog)
- Modify: `sensenova_claw/platform/secrets/store.py` (line ~34: keyring service_name)
- Any other `.py` file where display strings need hyphens

- [ ] **Step 1: Check argparse prog in main.py**

The batch replacement turned `prog="sensenova-claw"` into `prog="sensenova_claw"`. This should be `prog="sensenova-claw"` since it's the CLI command name (user-facing).

```bash
grep -n 'prog=' sensenova_claw/app/main.py
```

Fix to: `prog="sensenova-claw"`

- [ ] **Step 2: Check keyring service_name**

```bash
grep -n 'service_name' sensenova_claw/platform/secrets/store.py
```

The default `service_name="sensenova_claw"` is acceptable (it's an internal key). No change needed unless you prefer `"sensenova-claw"` for consistency with the brand name.

- [ ] **Step 3: Check display strings in Python files**

```bash
grep -rn "sensenova_claw" --include="*.py" . | grep -E '(description|title|label|print|log|"Sensenova)' | grep -v node_modules | grep -v .venv
```

Any user-facing display string that reads `Sensenova_Claw` or `sensenova_claw` but should display as `Sensenova-Claw` or `sensenova-claw` needs manual fix. Key locations:
- `sensenova_claw/app/main.py`: argparse description string
- Any logging/print statements with the brand name

- [ ] **Step 4: Commit Python string fixes**

```bash
git add -A
git commit -m "refactor: fix display strings in Python files to use hyphenated brand name"
```

---

### Task 7: Regenerate lock files and verify build

**Files:**
- Regenerate: `uv.lock`
- Regenerate: `sensenova_claw/app/web/package-lock.json`

- [ ] **Step 1: Reinstall Python package**

```bash
UV_CACHE_DIR=/tmp/uv_cache uv sync
```

Expected: successful install with no errors

- [ ] **Step 2: Verify Python package import**

```bash
python3 -c "import sensenova_claw; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify CLI entry point**

```bash
python3 -m sensenova_claw.app.main --help
```

Expected: help text with `sensenova-claw` program name

- [ ] **Step 4: Reinstall frontend dependencies**

```bash
cd sensenova_claw/app/web && npm install
```

Expected: successful install

- [ ] **Step 5: Commit lock files**

```bash
git add uv.lock sensenova_claw/app/web/package-lock.json
git commit -m "chore: regenerate lock files after rename"
```

---

### Task 8: Run tests and fix failures

**Files:** Various test files that may need fixes

- [ ] **Step 1: Run unit tests**

```bash
python3 -m pytest tests/unit/ -q 2>&1 | tail -30
```

Fix any import errors or assertion failures caused by the rename.

- [ ] **Step 2: Run integration tests**

```bash
python3 -m pytest tests/integration/ -q 2>&1 | tail -30
```

Fix any failures.

- [ ] **Step 3: Final grep verification**

```bash
# Confirm no sensenova-claw remains (excluding lock files and binary)
grep -ri "sensenova-claw" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.yml" --include="*.yaml" --include="*.json" --include="*.sh" --include="*.ps1" --include="*.bat" --include="*.md" --include="*.toml" . | grep -v node_modules | grep -v .venv | grep -v .git | grep -v uv.lock | grep -v package-lock.json | head -20
```

Expected: no results

- [ ] **Step 4: Confirm no Python hyphen leaks**

```bash
grep -rn "sensenova-claw" --include="*.py" . | grep -v node_modules | grep -v .venv | grep -v .git
```

Review: all matches should be inside strings, comments, or URLs only.

- [ ] **Step 5: Commit any test fixes**

```bash
git add -A
git commit -m "fix: resolve test failures after rename"
```

---

### Task 9: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md**

The batch replacement should have already updated most references. Manually review and ensure:
- Project name is `Sensenova-Claw`
- All commands use `sensenova-claw` (CLI) or `sensenova_claw` (Python module)
- All file paths use `sensenova_claw/` (Python package dir)
- Remove `docs_raw/` references since the directory was deleted
- Update the "关键文件路径" section

- [ ] **Step 2: Commit CLAUDE.md update**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for sensenova-claw rename"
```
