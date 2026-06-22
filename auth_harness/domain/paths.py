"""项目路径常量。"""

from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_DIR = HARNESS_ROOT / "scenarios"
SQL_DIR = HARNESS_ROOT / "sql"
EXAMPLE_CONFIG_PATH = HARNESS_ROOT / "config.example.yml"

SEED_ORDER = (
    "seed_roles_perms.sql",
    "seed_org.sql",
    "seed_posts.sql",
    "seed_users_bulk.sql",
    "seed_anchors.sql",
    "seed_grants.sql",
)

IMPACT_FIXTURES_PATH = HARNESS_ROOT / "fixtures" / "impact_cases.yml"

# 快速冒烟（3 条，兼容历史 make smoke）
SMOKE_SCENARIOS = (
    "grant-dept-remove.yml",
    "grant-dept-assign.yml",
    "role-permission-replace.yml",
)

# P0 后端闭环（文档 §5 优先集）
P0_SCENARIOS = (
    "grant-dept-assign.yml",
    "grant-dept-remove.yml",
    "grant-user-assign.yml",
    "grant-user-clear.yml",
    "grant-dept-replace.yml",
    "grant-post-assign.yml",
    "grant-post-remove.yml",
    "role-permission-replace.yml",
)

# 全量 L2 场景（不含负向与 Job）
INTEGRATION_SCENARIOS = (
    *P0_SCENARIOS,
    "role-permission-add.yml",
    "role-permission-remove.yml",
    "role-disable.yml",
    "permission-code-update.yml",
    "user-dept-assign.yml",
    "user-dept-move.yml",
    "dept-parent-change.yml",
    "user-dept-remove.yml",
    "user-post-assign.yml",
    "user-post-remove.yml",
)

# 待后端补充失效触发（SysUserServiceImpl 当前未 submit 失效事件）
PENDING_BACKEND_SCENARIOS = (
    "user-status-change.yml",
    "user-delete.yml",
)

NEGATIVE_SCENARIOS = (
    "negative-dept-rename.yml",
    "negative-role-rename.yml",
    "negative-post-sort.yml",
)
