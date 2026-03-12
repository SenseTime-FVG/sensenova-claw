"""Skill 市场管理数据模型"""
from __future__ import annotations

from pydantic import BaseModel


class SkillSearchItem(BaseModel):
    id: str
    name: str
    description: str
    author: str | None = None
    version: str | None = None
    downloads: int | None = None
    source: str


class SearchResult(BaseModel):
    source: str
    total: int
    page: int
    page_size: int
    items: list[SkillSearchItem]


class SkillDetail(BaseModel):
    id: str
    name: str
    description: str
    version: str | None = None
    author: str | None = None
    skill_md_preview: str
    files: list[str]
    installed: bool


class UpdateInfo(BaseModel):
    skill_id: str
    current_version: str
    latest_version: str
    changelog: str | None = None


class ErrorResponse(BaseModel):
    ok: bool = False
    error: str
    code: str


class InstallRequest(BaseModel):
    source: str
    id: str | None = None
    repo_url: str | None = None


class SkillInvokeRequest(BaseModel):
    skill_name: str
    arguments: str = ""
