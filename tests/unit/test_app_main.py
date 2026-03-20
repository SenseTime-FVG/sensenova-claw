"""agentos.app.main 的前端路径解析回归测试"""

from pathlib import Path

from agentos.app import main as app_main


def test_resolve_web_dir_prefers_project_root(tmp_path):
    """project_root 下有 node_modules 时优先使用"""
    web_dir = tmp_path / "agentos" / "app" / "web"
    (web_dir / "node_modules").mkdir(parents=True)

    assert app_main._resolve_web_dir(tmp_path) == web_dir


def test_resolve_web_dir_falls_back_to_installed(monkeypatch, tmp_path):
    """project_root 下无 node_modules，回退到 AGENTOS_HOME/app"""
    installed_web = tmp_path / "installed" / "app" / "agentos" / "app" / "web"
    (installed_web / "node_modules").mkdir(parents=True)
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "installed"))

    # project_root 下没有 node_modules
    project_root = tmp_path / "dev"
    project_root.mkdir()

    assert app_main._resolve_web_dir(project_root) == installed_web


def test_resolve_web_dir_defaults_to_project_root(monkeypatch, tmp_path):
    """都没有 node_modules 时返回 project_root 下的 web 目录"""
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "empty"))

    project_root = tmp_path / "dev"
    project_root.mkdir()

    assert app_main._resolve_web_dir(project_root) == project_root / "agentos" / "app" / "web"
