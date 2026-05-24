# Deploy

nanobot Manager 自动化部署脚本，用于在 Ubuntu 服务器上拉取代码、构建、部署。

## 文件说明

| 文件 | 用途 |
|------|------|
| `deploy.sh` | 部署脚本，支持首次初始化和后续更新 |
| `nanobot-manager.service` | systemd 服务模板，由 deploy.sh 自动生成 |

## 首次部署

```bash
# 1. 下载脚本到服务器
scp deploy/* user@server:~/

# 2. 运行初始化
GITHUB_TOKEN=ghp_xxxxxxxxxxxx ./deploy.sh --init
```

自动完成：clone 代码 → 创建 venv → 安装依赖 → 构建前端 → 安装 systemd service。

```bash
# 3. 创建配置文件
nano ~/.nanobot/manager-config.json
```

写入配置（按实际情况修改）：

```json
{
  "manager": { "port": 8080, "adminPassword": "你的密码" },
  "providers": {
    "deepseek": { "apiKey": "sk-xxx" }
  },
  "agentDefaults": { "provider": "deepseek", "model": "deepseek-chat" }
}
```

```bash
# 4. 启动服务
sudo systemctl start nanobot-manager

# 5. 浏览器访问
# http://服务器IP:8080/admin/
```

## 更新部署

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxx ./deploy.sh
```

自动完成：拉取代码 → 更新依赖 → 重建前端 → 重启服务。之前运行的 agent 会自动恢复。

## 切换分支

```bash
BRANCH=main GITHUB_TOKEN=ghp_xxx ./deploy.sh
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `GITHUB_TOKEN` | GitHub PAT（必需，用于访问私有仓库） | - |
| `BRANCH` | 部署的 Git 分支 | `dev` |

## 运维命令

```bash
sudo systemctl status nanobot-manager    # 查看状态
sudo journalctl -u nanobot-manager -f    # 实时日志
sudo systemctl restart nanobot-manager   # 重启服务
sudo systemctl stop nanobot-manager      # 停止服务
```

## 文件位置

| 内容 | 路径 |
|------|------|
| 代码 | `~/nanobot/` |
| 配置 | `~/.nanobot/manager-config.json` |
| 数据库 | `~/.nanobot/manager.db` |
| Agent 配置 | `~/.nanobot/configs/` |
| Agent 工作区 | `~/.nanobot/workspaces/` |

## 自动恢复

Manager 启动时会自动检查数据库中状态为 RUNNING 的 agent 并重新启动，因此以下场景 agent 都会自动恢复：

- 部署更新（systemctl restart）
- 服务器重启
- Manager 进程崩溃
