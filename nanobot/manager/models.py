"""Data models for the agent manager."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class AgentStatus(str, Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class QRCodeStatus(str, Enum):
    PENDING = "pending"
    SCANNED = "scanned"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    SCAN_REDIRECT = "scaned_but_redirect"


# -- Database models --


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    username: str
    password_hash: str
    created_at: datetime | None = None


class Agent(BaseModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)

    id: int | None = None
    user_id: int
    name: str
    soul: str = ""
    status: AgentStatus = AgentStatus.CREATING
    config_path: str = ""
    workspace_path: str = ""
    gateway_port: int = 0
    pid: int | None = None
    wechat_bound: bool = False
    qr_code_id: str = ""
    qr_code_url: str = ""
    qr_code_status: str = ""
    wechat_bot_id: str = ""
    wechat_bot_token: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WechatBinding(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    agent_id: int
    wechat_user_id: str
    bound_at: datetime | None = None


# -- API request/response models --


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str


class CreateAgentRequest(BaseModel):
    name: str
    soul: str = ""


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    soul: str | None = None


class AgentStatusResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    status: AgentStatus
    pid: int | None = None
    alive: bool = False
    gateway_port: int = 0
    wechat_bound: bool = False
    qr_code_status: str = ""


class AdminStatsResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    total_users: int = 0
    total_agents: int = 0
    running_agents: int = 0
    stopped_agents: int = 0
    error_agents: int = 0
