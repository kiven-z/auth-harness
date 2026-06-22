"""YAML 场景执行器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from auth_harness.assertions.runner import AssertRunner
from auth_harness.config import HarnessConfig
from auth_harness.domain.paths import SCENARIOS_DIR, SMOKE_SCENARIOS
from auth_harness.infrastructure.api import ApiClient
from auth_harness.infrastructure import db as db_mod
from auth_harness.infrastructure import redis_client as redis_mod
from auth_harness.steps import DEFAULT_REGISTRY
from auth_harness.steps import handlers as _handlers  # noqa: F401 — 注册内置步骤
from auth_harness.steps.context import StepContext
from auth_harness.wait.outbox import snapshot_outbox_cursor


class ScenarioRunner:
    """加载并执行 YAML 场景。"""

    def __init__(self, registry=DEFAULT_REGISTRY) -> None:
        self._registry = registry

    def run(self, config: HarnessConfig, scenario_path: Path) -> int:
        """执行场景，失败返回 1。"""
        try:
            return self._run_inner(config, scenario_path)
        except (AssertionError, TimeoutError, RuntimeError, ValueError) as exc:
            print(f"[scenario] FAILED: {exc}")
            return 1

    def _run_inner(self, config: HarnessConfig, scenario_path: Path) -> int:
        data = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
        name = data.get("name", scenario_path.stem)
        print(f"\n[scenario] === {name} ===")

        api = ApiClient(config)
        api.login()
        conn = db_mod.connect(config)
        rds = redis_mod.connect(config)
        ctx = StepContext(config=config, conn=conn, rds=rds, api=api)
        ctx.step_entry_cursor = snapshot_outbox_cursor(conn, None)

        try:
            for block_name in ("setup", "steps"):
                for step in data.get(block_name) or []:
                    self._run_step(ctx, step)

            assert_block = data.get("assert")
            if assert_block:
                AssertRunner(ctx).run(assert_block)
            return 0
        finally:
            conn.close()
            rds.close()

    def _run_step(self, ctx: StepContext, step: dict[str, Any]) -> None:
        """执行单步；将上一步入口游标交给 wait_outbox 使用。"""
        ctx.previous_step_cursor = ctx.step_entry_cursor
        ctx.step_entry_cursor = snapshot_outbox_cursor(ctx.conn, None)
        self._registry.execute(ctx, step)


def run_scenario(config: HarnessConfig, scenario_path: Path) -> int:
    """执行单个 YAML 场景。"""
    return ScenarioRunner().run(config, scenario_path)


def run_smoke(config: HarnessConfig) -> int:
    """依次运行三个关键场景。"""
    for name in SMOKE_SCENARIOS:
        code = run_scenario(config, SCENARIOS_DIR / name)
        if code != 0:
            return code
    print("\n[smoke] 全部场景通过")
    return 0
