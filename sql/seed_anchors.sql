-- auth-harness: 锚点用户（仅直连 / 仅部门 / 仅岗位 / 混合）+ 专用 disposable 用户

DELETE FROM user_post WHERE user_id BETWEEN 9001001001 AND 9001001100;
DELETE FROM user_dept WHERE user_id BETWEEN 9001001001 AND 9001001100
    OR id BETWEEN 9002002000 AND 9002002999;
DELETE FROM sys_user WHERE id BETWEEN 9001001001 AND 9001001100;

INSERT INTO sys_user (
    id, username, nickname, email, phone, password, status, perm_version,
    create_time, update_time, create_user, update_user, version, remark
) VALUES
    (9001001001, 'harness_u_direct',  'harness_u_direct',  'harness_u_direct@harness.local',  '19000001001',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'u_direct_only'),
    (9001001002, 'harness_u_dept',    'harness_u_dept',    'harness_u_dept@harness.local',    '19000001002',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'u_dept_only'),
    (9001001003, 'harness_u_post',    'harness_u_post',    'harness_u_post@harness.local',    '19000001003',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'u_post_only'),
    (9001001004, 'harness_u_mixed_a', 'harness_u_mixed_a', 'harness_u_mixed_a@harness.local', '19000001004',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'u_mixed_anchor'),
    (9001001098, 'harness_u_status',  'harness_u_status',  'harness_u_status@harness.local',  '19000001098',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'status disposable'),
    (9001001099, 'harness_u_delete',  'harness_u_delete',  'harness_u_delete@harness.local',  '19000001099',
     '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6', 1, 0, NOW(), NOW(), 1, 1, 0, 'delete disposable');

-- u_dept_only：仅 D_CHILD
INSERT INTO user_dept (id, user_id, dept_id, is_primary, status, create_time, update_time, create_user, update_user, version, remark)
VALUES (9002002001, 9001001002, 9000100003, 1, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness');

-- u_mixed_anchor：D_CHILD + P_FANOUT
INSERT INTO user_dept (id, user_id, dept_id, is_primary, status, create_time, update_time, create_user, update_user, version, remark)
VALUES (9002002002, 9001001004, 9000100003, 1, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness');

INSERT INTO user_post (id, user_id, post_id, is_primary, status, create_time, update_time, create_user, update_user, version, remark)
VALUES
    (9002003001, 9001001003, 9000600001, 1, 1, NOW(), NOW(), 1, 1, 0, 'u_post_only'),
    (9002003002, 9001001004, 9000600001, 0, 1, NOW(), NOW(), 1, 1, 0, 'u_mixed_anchor');
