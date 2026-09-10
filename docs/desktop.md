# 普通电脑使用指南

没有 NAS 时，可以在自己的电脑上构建并运行相同的 Linux 容器。课件和转写直接保存到本地目录，不需要 Syncthing、公网服务器或反向隧道。

本文提供桌面部署路径；目前项目的完整运行验证来自 NAS，macOS、Windows/WSL2 和不同 CPU 架构尚未逐一完成端到端验证，不保证所有环境均可直接运行。

## 环境准备

| 系统 | 准备工作 | 命令执行位置 |
|---|---|---|
| macOS | Git、Python 3、已启动的 [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) | 终端 |
| Windows | [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)、WSL2 Linux 发行版，并启用对应发行版的 [WSL Integration](https://docs.docker.com/desktop/features/wsl/)；在发行版内安装 Git、Python 3 | WSL Linux 终端，非 PowerShell |
| Linux | Git、Python 3、Docker Engine、Compose v2 | 终端 |

先检查 Docker 可用性：

```sh
docker info
docker compose version
git --version
python3 --version
```

Windows 使用 Linux 容器模式。本文不提供原生 Windows Python 运行方案：现有锁与调度依赖 Linux/Unix 接口，这些代码应在容器内执行。

首次构建需要下载镜像、Python/Rust 依赖和模型，磁盘占用不限于最终 Markdown 文件。无需 GPU；较长录课的 CPU 转写可能耗时较久。Docker 安装要求以官方文档为准，不将其最低配置视为本项目的性能保证。

## 初始化与输出目录

```sh
git clone https://github.com/kniphofia1/fudan-course-nas.git
cd fudan-course-nas
python3 scripts/init_local.py --semester 2026-fall --credentials
mkdir -p downloads/2026-fall
(cd downloads/2026-fall && pwd)
```

把最后输出的**完整绝对路径**填入 `.env` 的 `COURSE_OUTPUT_DIR`，其他配置按 [README 配置表](../README.md#部署) 填写。此目录已被 Git 忽略；也可以指定仓库外的课程目录。不要把 `~`、`/absolute/path/...` 占位值或另一台设备上的路径直接填入配置。

- **macOS**：路径通常位于 `/Users/…`。Docker Desktop 若提示目录访问权限，需允许挂载仓库与输出目录。
- **Windows/WSL2**：在 WSL 的 Linux 用户目录内克隆仓库，`.runtime/` 与 `secrets/` 保留在 Linux 文件系统中，以维持权限和锁语义。输出同样可使用上述 `pwd` 返回的 Linux 路径；不要填写 `C:\…`。在输出目录执行 `explorer.exe .` 可从 Windows 文件资源管理器访问文件。
- **Linux**：确认用户有 Docker 权限，且输出目录可写。

WSL 文件系统和挂载建议参见 [Docker WSL2 文档](https://docs.docker.com/desktop/features/wsl/)。不同架构的镜像与依赖是否可用，以实际构建结果为准；本文不默认强制模拟其他 CPU 架构。

## 手动运行

适合只在需要时下载或转写的用户，不启动常驻调度器。

完成 `.env` 配置后执行：

```sh
chmod 600 .env secrets/fudan_username secrets/fudan_password
docker compose config --quiet
docker compose --profile manual build
sh scripts/run-canvas.sh
sh scripts/run-icourse-once.sh
```

两个命令顺序执行：先生成课件及课程清单，再处理可匹配的录课。首次手动录课任务会下载模型；不要同时再启动一个录课容器。eLearning 未发布时需等待，或配置自己核验过的课程确认名单，方法见 README。

后续只需保持 Docker 运行，再执行：

```sh
sh scripts/run-canvas.sh
sh scripts/run-icourse-once.sh
```

任务结束后临时容器自动移除，文件和进度仍保留。手动录课任务默认不发送邮件；模型 API key 仍是必需配置。输出和报错直接显示在当前终端。

### 只下载课件

完成 UIS 凭据、学期和输出目录配置后，可仅构建、运行 Canvas：

```sh
docker compose build canvas
sh scripts/run-canvas.sh
```

不需要模型 key，也不下载 ASR 模型或启动 iCourse。

## 常驻运行与休眠

如需常驻录课调度，可在首次手动运行完成后执行：

```sh
docker compose up -d icourse
```

iCourse 按 `.env` 中的 `ICOURSE_RUN_TIMES` 调度；Canvas 仍需宿主机另行安排任务，或手动运行：

- Linux 可使用 cron / systemd timer。
- macOS 可使用 launchd；执行环境需能找到 Docker，且 Docker Desktop 已启动。
- Windows 可使用任务计划程序调用 WSL 内的脚本；需指定正确的发行版和仓库路径，并保证 Docker Desktop 与 WSL 可用。

本项目不自动安装这些桌面定时任务，也不会唤醒处于睡眠或关机状态的电脑。退出 Docker Desktop 后容器无法继续执行。不要依赖错过的时刻自动补跑，需要时手动同步；下一次运行会检查当前可用内容，而非仅当天新增内容。

转写期间保持电脑唤醒、网络连接和终端会话。进度按已保存的处理阶段复用，不是按音频秒数断点续传；中途中断时，尚未保存转写的课次可能需要重新识别。

## 使用已有 Linux 服务器

已有常在线服务器时，可直接使用 README 的 Linux 部署流程；输出路径属于服务器，不是本机。文件可通过 SFTP 或自行配置的 Syncthing 获取，无需为了本项目另行购买 NAS。

服务器必须能够访问学校相关接口和媒体资源。视频虽然不落盘，流式读取仍产生网络流量；还需考虑磁盘、CPU、带宽和模型服务额度。无需向公网开放本项目的端口。
