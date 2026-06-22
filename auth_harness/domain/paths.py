"""项目路径常量。"""

from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_DIR = HARNESS_ROOT / "scenarios"
SQL_DIR = HARNESS_ROOT / "sql"
EXAMPLE_CONFIG_PATH = HARNESS_ROOT / "config.example.yml"

SEED_ORDER = (
    "seed_roles_perms.sql",
    "seed_org.sql",
    "seed_users_bulk.sql",
    "seed_grants.sql",
)

SMOKE_SCENARIOS = (
    "grant-dept-remove.yml",
    "grant-dept-assign.yml",
    "role-permission-replace.yml",
)
