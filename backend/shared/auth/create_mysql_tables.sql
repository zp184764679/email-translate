-- Create users table for shared authentication
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    emp_no VARCHAR(50),
    user_type VARCHAR(20) NOT NULL DEFAULT 'employee',
    role VARCHAR(20) DEFAULT 'user',
    permissions TEXT,
    supplier_id INT NULL,
    department_id INT NULL,
    department_name VARCHAR(100) NULL,
    position_id INT NULL,
    position_name VARCHAR(100) NULL,
    team_id INT NULL,
    team_name VARCHAR(100) NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_emp_no (emp_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create default admin user (password: admin123)
-- Password hash generated with bcrypt
INSERT INTO users (username, email, hashed_password, full_name, role, permissions, is_active, is_admin)
SELECT 'admin', 'admin@jzchardware.cn', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.rFqELXIkJLm1qe', '系统管理员', 'super_admin', '["hr", "quotation", "采购", "account"]', TRUE, TRUE
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');
