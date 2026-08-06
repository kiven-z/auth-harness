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
  fixtures/           # impact_cases.yml + dept_scope*.yml
  sql/                # 种子与清理
  tests/
```

## 固定测试 ID（9000 前缀）

| 实体 | ID / 编码 |
|------|-----------|
| D_FANOUT / D_EDGE / D_CHILD | `9000100001` / `9000100002` / `9000100003` |
| P_FANOUT / P_EDGE | `9000600001` / `9000600002` |
| 扇出用户 | `9001000001` … `9001002000` |
| u_direct / u_dept / u_post / u_mixed_anchor / u_shared | `9001002001` … `9001002005` |
| R_USER_BASE … R_SHARED | `9000200001` … `9000200004` |

## 快速开始

```bash
cd auth-harness
cp config.example.yml config.yml   # 填写 MySQL / Redis / admin / JWT
# 直接连业务库 auth_admin + Redis db0（与 Release 种子同库；9000 前缀与演示数据隔离）
# 管理账号：Administrator / Admin@123456

make install
make seed          # 只灌/刷新 9000 前缀 harness 数据（先 cleanup，不碰 Release 1~14）
make cleanup       # 仅清理 9000 前缀
make preflight
make p0            # P0 闭环 8 场景
make integration   # 全量 21 场景 + 3 负向
make impact        # L1 fixture 6 条
make test          # 单元测试
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `make cleanup` / `python -m auth_harness cleanup` | 清理 9000 前缀测试数据（`sql/cleanup.sql`） |
| `python -m auth_harness seed` | 执行 sql/ 种子（会先跑 cleanup.sql） |
| `python -m auth_harness run <scenario.yml>` | 单场景 |
| `python -m auth_harness smoke` | 授权失效快速 3 场景（与数据权限无关） |
| `python -m auth_harness p0` | P0 套件（8 场景） |
| `python -m auth_harness integration` | 21 L2 + 3 负向 |
| `python -m auth_harness impact` | L1 影响面 fixture |
| `python -m auth_harness reconcile` | 批量对账 |
| `python -m auth_harness preflight` | 连通性检查 |
| `python -m auth_harness dept-scope` | 演示账号登录，断言 `/api/example/me` 的 `deptScope` |
| `python -m auth_harness dept-scope-list` | 演示账号登录，断言 `/api/example/orders` 行级过滤 |
| `python -m auth_harness data-scope` | 数据权限冒烟：`dept-scope` → `dept-scope-list` |
| `python -m auth_harness list-scenarios` | 列出场景文件 |

### 数据权限探针

与 `make smoke`（授权失效）分开：依赖 Release 演示账号 + `example_order` 种子 + 网关 `/api/example/**` + 已启动的 `service-example`。

**一键冒烟**

```bash
make data-scope
# 或：python -m auth_harness data-scope --user north_chen
```

**阶段 1 — 画像**：验证「配置 → AuthProfile.deptScope」

```bash
make dept-scope
# 或：python -m auth_harness dept-scope --user north_chen
```

期望见 `fixtures/dept_scope_cases.yml`（含路径盲区：`east_role_only` / `hr_self_override` / `orphan_self` / `admin_narrow`）。

**阶段 2 — 行级过滤**：验证「画像 → SQL `@DataScope`」

前置：空库已跑 Release `run-init.sh`（含 `13-seed-example-order.sql`，订单 id 1～12）；已有库可补灌 `auth-server/db/example-order-data-scope-demo.sql`。

```bash
make dept-scope-list
```

期望见 `fixtures/dept_scope_list_cases.yml`。

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

## Outbox `source_biz_id` 过滤

后端现格式为 `operation:xxxxxxxx`（8 位短 UUID），**不再嵌入业务 ID**。场景里用操作前缀匹配，例如：

| 操作 | `source_biz_id_contains` |
|------|--------------------------|
| 部门/岗位/用户 grant 全量覆盖 | `replace-roles:` |
| 角色权限分配 | `assign-permissions:` |
| 用户部门增/改/清 | `create-dept:` / `update-dept:` / `clear-dept:` |
| 用户岗位增/清 | `create-post:` / `clear-post:` |
| 部门移动 | `move:` |
| 角色/权限元数据更新 | `update:` |

负向场景（`assert_no_outbox`）不设过滤，按全局游标判定。

## 剩余缺口

- **J-01/J-02**：Outbox Job 补偿场景（需关闭 sync-dispatch 或 mock Feign）
- **U-01/U-02**：用户状态/删除失效（需 auth-server 补充 trigger）
- **L1 C4**：L2 `event.impacted_user_count` 与 L1 集合自动比对（可后续加 assert 块）
