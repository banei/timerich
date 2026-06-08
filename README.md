# TimeRich

纳指100 + 红利低波 · 定投组合管理系统

GitHub: https://github.com/banei/timerich

## 快速启动

### 前置要求

- Docker Desktop（Win/Mac）或 Docker Engine（Linux）
- Docker Compose v2

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，修改 MYSQL 密码和 JWT_SECRET_KEY
```

### 2. 启动

**Windows (PowerShell):**

```powershell
./manage.ps1 up
```

**Linux / macOS:**

```bash
chmod +x manage.sh scripts/*.sh
./manage.sh up
```

启动后自动执行：数据库迁移 → 种子数据（admin/112233 + 基金池）

### 3. 访问

| 地址 | 说明 |
|---|---|
| http://localhost:8050 | Web 前端 |
| http://localhost:8051/docs | API 文档 |
| http://localhost:8051/health | 健康检查 |

默认管理员：`admin` / `112233`

阿里云部署：安全组开放 **8050–8059**，浏览器访问 `http://<公网IP>:8050`

## 运维命令

```powershell
./manage.ps1 ps       # 查看状态
./manage.ps1 logs     # 查看日志
./manage.ps1 restart  # 重启
./manage.ps1 backup   # 手动备份
./manage.ps1 down     # 停止
```

## 技术栈

- 后端：Python 3.11 + FastAPI + SQLAlchemy + APScheduler + DataGuardian
- 数据库：MySQL 8.0
- 数据源：akshare + yfinance（入库缓存，TTL 防重复抓取，10 年回填）
- 前端：React 18 + Vite
- 部署：Docker Compose（Win/Linux/Mac 统一）

## 文档

- [产品规格](dca-dashboard-spec.md)
- [定投手册](纳指100_红利低波_组合定投手册.md)
- [定时检查清单](定时检查执行清单.md)
