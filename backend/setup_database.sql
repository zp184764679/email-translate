-- Database Setup Script for 供应商邮件翻译系统
-- Run this on MySQL server before starting the application

-- Create database
CREATE DATABASE IF NOT EXISTS email_translate CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create user (if not using shared app user)
-- CREATE USER IF NOT EXISTS 'email_translate'@'localhost' IDENTIFIED BY 'your-password';
-- GRANT ALL PRIVILEGES ON email_translate.* TO 'email_translate'@'localhost';

-- Use existing app user (same as Portal system)
GRANT ALL PRIVILEGES ON email_translate.* TO 'app'@'localhost';
FLUSH PRIVILEGES;

-- Switch to database
USE email_translate;

-- Note: Tables will be created automatically by SQLAlchemy on first run
-- This script is for database and permission setup only

-- Verify setup
SELECT 'Database email_translate created successfully' AS status;
SHOW DATABASES LIKE 'email_translate';
