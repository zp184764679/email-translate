// ===== 供应商邮件翻译系统 - PM2 配置 (服务器部署) =====
//
// 服务器使用方法:
//   pm2 start ecosystem.config.js
//   pm2 restart email-backend
//   pm2 logs email-backend
//   pm2 save

module.exports = {
  apps: [
    {
      name: 'email-backend',
      cwd: '/www/email-translate/backend',
      script: './venv/bin/uvicorn',
      args: 'main:app --host 0.0.0.0 --port 2000',
      interpreter: 'none',
      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      error_file: '/www/email-translate/logs/error.log',
      out_file: '/www/email-translate/logs/out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss'
    }
  ]
};
