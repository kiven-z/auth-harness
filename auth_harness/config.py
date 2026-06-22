"""加载 config.yml 配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

HARNESS_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = HARNESS_ROOT / "config.yml"
EXAMPLE_CONFIG_PATH = HARNESS_ROOT / "config.example.yml"


@dataclass
class HarnessConfig:
    """auth-harness 运行时配置。"""

    raw: dict[str, Any]
    config_path: Path

    @property
    def system_base_url(self) -> str:
        return self.raw["urls"]["system"].rstrip("/")

    @property
    def auth_base_url(self) -> str:
        return self.raw["urls"]["auth"].rstrip("/")

    @property
    def mysql(self) -> dict[str, Any]:
        return self.raw["mysql"]

    @property
    def redis(self) -> dict[str, Any]:
        return self.raw["redis"]

    @property
    def admin(self) -> dict[str, str]:
        return self.raw["admin"]

    @property
    def internal_jwt(self) -> dict[str, str]:
        return self.raw["internal_jwt"]

    @property
    def test_ids(self) -> dict[str, int]:
        return {k: int(v) for k, v in self.raw.get("test_ids", {}).items()}

    @property
    def wait(self) -> dict[str, float]:
        defaults = {
            "outbox_poll_interval_sec": 0.5,
            "outbox_timeout_sec": 60,
            "reconcile_retry_sec": 2,
            "reconcile_max_attempts": 15,
        }
        merged = {**defaults, **self.raw.get("wait", {})}
        return {k: float(v) for k, v in merged.items()}


def load_config(path: Path | None = None) -> HarnessConfig:
    """从 YAML 文件加载配置。"""
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {config_path}\n"
            f"请复制 {EXAMPLE_CONFIG_PATH} 为 config.yml 并填写连接信息。"
        )
    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"无效的配置文件: {config_path}")
    return HarnessConfig(raw=raw, config_path=config_path)
