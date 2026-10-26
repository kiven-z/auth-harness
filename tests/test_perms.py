"""权限码扫描 / 目录解析单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from auth_harness.perms import service as perms_service
from auth_harness.perms.catalog import PermissionsCatalog, load_catalog
from auth_harness.perms.scan import scan_java_permissions, unique_codes
from auth_harness.perms.seed_sql import build_prune_sql, build_sync_sql, build_upsert_sql, parse_seed_sql
from auth_harness.perms.service import check_permissions, format_diff_report
from auth_harness.domain.paths import (
    DEFAULT_AUTH_SERVER_ROOT,
    DEFAULT_PERMISSION_SEED_PATH,
    PERMISSIONS_CATALOG_PATH,
)


class CatalogResolveTest(unittest.TestCase):
    def test_resolve_standard_name(self) -> None:
        catalog = PermissionsCatalog(
            resources={"sys:user": "用户"},
            actions={"query": "查询"},
        )
        self.assertEqual(catalog.resolve_name("sys:user:query"), "用户-查询")

    def test_override_wins(self) -> None:
        catalog = PermissionsCatalog(
            resources={"sys:user": "用户"},
            actions={"query": "查询"},
            overrides={"sys:user:query": "用户查询覆盖"},
        )
        self.assertEqual(catalog.resolve_name("sys:user:query"), "用户查询覆盖")

    def test_load_repo_catalog(self) -> None:
        catalog = load_catalog(PERMISSIONS_CATALOG_PATH)
        self.assertEqual(catalog.resolve_name("sys:file:recycle:purge"), "文件回收站-彻底删除")
        self.assertIn("sys:xxx", catalog.ignore_codes)


class ScanJavaTest(unittest.TestCase):
    def test_scan_and_exclude(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctrl = root / "services" / "admin" / "FooController.java"
            ctrl.parent.mkdir(parents=True)
            ctrl.write_text(
                "@PreAuthorize(\"@auth.decide('sys:user:query')\")\n"
                "@PreAuthorize(\"@auth.decide('sys:user:create')\")\n"
                "// SpEL @PreAuthorize(\"@auth.decide('...')\")\n",
                encoding="utf-8",
            )
            example = root / "services" / "service-example" / "Ex.java"
            example.parent.mkdir(parents=True)
            example.write_text("@PreAuthorize(\"@auth.decide('sys:xxx')\")\n", encoding="utf-8")
            test_java = root / "services" / "admin" / "src" / "test" / "FooTest.java"
            test_java.parent.mkdir(parents=True)
            test_java.write_text("@PreAuthorize(\"@auth.decide('sys:user:delete')\")\n", encoding="utf-8")

            hits = scan_java_permissions(
                root,
                exclude_globs=("**/src/test/**", "**/service-example/**"),
            )
            codes = unique_codes(hits, ignore_codes=frozenset({"sys:xxx"}))
            self.assertEqual(codes, ["sys:user:create", "sys:user:query"])


class SeedSqlTest(unittest.TestCase):
    def test_parse_release_seed_if_present(self) -> None:
        if not DEFAULT_PERMISSION_SEED_PATH.exists():
            self.skipTest("Release seed 不在本机")
        rows = parse_seed_sql(DEFAULT_PERMISSION_SEED_PATH)
        self.assertGreaterEqual(len(rows), 100)
        codes = {row.permission_code for row in rows}
        self.assertIn("sys:user:query", codes)

    def test_build_upsert_sql(self) -> None:
        sql = build_upsert_sql([("sys:user:query", "用户-查询", 10)])
        self.assertIn("INSERT INTO sys_permission", sql)
        self.assertIn("sys:user:query", sql)
        self.assertIn("ON DUPLICATE KEY UPDATE", sql)

    def test_build_prune_sql(self) -> None:
        sql = build_prune_sql(["sys:file:export", "sys:old:query"])
        self.assertIn("DELETE FROM sys_permission", sql)
        self.assertIn("sys:file:export", sql)
        self.assertIn("sys:old:query", sql)

    def test_build_sync_sql_with_prune_only(self) -> None:
        sql = build_sync_sql([], ["sys:file:export"], prune=True)
        self.assertNotIn("INSERT INTO", sql)
        self.assertIn("DELETE FROM sys_permission", sql)
        self.assertIn("sys:file:export", sql)


class CheckAgainstSeedTest(unittest.TestCase):
    def test_check_against_release_seed(self) -> None:
        if not DEFAULT_PERMISSION_SEED_PATH.exists():
            self.skipTest("Release seed 不在本机")
        if not DEFAULT_AUTH_SERVER_ROOT.exists():
            self.skipTest("auth-server 不在本机")
        diff = check_permissions(
            server_root=DEFAULT_AUTH_SERVER_ROOT,
            seed_path=DEFAULT_PERMISSION_SEED_PATH,
        )
        report = format_diff_report(diff)
        self.assertIn("code=", report)
        # 当前已知：代码侧已去掉 sys:file:export，seed 仍保留 → orphan 可有；不应有 unresolved
        self.assertEqual(diff.unresolved_names, [])
        self.assertEqual(diff.missing, [])
        # seed 可能残留代码已删除的码（如 sys:file:export），仅报告不失败
        self.assertIsInstance(diff.orphan, list)

    def test_gen_prune_includes_orphan_delete(self) -> None:
        if not DEFAULT_PERMISSION_SEED_PATH.exists():
            self.skipTest("Release seed 不在本机")
        if not DEFAULT_AUTH_SERVER_ROOT.exists():
            self.skipTest("auth-server 不在本机")
        plan = perms_service.build_sync_plan(
            server_root=DEFAULT_AUTH_SERVER_ROOT,
            seed_path=DEFAULT_PERMISSION_SEED_PATH,
            prune=True,
        )
        if "sys:file:export" in plan.diff.orphan:
            self.assertIn("sys:file:export", plan.prune_codes)
            self.assertIn("DELETE FROM sys_permission", plan.sql)
        self.assertEqual(plan.inserts, [])


class PruneProtectTest(unittest.TestCase):
    def test_harness_prefix_protected(self) -> None:
        catalog = load_catalog(PERMISSIONS_CATALOG_PATH)
        self.assertTrue(catalog.is_prune_protected("harness:user:read"))
        self.assertFalse(catalog.is_prune_protected("sys:file:export"))

if __name__ == "__main__":
    unittest.main()
