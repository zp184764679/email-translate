// ===== 供应商邮件翻译系统 - PM2 配置 (服务器部署) =====
//
// 服务器使用方法:
//   pm2 start ecosystem.config.js
//   pm2 restart all
//   pm2 logs
//   pm2 save
//
// 日志查看:
//   pm2 logs email-backend --lines 100
//   tail -f /www/email-translate/logs/email-backend.log

module.exports = {
  apps: [
    // FastAPI 后端服务
    {
      name: 'email-backend',
      cwd: '/www/email-translate/backend',
      script: './venv/bin/uvicorn',
      args: 'main:app --host 0.0.0.0 --port 2000',
      interpreter: 'none',
      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        LOG_LEVEL: 'INFO',
        LOG_DIR: '/www/email-translate/logs'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',

      // 日志配置
      error_file: '/www/email-translate/logs/email-backend-error.log',
      out_file: '/www/email-translate/logs/email-backend.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,

      // 日志轮转 (需要 pm2-logrotate 模块)
      // pm2 install pm2-logrotate
      // pm2 set pm2-logrotate:max_size 50M
      // pm2 set pm2-logrotate:retain 10
      // pm2 set pm2-logrotate:compress true
    },

    // Celery Worker - 异步任务处理
    {
      name: 'celery-worker',
      cwd: '/www/email-translate/backend',
      script: './venv/bin/celery',
      args: '-A celery_app worker --loglevel=info --concurrency=4',
      interpreter: 'none',
      env: {
        PYTHONUNBUFFERED: '1',
        LOG_LEVEL: 'INFO',
        LOG_DIR: '/www/email-translate/logs'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '800M',

      error_file: '/www/email-translate/logs/celery-worker-error.log',
      out_file: '/www/email-translate/logs/celery-worker.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true
    },

    // Celery Beat - 定时任务调度
    {
      name: 'celery-beat',
      cwd: '/www/email-translate/backend',
      script: './venv/bin/celery',
      args: '-A celery_app beat --loglevel=info',
      interpreter: 'none',
      env: {
        PYTHONUNBUFFERED: '1',
        LOG_LEVEL: 'INFO',
        LOG_DIR: '/www/email-translate/logs'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '200M',

      error_file: '/www/email-translate/logs/celery-beat-error.log',
      out_file: '/www/email-translate/logs/celery-beat.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true
    }
  ]
};
