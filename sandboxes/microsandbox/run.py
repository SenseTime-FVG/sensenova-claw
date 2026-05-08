"""
microsandbox 启动 Sensenova-Claw 的最小可运行示例。

前置:
  pip install microsandbox
  msb 已安装并能跑通（参考 https://docs.microsandbox.dev）。
  镜像 ghcr.io/tsunamiblue/sensenova-claw:msb 已发布且为公共可见。

运行:
  python sandboxes/microsandbox/run.py
  # 启动后访问 http://localhost:3000 查看前端，http://localhost:8000 是后端 API

环境变量（可选，未设置时只把占位符注入 VM，agent 实际不会拿到任何真 key）:
  OPENAI_API_KEY / ANTHROPIC_API_KEY
"""

import asyncio
import os

from microsandbox import LogLevel, Sandbox, Secret

IMAGE = "ghcr.io/tsunamiblue/sensenova-claw:msb"

# 把 Sensenova-Claw 业务确实会回调的域名加进 allow_hosts；
# microsandbox 的 net-secrets 只在请求这些 host 时把占位符替换为真 key。
LLM_ALLOW_HOSTS = [
    "api.openai.com",
    "api.anthropic.com",
    "*.googleapis.com",
    "google.serper.dev",
]


def _build_secrets() -> list:
    secrets = []
    if val := os.environ.get("OPENAI_API_KEY"):
        secrets.append(Secret.env("OPENAI_API_KEY", value=val, allow_hosts=LLM_ALLOW_HOSTS))
    if val := os.environ.get("ANTHROPIC_API_KEY"):
        secrets.append(
            Secret.env("ANTHROPIC_API_KEY", value=val, allow_hosts=LLM_ALLOW_HOSTS)
        )
    if val := os.environ.get("SERPER_API_KEY"):
        secrets.append(
            Secret.env("SERPER_API_KEY", value=val, allow_hosts=["google.serper.dev"])
        )
    return secrets


async def main() -> None:
    print(f"[run.py] booting microVM from {IMAGE}")
    sb = await Sandbox.create(
        "sensenova-claw",
        image=IMAGE,
        cpus=2,
        memory=2048,
        ports={8000: 8000, 3000: 3000},  # host:guest，dict 形式
        # 持久化：把 token、会话、SQLite 数据放到 host 端的 claw-data 卷里。
        # 卷不存在时 SDK 会自动创建（等价于 `msb volume create claw-data`）。
        # value 是 dict，可选 named / bind / tmpfs / disk —— 此处用命名卷。
        volumes={"/root/.sensenova-claw": {"named": "claw-data"}},
        secrets=_build_secrets(),
        replace=True,
        log_level=LogLevel.INFO,
    )

    # 后台拉起 frontend + backend，主进程不阻塞。
    print("[run.py] starting sensenova-claw inside the VM...")
    await sb.shell("sensenova-claw-start > /tmp/claw.log 2>&1 &")

    # 等待后端 8000 端口就绪（最多 60s）—— /health 由 sensenova_claw/app/gateway/main.py 暴露
    print("[run.py] waiting for backend to be ready on :8000/health")
    for _ in range(60):
        out = await sb.shell(
            "wget -q -O /dev/null http://127.0.0.1:8000/health "
            "&& echo READY || echo WAIT"
        )
        if "READY" in out.stdout_text:
            break
        await asyncio.sleep(1)
    else:
        print("[run.py] backend did not come up; tail of log:")
        out = await sb.shell("tail -40 /tmp/claw.log")
        print(out.stdout_text)
        return

    print("[run.py] sensenova-claw is up:")
    print("         frontend:  http://localhost:3000")
    print("         backend:   http://localhost:8000")
    print("         (Ctrl+C 退出，VM 也会随脚本退出而停止)")

    try:
        # 保持脚本存活；microsandbox 的 SDK 上下文一退出 VM 就回收。
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[run.py] stopping VM...")
    finally:
        await sb.stop_and_wait()
        print("[run.py] VM stopped.")


if __name__ == "__main__":
    asyncio.run(main())
