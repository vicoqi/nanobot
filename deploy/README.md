# Deploy

nanobot Manager 自动化部署脚本，用于在 Ubuntu 服务器上拉取代码、构建、部署。

## 文件说明

| 文件 | 用途 |
|------|------|
| `deploy.sh` | 在服务器拉取远程 `dev` 分支、构建 WebUI 并部署 |
| `nanobot-manager.service` | systemd 服务模板，由 deploy.sh 自动生成 |

## 首次部署

```bash
# 1. 拉取 dev 分支
git clone --branch dev --single-branch https://github.com/vicoqi/nanobot.git ~/nanobot

# 2. 运行初始化
~/nanobot/deploy/deploy.sh --init
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
cd ~/nanobot
./deploy/deploy.sh
```

自动完成：拉取代码 → 更新依赖 → 重建前端 → 重启服务。之前运行的 agent 会自动恢复。

如果要更新指定分支，例如 `main`：

```bash
cd ~/nanobot
BRANCH=main ./deploy/deploy.sh
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `REPO_URL` | Git 仓库地址；私有仓库可改用 SSH 地址 | `https://github.com/vicoqi/nanobot.git` |
| `GITHUB_TOKEN` | GitHub PAT（仅私有 HTTPS 仓库需要） | - |
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
