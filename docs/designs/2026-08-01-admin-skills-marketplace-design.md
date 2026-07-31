# Admin Skills Marketplace 设计

- **日期**: 2026-08-01
- **状态**: 待 review
- **范围**: `webui-manager/`（前端）+ `nanobot/manager/`（后端）+ 上游 `skills_marketplace.py` 移植

## 背景与目标

当前 manager 后台的 skills 体系是**纯本地**的：agent 的 skills tab 扫描包内只读目录 `nanobot/manager-skills/`，安装就是把目录 symlink 到 agent workspace。没有「市场」概念——只能用打包进仓库的那几个预置 skill。

上游 HKUDS/nanobot 在主 WebUI 里做了 skills marketplace（PR #5116），支持从 skills.sh / SkillHub 浏览搜索 + 下载安装第三方 skill，但它是**终端用户视角、per-workspace 安装**，与本仓库的 manager 后台架构不同。

**目标**：在 manager 后台为**超级管理员**增加一个全局 skills 市场（Discover + Installed），admin 从远程源发现并下载 skill 进**全局仓库**；全局仓库成为所有 agent skills tab 的唯一可选来源，agent 仍按现有 symlink 机制选装到自己 workspace。

## 架构总览

```
AdminPage (webui-manager)              ← 新增 skills tab
  ├─ Discover ──搜索/trending──> skills.sh + SkillHub
  └─ Installed ──管理──> 全局仓库

全局仓库 ~/.nanobot/manager-skills/    (唯一源, admin 可写)
        ↓ scan_available_skills 扫这里

AgentDetailPage skills tab (现有, 逻辑不变)
  └─ 列出全局仓库 skill → 点安装 → symlink 到 workspace/skills/
```

**关键边界**：
- 市场仅 admin 可用；agent 侧只消费全局仓库，不直接访问远程源。
- 全局仓库是 agent 可选 skill 池的**唯一来源**；不再保留/扫描内置 `nanobot/manager-skills/`（含 alphaear-*）。
- admin 装进全局仓库 ≠ agent 立即生效；agent 仍需点「安装」symlink 到自己 workspace（复用现有机制）。

## 后端组件

### 移植 / 新增

| 文件 | 来源 | 说明 |
|------|------|------|
| `nanobot/manager/services/skills_marketplace.py` | 上游 `nanobot/webui/skills_marketplace.py`（938 行） | 搜索 / trending / SkillHub 下载+校验逻辑**原样复用**；`install_marketplace_skill` 改为下载到**全局仓库**而非 per-workspace |
| `PinnedDNSAsyncTransport` | 上游 `nanobot/security/network.py` | 移植到本仓库 `security/network.py`，提供 pinned-DNS HTTP 传输（SSRF 防护） |
| `nanobot/manager/api/marketplace.py` | 新增 | admin 市场端点（或并入现有 admin router） |

**移植要点**：
- 上游依赖 `agent/skills.py` (SkillsLoader)、`security/workspace_policy.py` (require_path_within)、`httpx` —— 本仓库均已具备。
- 唯一缺失依赖 `PinnedDNSAsyncTransport` —— 一并移植，不降级为普通 httpx。
- `install_marketplace_skill` 改造：去掉 `workspace_path` 语义，改为写入全局仓库目录。skills.sh 源仍走 `npx` 官方 CLI（`_CLI_AGENT="openclaw"`，服务器已具备 node v22 / npx）；SkillHub 源走 httpx 下载 zip + 签名校验 + 解压。
- well-known hostname 源（uizze.com 等，PR #5186）随 `skills_marketplace.py` 整体移植自动带，不单独处理。

### 改造现有

`nanobot/manager/services/skills.py`：
- `MANAGER_SKILLS_DIR` 从包内 `nanobot/manager-skills/` 改为由 `ManagerConfig.data_dir` 派生的全局仓库路径：`data_dir / "manager-skills"`（即 `~/.nanobot/manager-skills/`）。
- `scan_available_skills / install_skill / uninstall_skill` 全部指向全局仓库。
- `install_skill` 仍是 symlink 全局仓库 → agent workspace（源换了，逻辑不变）。
- 全局仓库路径作为参数从 config 注入（API 层已能拿到 `get_config()`），不在模块内硬编码。

`nanobot/manager/api/agents.py`：
- `/skills/available`、`/skills/install`、`/skills/uninstall` 调用点传入全局仓库路径，行为不变。

## API 端点（均走 `get_current_admin`）

| 方法 | 路径 | 作用 |
|------|------|------|
| GET | `/api/admin/skills/marketplace/search?q=&source=` | 搜索（source: all/skills_sh/skillhub） |
| GET | `/api/admin/skills/marketplace/trending?source=` | 热门列表 |
| POST | `/api/admin/skills/marketplace/install` | 下载装到全局仓库（body: `{skillId, source}`） |
| GET | `/api/admin/skills` | Installed 页：列全局仓库已装 skill |
| DELETE | `/api/admin/skills/{name}` | 从全局仓库卸载（连带清理，见下） |

## 数据流

### admin 安装一个市场 skill
1. admin 在 Discover 搜索 → search API（httpx + PinnedDNS 查 skills.sh/SkillHub）→ 卡片列表。
2. 点「安装」→ POST install → 后端按 source 分派：
   - skills.sh：`npx` 官方 CLI 拉取
   - SkillHub：httpx 下 zip + 签名/指纹校验 + 解压
3. 归档校验（路径穿越 / 包大小 / 指纹）通过 → 落到 `~/.nanobot/manager-skills/<name>/`。
4. Installed 列表刷新。

### agent 选装
agent 的 skills tab 调 `/skills/available`（现扫描全局仓库）→ 看到该 skill → 点安装 → symlink 到 `workspace/skills/`（现有逻辑）。

## 卸载断链处理（决策 5a：连带清理）

admin 卸载全局仓库某 skill 时，已被若干 agent symlink 使用的会变断链。

**策略**：卸载时先遍历 `config.workspaces_dir` 下所有 agent workspace，删除各自 `skills/` 目录下指向该 skill 的 symlink，再删除全局仓库里的 skill 目录。

- 实现：`uninstall_global_skill(name)` 内部：① 扫所有 workspace 清 symlink → ② 删全局仓库目录。两步都要做，① 失败不阻止 ②（断链本就无效）。
- 符合「全局管理」语义，admin 一次操作到底。

## 前端 UI（决策 6a：子 tab 切换）

`AdminPage` 现有 `agents` / `users` 两个 tab，新增第三个 `skills` tab。skills tab 内顶部 `Discover` / `Installed` 两个子按钮切换（复用现有 tab 按钮风格）。

- **Discover**：搜索框 + 源过滤（全部 / skills.sh / SkillHub）+ trending 区 + 结果卡片（名字 / 描述 / 来源 / 安装按钮，已装置灰）。安装走 loading 态。
- **Installed**：全局仓库已装 skill 列表（卡片或行表）+ 卸载按钮（二次确认）。

沿用现有 Tailwind + shadcn 组件（`Button` / `Input` 等）与 `useI18n`。新增组件建议：`webui-manager/src/components/SkillsMarketplace.tsx`、`SkillsInstalled.tsx`（或合一个文件带子视图）。

## 安全

- 移植上游全套校验：归档路径穿越检查、包大小上限、SkillHub 签名/指纹校验。
- `PinnedDNSAsyncTransport` 提供 SSRF 防护（pinned DNS，拒绝解析到内网）。
- 第三方 skill 含可执行代码——执行风险靠上述下载校验 + agent 现有 workspace 沙箱隔离兜底。
- 市场接口仅 admin（`get_current_admin`）可调；下载/卸载需显式操作。

## i18n

`webui-manager/src/i18n/en.ts`、`zh.ts` 补 marketplace 相关 key（搜索 / 安装 / 卸载 / 源过滤 / trending / 确认卸载提示等）。

## 测试策略

**后端**（`tests/manager/`）：
- 搜索/trending：mock httpx 响应，验证 skills.sh/SkillHub 结果解析与源过滤。
- 安装：mock 下载，验证解压到全局仓库 + 校验逻辑（含恶意路径穿越用例拒绝）。
- 卸载断链：构造多个 agent workspace 的 symlink，验证连带清理。

**前端**（`webui-manager` 现有测试模式）：
- Discover 搜索 / 源过滤 / 安装按钮状态（安装中 / 已装置灰）。
- Installed 列表渲染 / 卸载二次确认。

## 范围（YAGNI — 明确不做）

- ❌ per-agent 市场（市场仅 admin 全局）。
- ❌ `$skill-name` 输入补全（webui-manager 是管理后台，非聊天界面）。
- ❌ 保留/扫描内置 `nanobot/manager-skills/`（alphaear-* 不再作为预置源）。
- ❌ 非 admin 用户访问市场。
- ❌ 自定义/上传 skill（首版只接远程两个源；管理员手动添加留待后续）。

## 上游移植清单

从 `HKUDS/nanobot` main（分叉点 `2144af7c` 之后）移植：
1. `nanobot/webui/skills_marketplace.py` → `nanobot/manager/services/skills_marketplace.py`（install 目标改全局仓库）
2. `PinnedDNSAsyncTransport`（`security/network.py` 的相关部分）
3. 上游 `tests/webui/test_skills_marketplace.py` 的核心用例（适配到 manager 层）

**移植风险**：
- **路由耦合**：上游 `skills_marketplace.py` 与主 webui 的 `skills_api.py` / `ws_http.py` 路由耦合——本设计在 manager 层重写路由（`api/marketplace.py`），只搬服务层逻辑，规避路由耦合。
- **skills.sh CLI 目标目录（需实现阶段先验证）**：skills.sh 源的安装走 `npx` 官方 skills CLI，上游默认把 skill 拷进 `<workspace>/skills`（per-workspace）。移植为「装到全局仓库」需确认该 CLI 能接受自定义目标目录（或以全局仓库路径作为 workspace 上下文调用）。若 CLI 不支持自定义目标，首版 skills.sh 源降级为「仅搜索/展示」、安装仅走 SkillHub，或对 skills.sh 做额外适配。实现第一步须先跑通 CLI 接口验证。
- **PinnedDNSAsyncTransport 落地**：上游该类位于 `security/network.py`，本仓库 `network.py` 已有自定义改动（+50 行），移植时需合并而非覆盖，避免丢失本仓库既有逻辑。
