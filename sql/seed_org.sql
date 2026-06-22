-- auth-harness: 部门树（固定 ID 90001xxxx，避免雪花 JSON 精度问题）

DELETE FROM dept_closure WHERE ancestor_id BETWEEN 9000100000 AND 9000100099
    OR descendant_id BETWEEN 9000100000 AND 9000100099;
DELETE FROM sys_dept WHERE id BETWEEN 9000100000 AND 9000100099;

INSERT INTO sys_dept (id, parent_id, dept_name, dept_code, status, order_num, is_deleted, create_time, update_time, create_user, update_user, version, remark)
VALUES
    (9000100000, 0, 'Harness 根部门', 'D_ROOT', 1, 0, 0, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000100001, 9000100000, 'Harness 扇出部门', 'D_FANOUT', 1, 1, 0, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000100002, 9000100000, 'Harness 边缘部门', 'D_EDGE', 1, 2, 0, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    (9000100003, 9000100001, 'Harness 子部门', 'D_CHILD', 1, 3, 0, NOW(), NOW(), 1, 1, 0, 'auth-harness');

-- 闭包：自环 + 父子（与 sp_dept_insert 语义一致）
INSERT INTO dept_closure (ancestor_id, descendant_id, depth) VALUES
    (9000100000, 9000100000, 0),
    (9000100001, 9000100001, 0),
    (9000100002, 9000100002, 0),
    (9000100003, 9000100003, 0),
    (9000100000, 9000100001, 1),
    (9000100000, 9000100002, 1),
    (9000100000, 9000100003, 2),
    (9000100001, 9000100003, 1);
