#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 SenseTime-FVG. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# 一键构建 + 推送 sensenova-claw 的 microsandbox 镜像。
# 自动按需安装/配置 buildx、binfmt、buildx builder。
#
# 用法（在仓库根或本目录都能跑）:
#   ./sandboxes/microsandbox/build.sh                      # 单架构，本机原生 arch
#   ./sandboxes/microsandbox/build.sh --multi-arch         # arm64+amd64 manifest list
#   ./sandboxes/microsandbox/build.sh --no-push            # 只构建到本地 daemon，不推
#   IMAGE=ghcr.io/foo/bar:tag ./sandboxes/microsandbox/build.sh
#
# 注意: 多架构 + push 需要 buildx + docker-container driver + binfmt；脚本会自检并补齐。

set -euo pipefail

IMAGE="${IMAGE:-ghcr.io/tsunamiblue/sensenova-claw:msb}"
DEFAULT_ARCH="linux/$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"
PLATFORMS="$DEFAULT_ARCH"
PUSH=1

# ── 参数解析 ────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --multi-arch)
            PLATFORMS="linux/arm64,linux/amd64"
            ;;
        --platforms)
            PLATFORMS="$2"
            shift
            ;;
        --no-push)
            PUSH=0
            ;;
        --image)
            IMAGE="$2"
            shift
            ;;
        -h|--help)
            sed -n '4,17p' "$0"
            exit 0
            ;;
        *)
            echo "unknown arg: $1" >&2
            exit 2
            ;;
    esac
    shift
done

say() { printf "\033[1;36m[build]\033[0m %s\n" "$*"; }
die() { printf "\033[1;31m[build]\033[0m %s\n" "$*" >&2; exit 1; }

# 切到仓库根（Dockerfile 中的 COPY 都是相对于仓库根的）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# ── 1. docker daemon 可达 ───────────────────────────────────
if ! docker info >/dev/null 2>&1; then
    if command -v colima >/dev/null && ! colima status >/dev/null 2>&1; then
        say "Colima 未启动，尝试 colima start..."
        colima start || die "colima start 失败，请手动排查"
    else
        die "docker daemon 不可达。先启动 Docker Desktop / Colima。"
    fi
fi

# ── 2. buildx 可用 ──────────────────────────────────────────
if ! docker buildx version >/dev/null 2>&1; then
    say "未检测到 buildx，尝试通过 Homebrew 安装..."
    command -v brew >/dev/null || die "需要 Homebrew 安装 docker-buildx；或手动安装 buildx 后重试。"
    brew install docker-buildx >/dev/null
    mkdir -p ~/.docker/cli-plugins
    ln -sfn "$(brew --prefix)/opt/docker-buildx/bin/docker-buildx" ~/.docker/cli-plugins/docker-buildx
    docker buildx version >/dev/null || die "buildx 安装后仍不可用，请检查 ~/.docker/cli-plugins"
    say "buildx 安装完成: $(docker buildx version | head -1)"
fi

# ── 3. 多架构构建准备（仅当跨架构时） ─────────────────────────
need_multiarch=0
case "$PLATFORMS" in
    *,*) need_multiarch=1 ;;
    "$DEFAULT_ARCH") ;;
    *)   need_multiarch=1 ;;
esac

if [ "$need_multiarch" -eq 1 ]; then
    # binfmt：让 colima/Linux VM 能跑外架构二进制
    say "注册 binfmt QEMU handlers（如已注册则幂等）..."
    docker run --privileged --rm tonistiigi/binfmt --install all >/dev/null

    # buildx builder：默认 driver 不支持多 arch + push，需要 docker-container
    if ! docker buildx inspect multiarch >/dev/null 2>&1; then
        say "创建 buildx builder 'multiarch' (docker-container driver)..."
        docker buildx create --name multiarch --driver docker-container --use >/dev/null
        docker buildx inspect --bootstrap >/dev/null
    else
        docker buildx use multiarch
    fi
fi

# ── 4. 构建 + 推送 ───────────────────────────────────────────
say "image     = $IMAGE"
say "platforms = $PLATFORMS"
say "push      = $([ $PUSH -eq 1 ] && echo yes || echo no)"

build_args=(
    --progress=plain
    -f sandboxes/microsandbox/Dockerfile
    --platform "$PLATFORMS"
    -t "$IMAGE"
)

if [ $PUSH -eq 1 ]; then
    build_args+=(--push)
elif [ "$need_multiarch" -eq 1 ]; then
    die "多架构构建必须 --push（OCI manifest list 无法落到本地 daemon）。"
else
    build_args+=(--load)
fi

say "执行: docker buildx build ${build_args[*]} ."
docker buildx build "${build_args[@]}" .

# ── 5. 校验（仅 push 时） ────────────────────────────────────
if [ $PUSH -eq 1 ]; then
    say "推送完成，远端 manifest:"
    docker buildx imagetools inspect "$IMAGE" | head -20
fi

say "Done. 在 microsandbox 中拉取: msb pull $IMAGE"
