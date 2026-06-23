-- auth-harness: 初始 grant_table 边

DELETE FROM grant_table WHERE id BETWEEN 9000500001 AND 9000500099;

INSERT INTO grant_table (id, subject_type, subject_id, role_id, create_time, update_time, create_user, update_user, version, remark)
VALUES
    -- D_FANOUT 部门角色：R_USER_BASE
    (9000500001, 'DEPT', 9000100001, 9000200001, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    -- D_EDGE 部门：R_SHARED（供角色权限场景）
    (9000500004, 'DEPT', 9000100002, 9000200004, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    -- P_FANOUT 岗位：R_POST_OP（G-06）
    (9000500005, 'POST', 9000600001, 9000200003, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    -- u_direct_only 直连：R_USER_BASE（G-01/02）
    (9000500006, 'USER', 9001002001, 9000200001, NOW(), NOW(), 1, 1, 0, 'auth-harness'),
    -- u_mixed_anchor 直连：R_POST_OP
    (9000500007, 'USER', 9001002004, 9000200003, NOW(), NOW(), 1, 1, 0, 'auth-harness');
