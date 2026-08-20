-- auth-harness: 批量用户（9001000001..9001002000）
-- 默认密码 BCrypt("password")
-- 任职 INSERT 不含 status；须已执行 auth-server-pro db/user-org-relation-effective-view.sql

DELETE FROM user_dept WHERE user_id BETWEEN 9001000001 AND 9001002100;
DELETE FROM sys_user WHERE id BETWEEN 9001000001 AND 9001002100;

DROP PROCEDURE IF EXISTS sp_harness_seed_users;
DELIMITER $$
CREATE PROCEDURE sp_harness_seed_users()
BEGIN
    DECLARE i INT DEFAULT 1;
    DECLARE uid BIGINT;
    DECLARE uname VARCHAR(64);
    WHILE i <= 2000 DO
        SET uid = 9001000000 + i;
        SET uname = CONCAT('harness_u_', i);
        INSERT INTO sys_user (
            id, username, nickname, email, phone, password, status, perm_version,
            created_at, updated_at, created_by, updated_by, version, remark
        ) VALUES (
            uid, uname, uname,
            CONCAT(uname, '@harness.local'),
            CONCAT('19', LPAD(i, 9, '0')),
            '$2a$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6peLmJSMq/t/mJi6',
            1, 0,
            NOW(), NOW(), 1, 1, 0, 'auth-harness'
        );
        INSERT INTO user_dept (id, user_id, dept_id, is_primary, created_at, updated_at, created_by, updated_by, version, remark)
        VALUES (
            9002000000 + i, uid, 9000100001, 1,
            NOW(), NOW(), 1, 1, 0, 'auth-harness'
        );
        SET i = i + 1;
    END WHILE;
END$$
DELIMITER ;

CALL sp_harness_seed_users();
DROP PROCEDURE IF EXISTS sp_harness_seed_users;
