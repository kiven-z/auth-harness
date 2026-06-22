# auth-harness — 授权失效链路测试工具

用于自动化验证 **Admin API 变更 → Outbox → Auth 失效 → Redis 画像刷新** 全链路，避免手工点 UI。

## 架构要点

```
system-admin API (grant_table / user_dept / role_permission)
    → sys_authorization_invalidation_outbox (PENDING → SUCCESS)
    → Feign → auth-service /invalidate
    → Redis key: auth:security:user:perm:{userId}
```

**DB 真值（Oracle）**

1. **推荐**：`GET /api/auth/inner/authorization/principal/{userId}/effective-codes`（`buildByUserId` 重建）
2. **回退**：直接执行与 `UserAuthorizationGrantMapper` 等价的 SQL（`reconcile --oracle sql`）

内部接口需请求头 `X-Internal-JWT`（服务身份 JWT，与 `auth.common.jwt` 配置一致）。

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
# 或在 IDE / 启动脚本中设置同等变量
```

`config.example.yml` 默认对齐 **test** 环境；本地 dev 联调时复制后改回 `auth_admin_base` 与 Redis `db: 0`。

## 前置条件

- Python 3.10+（推荐 `python3-venv`；无 venv 时可用 `python3 -m pip install --user -r requirements.txt`）
- 可访问的 MySQL（`auth_admin_test`）、Redis、auth-service（20001）、system-service（20002）
- **管理账号**：`config.yml` 中 `admin.username` / `admin.password` 须在目标库中存在，且具备 `sysDept:update`、`sysRole:update`、`sysUserRole:update` 等权限（harness 不创建管理员，仅使用已有账号）
- `auth.system.authorization-invalidation.sync-dispatch-enabled: true`（默认开启，同步投递）
- 运行前建议：`make preflight`（检查 MySQL / Redis / 服务 / 登录）。服务探测访问 `/actuator/health`；若 Spring Security 保护 actuator，返回 `401`/`403` 亦视为服务已启动（仅连接失败、超时或其他状态码如 `404`/`5xx` 会失败）

## 快速开始

```bash
cd auth-harness

# 1. 配置
cp config.example.yml config.yml
# 编辑 config.yml：MySQL / Redis / 管理账号 / internal_jwt.secret（与 Nacos auth.common.jwt 一致）

# 2. 安装依赖
make install
# 或: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
# 若无 python3-venv: python3 -m pip install --user -r requirements.txt

# 3. 播种测试数据（会先执行 cleanup.sql 清理同 ID 范围的旧数据，可重复运行）
make seed

# 3.5 可选：连通性检查
make preflight

# 4. 冒烟（部门移除角色 / 部门分配角色 / 角色权限替换）
make auth-test
# 等价: make smoke
```

## CLI 命令

```bash
# 播种 SQL（roles → org → users → grants）
python -m auth_harness seed

# 清理测试数据
python -m auth_harness cleanup

# 运行单个场景
python -m auth_harness run scenarios/grant-dept-assign.yml

# 对账：DB oracle vs Redis
python -m auth_harness reconcile --user 9001000001
python -m auth_harness reconcile --dept D_FANOUT --sample 20
python -m auth_harness reconcile --sample 50
python -m auth_harness reconcile --user 9001000001 --oracle sql   # SQL 回退

# 冒烟三场景
python -m auth_harness smoke

# 启动前检查（MySQL / Redis / 服务 / 管理账号）
python -m auth_harness preflight

# 列出场景
python -m auth_harness list-scenarios
```

**退出码**：`reconcile` / `run` / `smoke` 在首个不一致或断言失败时返回 `1`。

## API 映射（已实现）

| 操作             | 方法与路径                                                                                |
| ---------------- | ----------------------------------------------------------------------------------------- |
| 登录             | `POST /api/auth/login/username`                                                           |
| 部门角色全量覆盖 | `PUT /api/system/dept/{deptId}/roles` `{roleIds:[]}`                                      |
| 用户直连角色     | `PUT /api/system/user-role/{userId}`                                                      |
| 角色权限全量分配 | `POST /api/system/role/{roleId}/permissions` `{permissionIds:[]}`                         |
| 内部生效码       | `GET /api/auth/inner/authorization/principal/{userId}/effective-codes` + `X-Internal-JWT` |

## 场景说明

| 文件                          | 验证点                                                       |
| ----------------------------- | ------------------------------------------------------------ |
| `grant-dept-assign.yml`       | 部门追加 `R_DEPT_MGR`，扇出 1000 用户权限刷新                |
| `grant-dept-remove.yml`       | 部门移除角色后成员不再持有该角色（grant 行已删仍能正确失效） |
| `role-permission-replace.yml` | 角色权限全量替换后 Redis 与 DB 一致                          |

## Outbox 等待

`wait_outbox` 轮询 `sys_authorization_invalidation_outbox`，按 `source_biz_id_contains` 匹配最新行，直至 `status=SUCCESS`（失败态 `FAILED`/`DEAD` 立即报错）。

## 目录结构

```
auth-harness/
  auth_harness/     # Python 包
  scenarios/        # YAML 场景
  sql/              # 种子与清理脚本
  config.example.yml
  Makefile
  run.sh
```

## 安全提示

- **勿提交** `config.yml`（已 gitignore）
- `internal_jwt.secret` 须与运行环境 JWT 密钥一致，仅用于本地/测试环境
