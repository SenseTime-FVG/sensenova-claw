"""agentos.app.main 的安装路径解析回归测试"""

from pathlib import Path

from agentos.app import main as app_main


def test_resolve_web_dir_prefers_installed_agentos_home(monkeypatch, tmp_path):
    installed_web = tmp_path / "app" / "agentos" / "app" / "web"
    (installed_web / "node_modules").mkdir(parents=True)
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path))

    assert app_main._resolve_web_dir() == installed_web


def test_resolve_web_dir_falls_back_to_repo_web_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path))

    assert app_main._resolve_web_dir() == Path(app_main.__file__).resolve().parent / "web"
