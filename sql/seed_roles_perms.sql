-- auth-harness: 测试角色与权限（ID 前缀 90002 / 90003）
-- 密码见 README（默认 password，BCrypt）

DELETE FROM sys_role_permission WHERE role_id BETWEEN 9000200001 AND 9000200004;
DELETE FROM sys_permission WHERE id BETWEEN 9000300001 AND 9000300004;
DELETE FROM sys_role WHERE id BETWEEN 9000200001 AND 9000200004;

INSERT INTO sys_role (id, role_code, role_name, status, order_num, create_time, update_time, create_user, update_user, version, remark)
VALUES
    (9000200001, 'R_USER_BASE', 'Harness 基础用户', 1, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000200002, 'R_DEPT_MGR',  'Harness 部门管理', 1, 2, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000200003, 'R_POST_OP',   'Harness 岗位操作', 1, 3, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000200004, 'R_SHARED',    'Harness 共享角色',   1, 4, NOW(), NOW(), 1, 1, 0, 'auth-harness');

INSERT INTO sys_permission (id, permission_code, permission_name, permission_type, order_num, status, create_time, update_time, create_user, update_user, version, remark)
VALUES
    (9000300001, 'harness:user:read',  'Harness 用户读', 1, 1, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000300002, 'harness:dept:manage', 'Harness 部门管', 1, 2, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000300003, 'harness:post:operate', 'Harness 岗位操', 1, 3, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000300004, 'harness:shared:view',  'Harness 共享视', 1, 4, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness');

INSERT INTO sys_role_permission (id, role_id, permission_id, create_time, update_time, create_user, update_user, version, remark)
VALUES
    (9000400001, 9000200001, 9000300001, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000400002, 9000200002, 9000300002, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000400003, 9000200003, 9000300003, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000400004, 9000200004, 9000300004, NOW(), NOW(), 1, 1, 0, 'auth-harness');
