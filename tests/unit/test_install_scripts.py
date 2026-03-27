"""安装脚本关键行为回归测试"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_install_sh_uses_editable_tool_install():
    content = (ROOT / "install" / "install.sh").read_text(encoding="utf-8")

    assert "uv tool install --editable --from . --force sensenova-claw" in content
    assert 'REPO_REF="${SENSENOVA_CLAW_REPO_REF:-${SENSENOVA_CLAW_REPO_BRANCH:-dev}}"' in content


def test_install_ps1_uses_editable_tool_install():
    content = (ROOT / "install" / "install.ps1").read_text(encoding="utf-8")

    assert "uv tool install --editable --from . --force sensenova-claw" in content
    assert '$REPO_REF = if ($env:SENSENOVA_CLAW_REPO_REF)' in content


def test_root_postinstall_uses_node_script_instead_of_bash():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["postinstall"] == "node ./scripts/postinstall.mjs"


def test_root_python_scripts_use_python_not_python3():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    scripts = package["scripts"]

    assert scripts["dev"] == "uv run python -m sensenova_claw.app.main run"
    assert scripts["dev:server"] == "uv run python -m sensenova_claw.app.main run --no-frontend"
    assert scripts["test"] == "uv run python -m pytest tests/ -q"
    assert scripts["test:unit"] == "uv run python -m pytest tests/unit/ -q"
    assert (
        scripts["test:core"]
        == "uv run python -m pytest tests/unit/test_agent_worker.py tests/unit/test_llm_worker.py tests/unit/test_openai_provider_message_normalization.py tests/e2e/test_agent_llm_core_flow.py -q"
    )
    assert scripts["test:e2e"] == "uv run python -m pytest tests/e2e/ -q"


def test_postinstall_shell_wrapper_delegates_to_node_script():
    content = (ROOT / "scripts" / "postinstall.sh").read_text(encoding="utf-8")

    assert 'node "$ROOT_DIR/scripts/postinstall.mjs" "$@"' in content


def test_app_postinstall_uses_node_script_instead_of_bash():
    package = json.loads((ROOT / "sensenova_claw" / "app" / "package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["postinstall"] == "node ./scripts/postinstall.mjs"
