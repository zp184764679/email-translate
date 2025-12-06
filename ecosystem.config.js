// ===== 供应商邮件翻译系统 - PM2 配置 =====
// Windows 开发环境

module.exports = {
  apps: [
    // ==================== 前端服务 ====================
    {
      name: 'email-frontend',
      cwd: 'C:\\Users\\Admin\\Desktop\\供应商邮件翻译系统\\frontend',
      script: 'cmd.exe',
      args: '/c npm run dev',
      interpreter: 'none',
      windowsHide: true,
      env: {
        NODE_ENV: 'development',
        PORT: '4567',
      },
      error_file: 'C:\\Users\\Admin\\Desktop\\logs\\email-frontend-error.log',
      out_file: 'C:\\Users\\Admin\\Desktop\\logs\\email-frontend-out.log',
      time: true,
      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
    },

    // ==================== 后端服务 ====================
    {
      name: 'email-backend',
      cwd: 'C:\\Users\\Admin\\Desktop\\供应商邮件翻译系统\\backend',
      script: 'C:\\Users\\Admin\\Desktop\\供应商邮件翻译系统\\backend\\venv\\Scripts\\python.exe',
      args: '-m uvicorn main:app --host 0.0.0.0 --port 8007',
      interpreter: 'none',
      windowsHide: true,
      env: {
        PYTHONUNBUFFERED: '1',
        PORT: '8007',
      },
      error_file: 'C:\\Users\\Admin\\Desktop\\logs\\email-backend-error.log',
      out_file: 'C:\\Users\\Admin\\Desktop\\logs\\email-backend-out.log',
      time: true,
      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
    },
  ],
};
