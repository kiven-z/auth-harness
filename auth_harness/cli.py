"""CLI 入口：seed / run / reconcile / smoke / perms。"""

from __future__ import annotations

from pathlib import Path

import click

from auth_harness.config import HarnessConfig, load_config
from auth_harness.domain.oracle import OracleMode
from auth_harness.domain.paths import (
    DEFAULT_AUTH_SERVER_ROOT,
    DEFAULT_PERMISSION_SEED_PATH,
    PERMISSIONS_CATALOG_PATH,
    SCENARIOS_DIR,
)
from auth_harness.infrastructure import db as db_mod
from auth_harness.infrastructure import redis_client as redis_mod
from auth_harness.perms import service as perms_service
from auth_harness.runner.scenario_runner import (
    run_integration,
    run_p0,
    run_scenario,
    run_smoke,
)
from auth_harness.services.dept_scope_list_probe import run_dept_scope_list_probe
from auth_harness.services.dept_scope_probe import run_dept_scope_probe
from auth_harness.services.example_order_export_probe import run_example_order_export_probe
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
    try:
        ctx.obj["config"] = load_config(config_path)
    except FileNotFoundError:
        # perms scan/check/gen 可无 config；其它命令自行 require_config
        ctx.obj["config"] = None


def require_config(ctx: click.Context) -> HarnessConfig:
    """需要 MySQL/API 的命令必须有 config.yml。"""
    config = ctx.obj.get("config")
    if config is None:
        raise click.ClickException(
            "缺少 config.yml，请先复制 config.example.yml 并填写连接信息。"
        )
    return config


@cli.command()
@click.pass_context
def seed(ctx: click.Context) -> None:
    """按顺序执行 sql/ 下 seed 脚本，并清掉 9001* Redis 画像。"""
    config = require_config(ctx)
    db_mod.run_seed(config)
    redis_mod.flush_harness_profiles(config)
    click.echo("[seed] 完成")


@cli.command("cleanup")
@click.pass_context
def cleanup_cmd(ctx: click.Context) -> None:
    """执行 cleanup.sql 清理测试数据，并清掉 9001* Redis 画像。"""
    config = require_config(ctx)
    db_mod.run_cleanup(config)
    redis_mod.flush_harness_profiles(config)
    click.echo("[cleanup] 完成")


@cli.command()
@click.argument("scenario", type=click.Path(path_type=Path, exists=True))
@click.pass_context
def run(ctx: click.Context, scenario: Path) -> None:
    """执行 YAML 场景。"""
    config = require_config(ctx)
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
    config = require_config(ctx)
    user_ids = resolve_user_ids(config, user_id=user_id, dept_code=dept_code, sample=sample)
    code = reconcile_many(config, user_ids, oracle_mode=oracle_mode, retry=not no_retry)
    raise SystemExit(code)


@cli.command()
@click.pass_context
def preflight(ctx: click.Context) -> None:
    """检查 MySQL / Redis / 服务连通性与管理账号。"""
    config = require_config(ctx)
    raise SystemExit(run_preflight(config))


@cli.command()
@click.pass_context
def smoke(ctx: click.Context) -> None:
    """快速运行三个关键场景。"""
    config = require_config(ctx)
    raise SystemExit(run_smoke(config))


@cli.command()
@click.pass_context
def p0(ctx: click.Context) -> None:
    """运行 P0 后端闭环场景套件。"""
    config = require_config(ctx)
    raise SystemExit(run_p0(config))


@cli.command()
@click.option("--no-negative", is_flag=True, help="跳过负向场景")
@click.pass_context
def integration(ctx: click.Context, no_negative: bool) -> None:
    """运行全量 L2 集成场景。"""
    config = require_config(ctx)
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
    config = require_config(ctx)
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
    config = require_config(ctx)
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
    config = require_config(ctx)
    raise SystemExit(
        run_dept_scope_list_probe(
            config,
            fixture_path=fixture_path,
            base_url=base_url,
            username=username,
        )
    )


@cli.command("data-scope")
@click.option(
    "--base-url",
    default=None,
    help="网关根地址（默认 config urls.gateway 或 http://127.0.0.1:8080）",
)
@click.option("--user", "username", default=None, help="只测单个用户名")
@click.pass_context
def data_scope(ctx: click.Context, base_url: str | None, username: str | None) -> None:
    """数据权限冒烟：先断言 deptScope 画像，再断言 example_order 行级过滤。"""
    config = require_config(ctx)
    code = run_dept_scope_probe(config, base_url=base_url, username=username)
    if code != 0:
        raise SystemExit(code)
    raise SystemExit(run_dept_scope_list_probe(config, base_url=base_url, username=username))


@cli.command("example-order-export")
@click.option(
    "--fixture",
    "fixture_path",
    type=click.Path(path_type=Path, exists=True),
    default=None,
    help="导出冒烟 fixture（默认 fixtures/example_order_export_cases.yml）",
)
@click.option(
    "--base-url",
    default=None,
    help="网关根地址（默认 config urls.gateway 或 http://127.0.0.1:8080）",
)
@click.option("--user", "username", default=None, help="只测单个用户名")
@click.pass_context
def example_order_export(
    ctx: click.Context,
    fixture_path: Path | None,
    base_url: str | None,
    username: str | None,
) -> None:
    """提交 example_order 异步导出，轮询至 SUCCESS 并校验产物链接。"""
    config = require_config(ctx)
    raise SystemExit(
        run_example_order_export_probe(
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


def _perms_path_options(fn):
    """共享 --server-root / --seed / --catalog。"""
    fn = click.option(
        "--catalog",
        "catalog_path",
        type=click.Path(path_type=Path, exists=True),
        default=PERMISSIONS_CATALOG_PATH,
        show_default=True,
        help="权限中文名映射 YAML",
    )(fn)
    fn = click.option(
        "--seed",
        "seed_path",
        type=click.Path(path_type=Path),
        default=DEFAULT_PERMISSION_SEED_PATH,
        show_default=True,
        help="02-seed-sys-permission.sql 路径",
    )(fn)
    fn = click.option(
        "--server-root",
        "server_root",
        type=click.Path(path_type=Path, exists=True, file_okay=False),
        default=DEFAULT_AUTH_SERVER_ROOT,
        show_default=True,
        help="auth-server 根目录",
    )(fn)
    return fn


@cli.group("perms")
def perms_group() -> None:
    """从 @auth.decide 扫描权限码，对照 seed / DB。"""


@perms_group.command("scan")
@_perms_path_options
def perms_scan(
    server_root: Path,
    seed_path: Path,
    catalog_path: Path,
) -> None:
    """打印代码中的权限码清单。"""
    del seed_path  # 扫描不需要 seed
    codes, hits, _catalog = perms_service.scan_permission_codes(
        server_root=server_root,
        catalog_path=catalog_path,
    )
    click.echo(f"unique={len(codes)} refs={len(hits)}")
    for code in codes:
        click.echo(code)


@perms_group.command("check")
@_perms_path_options
@click.option("--db", "against_db", is_flag=True, help="对照开发库 sys_permission，而非 seed SQL")
@click.option("--strict", "fail_on_orphan", is_flag=True, help="seed/DB 中有代码未使用的码也失败")
@click.pass_context
def perms_check(
    ctx: click.Context,
    server_root: Path,
    seed_path: Path,
    catalog_path: Path,
    against_db: bool,
    fail_on_orphan: bool,
) -> None:
    """校验代码权限码是否都在 seed（或 DB）中。"""
    config = require_config(ctx) if against_db else ctx.obj.get("config")
    try:
        diff = perms_service.check_permissions(
            server_root=server_root,
            catalog_path=catalog_path,
            seed_path=seed_path,
            config=config,
            against_db=against_db,
            fail_on_orphan=fail_on_orphan,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(perms_service.format_diff_report(diff, fail_on_orphan=fail_on_orphan))
    raise SystemExit(perms_service.exit_code_for_diff(diff, fail_on_orphan=fail_on_orphan))


@perms_group.command("gen")
@_perms_path_options
@click.option("--db", "against_db", is_flag=True, help="按开发库差异生成，而非 seed")
@click.option(
    "--prune",
    is_flag=True,
    help="同时生成删除 orphan 的 SQL（开发库对齐用；会 CASCADE 角色绑定）",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="写出 SQL 文件（默认打印到 stdout）",
)
@click.pass_context
def perms_gen(
    ctx: click.Context,
    server_root: Path,
    seed_path: Path,
    catalog_path: Path,
    against_db: bool,
    prune: bool,
    output_path: Path | None,
) -> None:
    """为缺失权限码生成 upsert SQL；可选 --prune 删除 orphan。"""
    config = require_config(ctx) if against_db else ctx.obj.get("config")
    try:
        plan = perms_service.build_sync_plan(
            server_root=server_root,
            catalog_path=catalog_path,
            seed_path=seed_path,
            config=config,
            against_db=against_db,
            prune=prune,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(perms_service.format_diff_report(plan.diff), err=True)
    if plan.diff.unresolved_names:
        unresolved_missing = [c for c in plan.diff.missing if c in plan.diff.unresolved_names]
        if unresolved_missing:
            raise click.ClickException(
                "无法解析中文名，请补 fixtures/permissions_catalog.yml: "
                + ", ".join(unresolved_missing)
            )
    if output_path is None:
        click.echo(plan.sql, nl=False)
    else:
        output_path.write_text(plan.sql, encoding="utf-8")
        click.echo(f"[perms gen] wrote -> {output_path}", err=True)
    click.echo(
        f"[perms gen] insert={len(plan.inserts)} prune={len(plan.prune_codes)}",
        err=True,
    )


@perms_group.command("apply")
@_perms_path_options
@click.option(
    "--prune",
    is_flag=True,
    help="同时删除 orphan（开发库对齐；会 CASCADE 清理 sys_role_permission）",
)
@click.pass_context
def perms_apply(
    ctx: click.Context,
    server_root: Path,
    seed_path: Path,
    catalog_path: Path,
    prune: bool,
) -> None:
    """把代码权限对齐到开发库：补缺；加 --prune 则删 orphan。"""
    del seed_path
    config = require_config(ctx)
    try:
        inserted, pruned, entries, prune_codes, diff = perms_service.apply_missing(
            config,
            server_root=server_root,
            catalog_path=catalog_path,
            prune=prune,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(perms_service.format_diff_report(diff))
    click.echo(f"[perms apply] inserted={inserted} pruned={pruned}")
    for code, name, order_num in entries:
        click.echo(f"  + {code} ({name}) order={order_num}")
    for code in prune_codes:
        click.echo(f"  - {code}")
    if diff.orphan and not prune:
        click.echo(f"[perms apply] orphan left untouched: {len(diff.orphan)}（加 --prune 可删）")


def main() -> None:
    """程序入口。"""
    cli()
