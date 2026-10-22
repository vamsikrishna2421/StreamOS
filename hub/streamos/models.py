"""Pydantic request/response models for the hub API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SourceIn(BaseModel):
    name: str
    kind: str = Field(pattern="^(live|vod)$")
    upstream_url: str
    max_sessions: int = 1
    shareable: bool = True
    logo: str | None = None
    group_name: str | None = None
    enabled: bool = True


class SourceOut(SourceIn):
    id: str
    created_at: float


class DevicePairStart(BaseModel):
    name: str
    platform: str = "web"


class DevicePairComplete(BaseModel):
    code: str
    name: str
    platform: str = "web"


class DeviceOut(BaseModel):
    id: str
    name: str
    platform: str | None
    paired_at: float
    last_seen: float | None


class HistoryIn(BaseModel):
    source_id: str
    position_s: float = 0.0
    duration_s: float | None = None
    profile_id: str = "default"


class AllocResult(BaseModel):
    ok: bool
    mode: str          # "shared" | "independent" | "rejected"
    source_id: str
    reason: str | None = None
    play_url: str | None = None
    upstream_sessions: int = 0
