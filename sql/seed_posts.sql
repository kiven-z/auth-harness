-- auth-harness: 岗位 P_FANOUT / P_EDGE

DELETE FROM user_post WHERE id BETWEEN 9002003000 AND 9002003099
    OR post_id BETWEEN 9000600001 AND 9000600009;
DELETE FROM sys_post WHERE id BETWEEN 9000600001 AND 9000600009;

INSERT INTO sys_post (
    id, dept_id, post_code, post_name, status, order_num,
    create_time, update_time, create_user, update_user, version, remark
) VALUES
    (9000600001, 9000100001, 'P_FANOUT', 'Harness 扇出岗位', 1, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000600002, 9000100002, 'P_EDGE',   'Harness 边缘岗位', 1, 2, 0, NOW(), NOW(), 1, 1, 0, 'auth-harness');
