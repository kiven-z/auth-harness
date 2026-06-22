# auth-harness — 授权失效链路测试工具

用于自动化验证 **Admin API 变更 → Outbox → Auth 失效 → Redis 画像刷新** 全链路（L2 smoke），以及 **L1 影响面 SQL 反查**。

## 架构

```text
YAML scenario → ScenarioRunner → StepRegistry (步骤策略)
                               → AssertRunner (oracle + redis + 可选 event)
                               → infrastructure (API / MySQL / Redis)
```

**三层断言（triple assert）**

1. **DB oracle**：`GET /api/auth/inner/authorization/principal/{userId}/effective-codes`（或 SQL 回退）
2. **Redis**：`auth:security:user:perm:{userId}`
3. **可选事件表**：`auth_authorization_invalidation_event`（`impacted_user_count` 等；`wait_outbox` 后自动取 `event_id`）

## 包结构

```text
auth-harness/
  auth_harness/
    cli.py
    domain/
      oracle.py, paths.py, impact.py    # L1 影响面 SQL
    infrastructure/
      api.py, db.py, redis_client.py
    steps/ handlers.py, registry.py, context.py
    assertions/ runner.py, user_codes.py, event.py
    wait/ outbox.py
    runner/ scenario_runner.py
    services/ preflight.py, reconcile.py, impact.py
  scenarios/          # 23 个 YAML（21 可跑 + 2 待后端）
  fixtures/           # L1 impact_cases.yml
  sql/                # 种子与清理
  tests/
```

## 固定测试 ID（9000 前缀）

| 实体 | ID / 编码 |
|------|-----------|
| D_FANOUT / D_EDGE / D_CHILD | `9000100001` / `9000100002` / `9000100003` |
| P_FANOUT / P_EDGE | `9000600001` / `9000600002` |
| 扇出用户 | `9001000001` … `9001001000` |
| u_direct / u_dept / u_post / u_mixed_anchor | `9001001001` … `9001001004` |
| R_USER_BASE … R_SHARED | `9000200001` … `9000200004` |

## 快速开始

```bash
cd auth-harness
cp config.example.yml config.yml   # 填写 MySQL / Redis / admin / JWT
export SPRING_PROFILES_ACTIVE=test

make install
make seed          # 会先执行 cleanup.sql 再灌种子
make cleanup       # 仅清理 9000 前缀测试数据（sql/cleanup.sql）
make preflight
make p0          # P0 闭环 8 场景
make integration # 全量 21 场景 + 3 负向
make impact      # L1 fixture 6 条
make test        # 单元测试
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `make cleanup` / `python -m auth_harness cleanup` | 清理 9000 前缀测试数据（`sql/cleanup.sql`） |
| `python -m auth_harness seed` | 执行 sql/ 种子（会先跑 cleanup.sql） |
| `python -m auth_harness run <scenario.yml>` | 单场景 |
| `python -m auth_harness smoke` | 快速 3 场景 |
| `python -m auth_harness p0` | P0 套件（8 场景） |
| `python -m auth_harness integration` | 21 L2 + 3 负向 |
| `python -m auth_harness impact` | L1 影响面 fixture |
| `python -m auth_harness reconcile` | 批量对账 |
| `python -m auth_harness preflight` | 连通性检查 |
| `python -m auth_harness list-scenarios` | 列出场景文件 |

## 场景清单（23）

### P0（8）

| 文件 | 验证点 |
|------|--------|
| grant-dept-assign / remove | 部门角色扇出 |
| grant-user-assign / clear | 用户直连角色 |
| grant-dept-replace | 部门角色全量替换 |
| grant-post-assign / remove | 岗位角色 |
| role-permission-replace | 角色权限全量替换 |

### 扩展 L2（13）

role-permission-add/remove, role-disable, permission-code-update, user-dept-assign/move/remove, dept-parent-change, user-post-assign/remove

### 负向（3）

negative-dept-rename, negative-role-rename, negative-post-sort（`assert_no_outbox`）

### 待后端（2）

`user-status-change.yml`、`user-delete.yml` — `SysUserServiceImpl` 当前未触发失效 outbox，未纳入 `make integration`。

## 步骤类型（节选）

| 步骤 | 说明 |
|------|------|
| `put_dept_roles` / `put_user_roles` / `put_post_roles` | grant_table 全量覆盖 |
| `post_role_permissions` | 角色权限全量分配 |
| `post_user_dept` / `put_user_dept` / `delete_user_dept` | 用户部门 |
| `post_user_post` / `delete_user_post` | 用户岗位 |
| `ensure_user_post` | 幂等恢复岗位成员（`wait_outbox: true` 时仅新建关联才等待） |
| `update_dept_meta` / `move_dept` | 部门元数据 / 移动 |
| `update_role_meta` / `update_permission_meta` / `update_post_meta` | 元数据更新 |
| `wait_outbox` | 等待 outbox SUCCESS |
| `assert_no_outbox` | 负向：不应产生 outbox |
| `assert` | triple assert（支持 `expect_outbox: false`） |

## Outbox `source_biz_id` 过滤示例

| 操作 | `source_biz_id_contains` |
|------|--------------------------|
| 部门 grant | `9000100001` |
| 用户直连角色 | `replace-roles:9001001001` |
| 岗位 grant | `post:9000600001` |
| 角色权限 | `assign-permissions:R_SHARED` |
| 用户部门 | `create-dept:9001001001` |

## CI

`.github/workflows/auth-harness.yml`：push 跑单元测试；`workflow_dispatch` 可跑 `make integration`（需配置 secrets）。

## 剩余缺口

- **J-01/J-02**：Outbox Job 补偿场景（需关闭 sync-dispatch 或 mock Feign）
- **U-01/U-02**：用户状态/删除失效（需 auth-server 补充 trigger）
- **L1 C4**：L2 `event.impacted_user_count` 与 L1 集合自动比对（可后续加 assert 块）
