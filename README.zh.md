![Hetzner-Web](docs/brand-logo.svg)

[English](README.md) | [中文](README.zh.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE.md)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED)](#快速开始)

一个轻量的 Hetzner 流量控制台 + 自动化监控工具。支持可视化仪表盘、Telegram 通知/命令、自动重建、DNS 检查。

## 目录

- [快速开始](#快速开始)
- [界面截图](#界面截图)
- [亮点功能](#亮点功能)
- [使用场景](#使用场景)
- [安装方式](#安装方式)
- [环境要求](#环境要求)
- [配置设置](#配置设置)
- [配置文件位置](#配置文件位置)
- [排错指南](#排错指南)
- [项目结构](#项目结构)
- [GitHub 协作规范](#github-协作规范)
- [常见问题](#常见问题)
- [安全说明](#安全说明)

---

<a id="快速开始"></a>
## ![Start](docs/icon-start.svg) 快速开始

使用全自动一键脚本，一次性装好 Web 控制台 + 流量监控 + Telegram 支持。

```bash
curl -fsSL https://raw.githubusercontent.com/liuweiqiang0523/Hetzner-Web/main/scripts/install-all.sh | sudo bash
```

然后继续看「配置设置」。

![安装流程](docs/quickstart-flow.light.svg)

---

<a id="界面截图"></a>
## ![Camera](docs/icon-camera.svg) 界面截图

![Web 控制台](docs/web2.png)
![Telegram 机器人](docs/telegram2.png)

---

<a id="亮点功能"></a>
## ![List](docs/icon-list.svg) 亮点功能

![Feature Cards](docs/feature-cards.svg)

---

<a id="使用场景"></a>
## ![List](docs/icon-list.svg) 使用场景

![Use Cases](docs/use-cases.svg)

更适合「流量可视化优先 + 自动化辅助 + 随时手动控制」的场景。
常见用法：流量封顶告警、夜间删建机、Telegram 随时操作。

---

<a id="安装方式"></a>
## ![Install](docs/icon-install.svg) 安装方式

推荐使用一键安装脚本（Docker 模式）：

```bash
curl -fsSL https://raw.githubusercontent.com/liuweiqiang0523/Hetzner-Web/main/scripts/install-all.sh | sudo bash
```

默认不会影响已有部署。如果你要更新已有安装：

```bash
curl -fsSL https://raw.githubusercontent.com/liuweiqiang0523/Hetzner-Web/main/scripts/install-all.sh | sudo ALLOW_UPDATE=1 bash
```

---

<a id="环境要求"></a>
## ![Check](docs/icon-check.svg) 环境要求

先确认这些命令可用：

```bash
git --version
docker --version
docker compose version
```

如果缺少，请先安装（Ubuntu/Debian 可用 apt）。

---

<a id="配置设置"></a>
## ![Config](docs/icon-config.svg) 配置设置

所有的配置现在统一在根目录的 `config.yaml` 中完成。

**核心配置项：**
- `hetzner.api_token`：填写你的 Hetzner API Token
- `web.username` / `web.password`：Web 登录凭证（默认 admin / CHANGE_ME，**必须修改**）
- `telegram.bot_token` / `telegram.chat_id`：Telegram 机器人设置

**可选调优：**
- `cloudflare.update_retries`：DNS 更新重试次数
- `qbittorrent.instances`：qBittorrent 统计实例配置
- `report_state.json` 每日备份到 `report_state_backups/`（仅保留最近 3 份）

**应用配置：**

```bash
cd /opt/hetzner-web
docker compose up -d --build
```

打开：`http://<你的服务器IP>:1227`

---

<a id="配置文件位置"></a>
## ![Map](docs/icon-map.svg) 配置文件位置

![配置文件速查](docs/config-files.light.svg)

- **主配置文件**：`/opt/hetzner-web/config.yaml`
- **运行状态**：`/opt/hetzner-web/report_state.json`
- **环境变量示例**：`/opt/hetzner-web/.env.example`

---

<a id="排错指南"></a>
## ![Tools](docs/icon-tools.svg) 排错指南

![排错流程](docs/troubleshooting-flow.light.svg)

一键自检：
- `docker ps`（确认容器在运行）
- `docker compose logs -f`（查看实时日志）

---

<a id="项目结构"></a>
## ![Layout](docs/icon-layout.svg) 项目结构

- **Web 控制台** (`app/`)：采用模块化 FastAPI 架构
  - `app/main.py`: 程序入口与后台任务生命周期管理
  - `app/api/`: REST API 路由定义
  - `app/services/`: 第三方集成（Hetzner, Telegram, Cloudflare, qBittorrent）
  - `app/tasks/`: 流量监控与自动化调度循环
  - `app/core/`: 核心配置与全局状态管理
  - `app/utils/`: 统计计算与格式化工具集
- **前端界面** (`static/`): Vue 编译后的静态资源
- **脚本工具** (`scripts/`): 一键安装与维护脚本

---

<a id="github-协作规范"></a>
## ![Tools](docs/icon-tools.svg) GitHub 协作规范

仓库已内置基础协作规范：

- CI 工作流：`.github/workflows/ci.yml`
  - push / pull request 自动做 Python 编译检查
- PR 模板：`.github/pull_request_template.md`

建议贡献流程：

```bash
git checkout -b feat/your-change
# 修改代码
python3 -m py_compile app/*.py app/*/*.py
git add .
git commit -m "feat: your change"
git push origin feat/your-change
# 然后在 GitHub 发起 PR
```

---

<a id="常见问题"></a>
## ![List](docs/icon-list.svg) 常见问题

Q：打开不了网页？  
A：先确认 1227 端口放行，再用 `docker ps` 看容器是否在运行。

Q：Telegram 没有消息？  
A：确认 `config.yaml` 里的 `bot_token`/`chat_id` 是否开启，然后运行 `docker compose up -d --build` 重启。

Q：改了配置没生效？  
A：统一运行 `docker compose up -d --build`。

Q：重建后 DNS 还是旧 IP？  
A：Telegram 执行 `/dnsync` 强制同步，或检查 Cloudflare Token 权限。

Q：配置文件在哪里？  
A：全部在 `/opt/hetzner-web/config.yaml`。

---

<a id="安全说明"></a>
## ![Shield](docs/icon-shield.svg) 安全说明

- `config.yaml` 和 `.env` 包含敏感信息，请不要提交到 Git。
- 建议通过 HTTPS 反向代理访问。
