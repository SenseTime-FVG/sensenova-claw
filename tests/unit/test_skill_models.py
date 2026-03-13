"""Skill 市场数据模型单测"""
import pytest
from agentos.capabilities.skills.models import (
    SkillSearchItem, SearchResult, SkillDetail,
    UpdateInfo, ErrorResponse, InstallRequest, SkillInvokeRequest,
)


def test_search_result_serialization():
    item = SkillSearchItem(
        id="pdf-tool", name="pdf-tool", description="PDF工具",
        author="test", version="1.0.0", downloads=100, source="clawhub",
    )
    result = SearchResult(source="clawhub", total=1, page=1, page_size=20, items=[item])
    d = result.model_dump()
    assert d["total"] == 1
    assert d["items"][0]["id"] == "pdf-tool"


def test_skill_detail_defaults():
    detail = SkillDetail(
        id="x", name="x", description="d",
        skill_md_preview="---\nname: x\n---\nbody", files=["SKILL.md"],
        installed=False,
    )
    assert detail.version is None
    assert detail.author is None


def test_error_response():
    err = ErrorResponse(error="conflict", code="NAME_CONFLICT")
    assert err.ok is False


def test_install_request_clawhub():
    req = InstallRequest(source="clawhub", id="my-skill")
    assert req.repo_url is None


def test_install_request_git():
    req = InstallRequest(source="git", repo_url="https://github.com/u/r")
    assert req.id is None


def test_skill_invoke_request():
    req = SkillInvokeRequest(skill_name="pdf-tool", arguments="file.pdf")
    assert req.skill_name == "pdf-tool"
