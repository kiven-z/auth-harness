-- auth-harness: 锚点用户（仅直连 / 仅部门 / 仅岗位 / 混合）+ 专用 disposable 用户
-- ID 段 9001002001..9001002100，位于 bulk 扇出用户（9001002000）之后，避免覆盖

DELETE FROM user_post WHERE user_id BETWEEN 9001002001 AND 9001002100;
DELETE FROM user_dept WHERE user_id BETWEEN 9001002001 AND 9001002100
    OR id BETWEEN 9002002100 AND 9002002999;
DELETE FROM sys_user WHERE id BETWEEN 9001002001 AND 9001002100;

INSERT INTO sys_user (
    id, username, nickname, email, phone, password, status, perm_version,
    created_at, updated_at, created_by, updated_by, version, remark
) VALUES
    (9001002001, 'harness_u_direct',  'harness_u_direct',  'harness_u_direct@harness.local',  '19000002001',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'u_direct_only'),
    (9001002002, 'harness_u_dept',    'harness_u_dept',    'harness_u_dept@harness.local',    '19000002002',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'u_dept_only'),
    (9001002003, 'harness_u_post',    'harness_u_post',    'harness_u_post@harness.local',    '19000002003',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'u_post_only'),
    (9001002004, 'harness_u_mixed_a', 'harness_u_mixed_a', 'harness_u_mixed_a@harness.local', '19000002004',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'u_mixed_anchor'),
    (9001002005, 'harness_u_shared',  'harness_u_shared',  'harness_u_shared@harness.local',  '19000002005',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'u_shared'),
    (9001002098, 'harness_u_status',  'harness_u_status',  'harness_u_status@harness.local',  '19000002098',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'status disposable'),
    (9001002099, 'harness_u_delete',  'harness_u_delete',  'harness_u_delete@harness.local',  '19000002099',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'delete disposable');

-- 任职无 status：人在 = 有行；兼职只走 is_primary。须已执行 auth-server-pro 的 view DDL。
-- u_dept_only：仅 D_CHILD
INSERT INTO user_dept (id, user_id, dept_id, is_primary, created_at, updated_at, created_by, updated_by, version, remark)
VALUES (9002002101, 9001002002, 9000100003, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness');

-- u_shared：D_EDGE（持有 R_SHARED）
INSERT INTO user_dept (id, user_id, dept_id, is_primary, created_at, updated_at, created_by, updated_by, version, remark)
VALUES (9002002103, 9001002005, 9000100002, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness');

-- u_mixed_anchor：D_CHILD + P_FANOUT
INSERT INTO user_dept (id, user_id, dept_id, is_primary, created_at, updated_at, created_by, updated_by, version, remark)
VALUES (9002002102, 9001002004, 9000100003, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness');

INSERT INTO user_post (id, user_id, post_id, is_primary, created_at, updated_at, created_by, updated_by, version, remark)
VALUES
    (9002003001, 9001002003, 9000600001, 1, NOW(), NOW(), 1, 1, 0, 'u_post_only'),
    (9002003002, 9001002004, 9000600001, 0, NOW(), NOW(), 1, 1, 0, 'u_mixed_anchor');
