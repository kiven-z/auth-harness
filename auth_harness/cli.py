"""CLI 入口：seed / run / reconcile / smoke。"""

from __future__ import annotations

from pathlib import Path

import click

from auth_harness.config import HARNESS_ROOT, load_config
from auth_harness import db as db_mod
from auth_harness.oracle import OracleMode
from auth_harness.reconcile import reconcile_many, resolve_user_ids
from auth_harness.scenarios import SCENARIOS_DIR, run_scenario, run_smoke


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path, exists=True),
    default=None,
    help="配置文件路径（默认 tools/auth-harness/config.yml）",
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
def smoke(ctx: click.Context) -> None:
    """快速运行三个关键场景。"""
    config = ctx.obj["config"]
    raise SystemExit(run_smoke(config))


@cli.command("list-scenarios")
def list_scenarios() -> None:
    """列出内置场景文件。"""
    for path in sorted(SCENARIOS_DIR.glob("*.yml")):
        click.echo(path.name)


def main() -> None:
    """程序入口。"""
    cli()
