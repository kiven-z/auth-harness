-- auth-harness: 批量用户（9001000001..9001001000）+ u_anchor / u_mixed
-- 默认密码 BCrypt("password")

DELETE FROM user_dept WHERE user_id BETWEEN 9001000001 AND 9001001100;
DELETE FROM sys_user WHERE id BETWEEN 9001000001 AND 9001001100;

DROP PROCEDURE IF EXISTS sp_harness_seed_users;
DELIMITER $$
CREATE PROCEDURE sp_harness_seed_users()
BEGIN
    DECLARE i INT DEFAULT 1;
    DECLARE uid BIGINT;
    DECLARE uname VARCHAR(64);
    WHILE i <= 1000 DO
        SET uid = 9001000000 + i;
        SET uname = CONCAT('harness_u_', i);
        INSERT INTO sys_user (
            id, username, nickname, password, status, perm_version,
            create_time, update_time, create_user, update_user, version, remark
        ) VALUES (
            uid, uname, uname,
            '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6',
            1, 0,
            NOW(), NOW(), 1, 1, 0, 'auth-harness'
        );
        INSERT INTO user_dept (id, user_id, dept_id, is_primary, status, create_time, update_time, create_user, update_user, version, remark)
        VALUES (
            9002000000 + i, uid, 9000100001, 1, 1,
            NOW(), NOW(), 1, 1, 0, 'auth-harness'
        );
        SET i = i + 1;
    END WHILE;

    -- u_mixed：挂在 D_EDGE
    INSERT INTO user_dept (id, user_id, dept_id, is_primary, status, create_time, update_time, create_user, update_user, version, remark)
    VALUES (9002001001, 9001000002, 9000100002, 0, 1, NOW(), NOW(), 1, 1, 0, 'auth-harness');
END$$
DELIMITER ;

CALL sp_harness_seed_users();
DROP PROCEDURE IF EXISTS sp_harness_seed_users;
