"""CLI 入口：seed / run / reconcile / smoke。"""

from __future__ import annotations

from pathlib import Path

import click

from auth_harness.config import load_config
from auth_harness.domain.oracle import OracleMode
from auth_harness.domain.paths import SCENARIOS_DIR
from auth_harness.infrastructure import db as db_mod
from auth_harness.runner.scenario_runner import (
    run_integration,
    run_p0,
    run_scenario,
    run_smoke,
)
from auth_harness.services.dept_scope_list_probe import run_dept_scope_list_probe
from auth_harness.services.dept_scope_probe import run_dept_scope_probe
from auth_harness.services.impact import run_impact_suite
from auth_harness.services.preflight import run_preflight
from auth_harness.services.reconcile import reconcile_many, resolve_user_ids


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path, exists=True),
    default=None,
    help="配置文件路径（默认项目根目录 config.yml）",
)
@click.pass_context
def cli(ctx: click.Context, config_path: Path | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config_path)


@cli.command()
@click.pass_context
def seed(ctx: click.Context) -> None:
    """按顺序执行 sql/ 下 seed 脚本。"""
    config = ctx.obj["config"]
    db_mod.run_seed(config)
    click.echo("[seed] 完成")


@cli.command("cleanup")
@click.pass_context
def cleanup_cmd(ctx: click.Context) -> None:
    """执行 cleanup.sql 清理测试数据。"""
    config = ctx.obj["config"]
    db_mod.run_cleanup(config)
    click.echo("[cleanup] 完成")


@cli.command()
@click.argument("scenario", type=click.Path(path_type=Path, exists=True))
@click.pass_context
def run(ctx: click.Context, scenario: Path) -> None:
    """执行 YAML 场景。"""
    config = ctx.obj["config"]
    raise SystemExit(run_scenario(config, scenario))


@cli.command()
@click.option("--user", "user_id", type=int, default=None, help="单用户 ID")
@click.option("--dept", "dept_code", type=str, default=None, help="部门编码（如 D_FANOUT）")
@click.option("--sample", type=int, default=None, help="大集合随机抽样数量")
@click.option(
    "--oracle",
    "oracle_mode",
    type=click.Choice([OracleMode.API, OracleMode.SQL]),
    default=OracleMode.API,
    help="DB 真值来源：internal API 或 SQL",
)
@click.option("--no-retry", is_flag=True, help="不一致时不重试")
@click.pass_context
def reconcile(
    ctx: click.Context,
    user_id: int | None,
    dept_code: str | None,
    sample: int | None,
    oracle_mode: str,
    no_retry: bool,
) -> None:
    """对比 DB oracle 与 Redis 画像。"""
    config = ctx.obj["config"]
    user_ids = resolve_user_ids(config, user_id=user_id, dept_code=dept_code, sample=sample)
    code = reconcile_many(config, user_ids, oracle_mode=oracle_mode, retry=not no_retry)
    raise SystemExit(code)


@cli.command()
@click.pass_context
def preflight(ctx: click.Context) -> None:
    """检查 MySQL / Redis / 服务连通性与管理账号。"""
    config = ctx.obj["config"]
    raise SystemExit(run_preflight(config))


@cli.command()
@click.pass_context
def smoke(ctx: click.Context) -> None:
    """快速运行三个关键场景。"""
    config = ctx.obj["config"]
    raise SystemExit(run_smoke(config))


@cli.command()
@click.pass_context
def p0(ctx: click.Context) -> None:
    """运行 P0 后端闭环场景套件。"""
    config = ctx.obj["config"]
    raise SystemExit(run_p0(config))


@cli.command()
@click.option("--no-negative", is_flag=True, help="跳过负向场景")
@click.pass_context
def integration(ctx: click.Context, no_negative: bool) -> None:
    """运行全量 L2 集成场景。"""
    config = ctx.obj["config"]
    raise SystemExit(run_integration(config, include_negative=not no_negative))


@cli.command()
@click.option(
    "--fixture",
    "fixture_path",
    type=click.Path(path_type=Path, exists=True),
    default=None,
    help="影响面 fixture YAML（默认 fixtures/impact_cases.yml）",
)
@click.pass_context
def impact(ctx: click.Context, fixture_path: Path | None) -> None:
    """L1 影响面反查（SQL fixture 驱动）。"""
    config = ctx.obj["config"]
    raise SystemExit(run_impact_suite(config, fixture_path))


@cli.command("dept-scope")
@click.option(
    "--fixture",
    "fixture_path",
    type=click.Path(path_type=Path, exists=True),
    default=None,
    help="deptScope fixture（默认 fixtures/dept_scope_cases.yml）",
)
@click.option(
    "--base-url",
    default=None,
    help="网关根地址（默认 config urls.gateway 或 http://127.0.0.1:8080）",
)
@click.option("--user", "username", default=None, help="只测单个用户名")
@click.pass_context
def dept_scope(
    ctx: click.Context,
    fixture_path: Path | None,
    base_url: str | None,
    username: str | None,
) -> None:
    """登录演示账号，断言 /api/example/me 的 AuthProfile.deptScope。"""
    config = ctx.obj["config"]
    raise SystemExit(
        run_dept_scope_probe(
            config,
            fixture_path=fixture_path,
            base_url=base_url,
            username=username,
        )
    )


@cli.command("dept-scope-list")
@click.option(
    "--fixture",
    "fixture_path",
    type=click.Path(path_type=Path, exists=True),
    default=None,
    help="行级过滤 fixture（默认 fixtures/dept_scope_list_cases.yml）",
)
@click.option(
    "--base-url",
    default=None,
    help="网关根地址（默认 config urls.gateway 或 http://127.0.0.1:8080）",
)
@click.option("--user", "username", default=None, help="只测单个用户名")
@click.pass_context
def dept_scope_list(
    ctx: click.Context,
    fixture_path: Path | None,
    base_url: str | None,
    username: str | None,
) -> None:
    """登录演示账号，断言 /api/example/orders 行级过滤 id 集合。"""
    config = ctx.obj["config"]
    raise SystemExit(
        run_dept_scope_list_probe(
            config,
            fixture_path=fixture_path,
            base_url=base_url,
            username=username,
        )
    )


@cli.command("list-scenarios")
def list_scenarios() -> None:
    """列出内置场景文件。"""
    for path in sorted(SCENARIOS_DIR.glob("*.yml")):
        click.echo(path.name)


def main() -> None:
    """程序入口。"""
    cli()
