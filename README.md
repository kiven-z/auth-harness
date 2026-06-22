# auth-harness — 授权失效链路测试工具

用于自动化验证 **Admin API 变更 → Outbox → Auth 失效 → Redis 画像刷新** 全链路（L2 smoke），避免手工点 UI。

## 架构

```text
YAML scenario → ScenarioRunner → StepRegistry (步骤策略)
                               → AssertRunner (oracle + redis + 可选 event)
                               → infrastructure (API / MySQL / Redis)
```

**三层断言（triple assert）**

1. **DB oracle**：`GET /api/auth/inner/authorization/principal/{userId}/effective-codes`（或 SQL 回退）
2. **Redis**：`auth:security:user:perm:{userId}`
3. **可选事件表**：`auth_authorization_invalidation_event`（`impacted_user_count` 等）

内部接口需请求头 `X-Internal-JWT`（服务身份 JWT，与 `auth.common.jwt` 配置一致）。

## 包结构

```text
auth-harness/
  auth_harness/
    cli.py                 # Click 入口
    config.py              # config.yml 加载
    domain/
      oracle.py            # DB vs Redis 对比
      paths.py             # 场景/SQL 路径常量
    infrastructure/
      api.py               # HTTP 客户端
      db.py                # MySQL（seed、outbox、event、oracle SQL）
      redis_client.py      # Redis 画像读取
    steps/
      registry.py          # 步骤注册表
      context.py           # 步骤共享上下文（含 outbox 游标）
      handlers.py          # 内置步骤处理器
    assertions/
      runner.py            # 断言块（含 reconcile 重试）
      user_codes.py        # 用户角色/权限码断言
      event.py             # 失效事件表断言
    wait/
      outbox.py            # outbox 轮询（游标防陈旧 SUCCESS）
    runner/
      scenario_runner.py   # YAML 场景执行
    services/
      reconcile.py         # 批量对账 CLI 逻辑
      preflight.py         # 连通性检查
  scenarios/               # YAML 场景
  sql/                     # 种子与清理脚本
  tests/                   # 单元测试（纯逻辑）
```

## 固定测试 ID（9000 前缀）

> 使用固定大整数，避免前端 JSON 雪花 ID 精度丢失。

| 实体        | ID / 编码                              |
| ----------- | -------------------------------------- |
| D_FANOUT    | `9000100001`                           |
| D_EDGE      | `9000100002`                           |
| 扇出用户    | `9001000001` … `9001001000`（1000 人） |
| u_anchor    | `9001000001`                           |
| u_mixed     | `9001000002`                           |
| R_USER_BASE | `9000200001`                           |
| R_DEPT_MGR  | `9000200002`                           |
| R_POST_OP   | `9000200003`                           |
| R_SHARED    | `9000200004`                           |

种子用户默认密码：`password`（BCrypt）。

## Dev vs Test 环境

auth-server 通过 Spring Profile 区分环境（Nacos namespace 同为 `${spring.profiles.active}`）：

| Profile       | MySQL 库          | 主机         | Redis db |
| ------------- | ----------------- | ------------ | -------- |
| `dev`（默认） | `auth_admin_base` | 192.168.3.19 | 0        |
| `test`        | `auth_admin_test` | 192.168.3.4  | 1        |

运行 harness 前，请让 **auth-service、system-service** 使用 test 配置，避免写入 dev 库或 Redis db 0：

```bash
export SPRING_PROFILES_ACTIVE=test
```

`config.example.yml` 默认对齐 **test** 环境。

## 前置条件

- Python 3.10+
- 可访问的 MySQL（`auth_admin_test`）、Redis、auth-service（20001）、system-service（20002）
- **管理账号**：`config.yml` 中 `admin` 须在目标库中存在，且具备 `sysDept:update`、`sysRole:update` 等权限
- `auth.system.authorization-invalidation.sync-dispatch-enabled: true`（默认开启）
- 运行前建议：`make preflight`

## 快速开始

```bash
cd auth-harness

cp config.example.yml config.yml
# 编辑 MySQL / Redis / admin / internal_jwt.secret

make install
make seed
make preflight   # 可选
make auth-test   # 等价 make smoke
```

## CLI 命令

```bash
python -m auth_harness seed
python -m auth_harness cleanup
python -m auth_harness run scenarios/grant-dept-assign.yml
python -m auth_harness reconcile --user 9001000001
python -m auth_harness reconcile --dept D_FANOUT --sample 20
python -m auth_harness smoke
python -m auth_harness preflight
python -m auth_harness list-scenarios
make test        # 单元测试
```

**退出码**：`reconcile` / `run` / `smoke` 在首个不一致或断言失败时返回 `1`。

## 如何新增场景

在 `scenarios/` 下新建 YAML，格式与现有一致：

```yaml
name: my-scenario
description: 简短说明
setup:          # 可选
  - put_dept_roles:
      dept_id: 9000100001
      role_ids: [9000200001]
  - wait_outbox:
      source_biz_id_contains: "9000100001"
steps:
  - put_dept_roles:
      dept_id: 9000100001
      role_ids: [9000200001, 9000200002]
  - wait_outbox:
      source_biz_id_contains: "9000100001"
  - assert:
      impacted_user_count_min: 1000    # 部门子树成员数下限
      event:                           # 可选：事件表断言
        impacted_user_count_min: 1000
      users:
        - user_id: 9001000001
          roles_contain: [R_DEPT_MGR]
      sample_from_dept:
        dept_id: 9000100001
        sample_size: 5
        roles_contain: [R_DEPT_MGR]
```

顶层 `assert:` 块与步骤内 `- assert:` 等价；`assert` 块会自动按 `config.wait` 重试（与 `reconcile` 相同策略）。

## 如何新增步骤类型

在 `auth_harness/steps/handlers.py`（或新模块）中注册：

```python
from auth_harness.steps.registry import DEFAULT_REGISTRY

register = DEFAULT_REGISTRY.register

@register("my_action")
def my_action(ctx: StepContext, params: dict) -> None:
  ctx.api.some_call(...)
```

YAML 中即可使用 `- my_action: { ... }`。`StepContext` 提供 `config`、`conn`、`rds`、`api` 及 `last_outbox_row`。

可选步骤：

| 步骤 | 说明 |
| ---- | ---- |
| `put_dept_roles` | 部门角色全量覆盖 |
| `put_user_roles` | 用户直连角色 |
| `post_role_permissions` | 角色权限全量分配 |
| `wait_outbox` | 等待 outbox SUCCESS（自动使用上一步边界游标） |
| `prepare_outbox_wait` | 显式记录游标（高级用法） |
| `reconcile_user` | 单用户对账（无重试） |
| `assert` | 断言块（含重试） |

## Outbox 等待与游标

`wait_outbox` 只匹配**上一步开始前**之后产生的新 outbox 行（`id > boundary_cursor`），避免匹配到历史 `SUCCESS` 行。

`source_biz_id_contains` 须与后端 `source_biz_id` 格式一致：

| 操作 | 示例 filter |
| ---- | ----------- |
| 部门角色 | `9000100001`（部门 ID） |
| 角色权限 | `assign-permissions:R_SHARED`（`assign-permissions:{roleCode}`） |

每步执行前 `ScenarioRunner` 记录 outbox 入口游标；`wait_outbox` 使用**上一步**的入口游标。也可用 `prepare_outbox_wait` 显式指定游标。

## 内置场景

| 文件                          | 验证点                                       |
| ----------------------------- | -------------------------------------------- |
| `grant-dept-assign.yml`       | 部门追加 `R_DEPT_MGR`，扇出 1000 用户刷新    |
| `grant-dept-remove.yml`       | 部门移除角色后成员不再持有该角色             |
| `role-permission-replace.yml` | 角色权限全量替换后 Redis 与 DB 一致          |

## API 映射

| 操作             | 方法与路径                                                                                |
| ---------------- | ----------------------------------------------------------------------------------------- |
| 登录             | `POST /api/auth/login/username`                                                           |
| 部门角色全量覆盖 | `PUT /api/system/dept/{deptId}/roles`                                                     |
| 用户直连角色     | `PUT /api/system/user-role/{userId}`                                                      |
| 角色权限全量分配 | `POST /api/system/role/{roleId}/permissions`                                              |
| 内部生效码       | `GET /api/auth/inner/authorization/principal/{userId}/effective-codes` + `X-Internal-JWT` |

## 安全提示

- **勿提交** `config.yml`（已 gitignore）
- `internal_jwt.secret` 须与运行环境 JWT 密钥一致，仅用于本地/测试环境
