// ===== 供应商邮件翻译系统 - PM2 生产环境配置 =====
// Linux 服务器 (61.145.212.28)

module.exports = {
  apps: [
    {
      name: 'email-backend',
      cwd: '/www/email-translate/backend',
      script: '/www/email-translate/backend/venv/bin/python',
      args: '-m uvicorn main:app --host 127.0.0.1 --port 8007',
      interpreter: 'none',
      env: {
        PYTHONUNBUFFERED: '1',
        PORT: '8007',
      },
      error_file: '/var/log/pm2/email-backend-error.log',
      out_file: '/var/log/pm2/email-backend-out.log',
      time: true,
      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
      watch: false,
      instances: 1,
      exec_mode: 'fork',
    },
  ],
};
