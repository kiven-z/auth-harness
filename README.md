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
    perms/              # 从 @auth.decide 扫权限码 → check/gen/apply
    domain/
      oracle.py, paths.py, impact.py
    infrastructure/
      api.py, system_paths.py, db.py, redis_client.py
    steps/ handlers.py, registry.py, context.py
    assertions/ runner.py, user_codes.py, event.py
    wait/ outbox.py
    runner/ scenario_runner.py
    services/ preflight.py, reconcile.py, impact.py
  scenarios/
  fixtures/             # impact / dept_scope / permissions_catalog.yml
  sql/
  tests/
```

## 固定测试 ID（9000 前缀）

| 实体 | ID / 编码 |
| ------ | ----------- |
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
make seed          # 灌 9000 前缀 MySQL + 清 Redis `auth:security:user:perm:9001*`
make cleanup       # 仅清理 9000 前缀（SQL + Redis 画像）
make preflight
make p0            # P0 闭环 8 场景
make integration   # 全量 21 场景 + 3 负向
make impact        # L1 fixture 6 条
make test          # 单元测试
```

## CLI 命令

| 命令 | 说明 |
| ------ | ------ |
| `make cleanup` / `python -m auth_harness cleanup` | 清理 9000 前缀测试数据（SQL + Redis 画像） |
| `python -m auth_harness seed` | 执行 sql/ 种子（先 cleanup）并删除 `9001*` Redis 画像 |
| `python -m auth_harness run <scenario.yml>` | 单场景 |
| `python -m auth_harness smoke` | 授权失效快速 3 场景（与数据权限无关） |
| `python -m auth_harness p0` | P0 套件（8 场景） |
| `python -m auth_harness integration` | 21 L2 + 3 负向 |
| `python -m auth_harness impact` | L1 影响面 fixture |
| `python -m auth_harness reconcile` | 批量对账（无 Redis 画像视为尚未加载，跳过；有画像则必须与 DB 一致） |
| `python -m auth_harness preflight` | 连通性检查 |
| `python -m auth_harness dept-scope` | 演示账号登录，断言 `/api/example/me` 的 `deptScope` |
| `python -m auth_harness dept-scope-list` | 演示账号登录，断言 `/api/example/orders` 行级过滤 |
| `python -m auth_harness data-scope` | 数据权限冒烟：`dept-scope` → `dept-scope-list` |
| `python -m auth_harness example-order-export` | 多账号并行提交 example_order 异步导出，轮询 SUCCESS、校验下载链接与执行窗口重叠 |
| `python -m auth_harness list-scenarios` | 列出场景文件 |
| `python -m auth_harness perms scan` | 扫描 `@auth.decide` 权限码 |
| `python -m auth_harness perms check` | 对照 Release seed（或 `--db`）校验漂移 |
| `python -m auth_harness perms gen` | 为缺失码生成 upsert SQL（`--prune` 可附带 DELETE orphan） |
| `python -m auth_harness perms apply` | 开发库补缺（`--prune` 同时删 orphan） |

### 权限码同步（perms）

接口上的 `@PreAuthorize("@auth.decide('sys:user:query')")` 是权限码真源；`sys_permission` / Release seed 是授权目录。不要在后端启动时自动写库，用本工具对齐：

```bash
make perms-scan
make perms-check                          # 对照 assets/Release/db/02-seed-sys-permission.sql
make perms-check ARGS='--db'              # 对照开发库（需 config.yml）
make perms-gen ARGS='-o /tmp/perms.sql'   # 只生成缺失码 INSERT
make perms-gen ARGS='--prune -o /tmp/perms.sql'   # INSERT + DELETE orphan
make perms-apply                          # 开发库只补缺
make perms-apply ARGS='--prune'           # 开发库对齐代码：补缺并删 orphan
```

中文名来自 `fixtures/permissions_catalog.yml`（`资源-动作`）。新资源/动作先补映射，再 apply。演示码（`service-example`、`sys:xxx`）已忽略；`harness:` 前缀受 `prune_protect_prefixes` 保护，`--prune` 不会删。

- **missing**：代码有、seed/DB 没有 → check 失败，gen/apply 可补
- **orphan**：seed/DB 有、代码没有 → 默认只提示；`--strict` 失败；**`--prune` 生成/执行 DELETE**（CASCADE 清角色绑定，适合开发库）
- **生产**：不要对生产库跑 `apply --prune`

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

### example_order 异步导出

与数据权限探针分开：验证跨服务建任务（example → file）→ Worker 回调取数 → 产物可下载，并验证 **多用户导出可并行**（全局 `max-concurrency`，不按用户限流）。

前置同上（演示账号 + `example_order` 种子 + 网关 + `service-example`），且 **file 异步导出 Worker 已在跑**。

```bash
make example-order-export
# 或：python -m auth_harness example-order-export --user north_chen
```

`fixtures/example_order_export_cases.yml` 中有两条及以上账号时：

1. 各账号先登录并记录 `/api/example/orders` 可见行数。
2. **同时** `POST .../export/async`，再轮询各自任务详情。
3. 每条任务 `SUCCESS`，`processedRows` 等于该账号可见行数，下载链接非空。
4. 断言执行窗口重叠（`startedAt`/`finishedAt` 相交），或轮询过程中见过至少 2 条 `RUNNING`。串行 Worker（同一时刻只有一条在跑）会在此项失败。

`--user` 只跑单个账号时跳过第 4 步。

## 场景清单（23）

### P0（8）

| 文件 | 验证点 |
| ------ | -------- |
| grant-dept-assign / remove | 部门角色扇出 |
| grant-user-assign / clear | 用户直连角色 |
| grant-dept-replace | 部门角色全量替换 |
| grant-post-assign / remove | 岗位角色 |
| role-permission-replace | 角色权限全量替换 |

### 扩展 L2（13）

role-permission-add/remove, role-disable, permission-code-update, user-dept-assign/move/remove, dept-parent-change, user-post-assign/remove, user-status-change, user-delete

### 负向（3）

negative-dept-rename, negative-role-rename, negative-post-sort（`assert_no_outbox`）

## 步骤类型（节选）

| 步骤 | 说明 |
| ------ | ------ |
| `put_dept_roles` / `put_user_roles` / `put_post_roles` | grant_table 全量覆盖 |
| `post_role_permissions` | 角色权限全量分配 |
| `post_user_dept` / `put_user_dept` / `delete_user_dept` | 用户部门（删可按 `dept_id` 查找；无关联则跳过） |
| `post_user_post` / `delete_user_post` | 用户岗位（删可按 `post_id` 查找） |
| `ensure_user_dept` / `ensure_user_post` | 幂等恢复成员（`wait_outbox: true` 时仅实际写入才等待） |
| `ensure_dept_parent` | 幂等恢复部门父节点 |
| `update_dept_meta` / `move_dept` | 部门元数据 / 移动 |
| `update_role_meta` / `update_permission_meta` / `update_post_meta` | 元数据更新 |
| `wait_outbox` | 等待 outbox SUCCESS |
| `assert_no_outbox` | 负向：不应产生 outbox |
| `assert` | triple assert（支持 `expect_outbox: false`） |

## Outbox `source_biz_id` 过滤

后端现格式为 `operation:xxxxxxxx`（8 位短 UUID），**不再嵌入业务 ID**。场景里用操作前缀匹配，例如：

| 操作 | `source_biz_id_contains` |
| ------ | -------------------------- |
| 部门/岗位/用户 grant 全量覆盖 | `replace-roles:` |
| 角色权限分配 | `assign-permissions:` |
| 用户部门增/改/批删 | `create-dept:` / `update-dept:` / `delete-dept:` |
| 用户部门清空全部 | `clear-dept:`（仅 `DELETE /{userId}/all`；批删是 `delete-dept:`） |
| 用户岗位增/批删 | `create-post:` / `delete-post:` |
| 用户岗位清空全部 | `clear-post:`（仅 `DELETE /{userId}/all`；批删是 `delete-post:`） |
| 部门移动 | `move:` |
| 角色/权限元数据更新 | `update:` |

负向场景（`assert_no_outbox`）不设过滤，按全局游标判定。

**游标规则**：每个 step 入口快照全局 `max(id)`；`wait_outbox` 用**上一步**的入口游标。YAML 写成「变更 API → `wait_outbox`」，不要再插 `prepare_outbox_wait`。`source_biz_id_contains` 只筛选行（`operation:` 前缀匹配），不参与游标。

`make seed` 只写 MySQL，会顺带删掉 9001* Redis 画像，避免上一轮测试残留导致 `make reconcile` 误报。seed 之后无画像不算不一致；场景 assert 仍要求 outbox 刷出画像。

## 剩余缺口

- **J-01/J-02**：Outbox Job 补偿场景（需关闭 sync-dispatch 或 mock Feign）
- **U-01/U-02**：用户状态/删除失效（需 auth-server 补充 trigger）
- **L1 C4**：L2 `event.impacted_user_count` 与 L1 集合自动比对（可后续加 assert 块）
