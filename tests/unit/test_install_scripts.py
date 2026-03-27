"""安装脚本关键行为回归测试"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_install_sh_uses_editable_tool_install():
    content = (ROOT / "install" / "install.sh").read_text(encoding="utf-8")

    assert "uv tool install --editable --from . --force sensenova-claw" in content
    assert (
        'REPO_REF="${SENSENOVA_CLAW_APP_BRANCH:-${SENSENOVA_CLAW_REPO_REF:-${SENSENOVA_CLAW_REPO_BRANCH:-dev}}}"'
        in content
    )
    assert 'info "app 目录将使用仓库分支/引用: $REPO_REF"' in content


def test_install_ps1_uses_editable_tool_install():
    content = (ROOT / "install" / "install.ps1").read_text(encoding="utf-8")

    assert "uv tool install --editable --from . --force sensenova-claw" in content
    assert '$REPO_REF = if ($env:SENSENOVA_CLAW_REPO_REF)' in content
