"""步骤类型注册表。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from auth_harness.steps.context import StepContext

StepHandler = Callable[[StepContext, dict[str, Any]], None]


class StepRegistry:
    """按名称分发 YAML step。"""

    def __init__(self) -> None:
        self._handlers: dict[str, StepHandler] = {}

    def register(self, name: str) -> Callable[[StepHandler], StepHandler]:
        """装饰器：注册步骤处理函数。"""

        def decorator(handler: StepHandler) -> StepHandler:
            if name in self._handlers:
                raise ValueError(f"步骤类型已注册: {name}")
            self._handlers[name] = handler
            return handler

        return decorator

    def execute(self, ctx: StepContext, step: dict[str, Any]) -> None:
        """执行单个 YAML step。"""
        if not isinstance(step, dict) or len(step) != 1:
            raise ValueError(f"无效 step: {step}")

        action, params = next(iter(step.items()))
        handler = self._handlers.get(action)
        if handler is None:
            raise ValueError(f"未知 step 类型: {action}")
        handler(ctx, params or {})


DEFAULT_REGISTRY = StepRegistry()
