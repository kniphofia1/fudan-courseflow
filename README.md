# Fudan CourseFlow · 复旦课流

面向复旦 eLearning（Canvas）与 iCourse 的课程资料自动化工具，支持课件增量下载、录课转写和 AI 摘要，按学期与课程统一归档。

**NAS 不是必需条件。** 项目使用 Linux 容器，可在 NAS、普通电脑或 Linux 服务器上部署。

[功能](#功能) · [环境准备](#环境准备) · [初始化与配置](#初始化与配置) · [运行方式](#运行方式) · [维护与排错](#维护与排错) · [隐私与安全](#隐私与安全) · [测试与来源](#测试与来源)

## 功能

- **课件下载**：UIS 自动登录、短期 token 刷新、目标学期识别，保留课程文件夹结构。
- **课程匹配**：基于课程代码、教学班、名称和教师匹配 iCourse 课程，跳过歧义及未开放录播。
- **录课转写**：SenseVoice Small INT8 + sherpa-onnx + Silero VAD，本机 CPU 识别，默认中文主导，保留英文术语。
- **资料归档**：流式处理音频，不保存音视频文件；输出完整转写与 AI 摘要 Markdown。
- **增量处理**：独立学期进度、互斥锁与失败重试；目标学期未发布时等待，不回退至旧学期。

输出示例：

```text
26-27秋学期/
└── CS99999.01 示例课程/
    ├── 讲义/
    │   └── chapter-1.pptx
    └── 录课转写/
        ├── README.md
        └── 2026-09-01_123456_课次标题.md
```

普通电脑运行时直接保存到本地；NAS 或服务器上的文件可通过 SFTP 或自行配置的 Syncthing 获取。本项目不提供 Web 管理界面，不需要开放公网端口或配置反向隧道。

## 环境准备

需要 Git、Python 3、Compose v2、支持 Linux 容器的 Docker 环境，以及可访问目标课程的复旦 UIS 账号。无需 GPU；运行设备需能访问学校认证、课程平台、模型服务和依赖下载站点。

| 环境 | Docker 环境 | 命令执行位置 |
|---|---|---|
| Linux NAS / 服务器 / 桌面 | Docker Engine + Compose | 设备终端，用户需有 Docker 权限 |
| macOS | 已启动的 [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) | 终端 |
| Windows | [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) + WSL2 Linux 发行版，启用 [WSL Integration](https://docs.docker.com/desktop/features/wsl/) | WSL 终端，非 PowerShell；Git 和 Python 安装在 WSL 内 |

Windows 使用 Linux 容器模式，不提供原生 Windows Python 运行方案。已完成 NAS 运行验证；桌面配置复用相同容器，尚未逐平台、逐架构完成端到端转写验证。

安装后检查：

```sh
docker info
docker compose version
git --version
python3 --version
```

首次构建需下载镜像、Python/Rust 依赖和模型，磁盘占用不限于最终文档。长录课的 CPU 转写可能耗时较久；流式读取仍消耗网络流量，云服务器需考虑带宽和模型服务额度。

## 初始化与配置

### 1. 初始化

以下命令在实际运行设备上执行。克隆后保持在仓库根目录：

```sh
git clone https://github.com/kniphofia1/fudan-courseflow.git
cd fudan-courseflow
python3 scripts/init_local.py --semester 2026-fall --credentials
mkdir -p downloads/2026-fall
(cd downloads/2026-fall && pwd)
```

脚本通过隐藏输入读取 UIS 凭据，保存到 `secrets/`，并创建 `.env` 和私有运行目录；不会覆盖已有文件。

将最后输出的绝对路径填入 `.env` 的 `COURSE_OUTPUT_DIR`，也可使用其他提前创建的本学期目录：

- **macOS**：Docker Desktop 若提示访问权限，需允许挂载仓库和输出目录。
- **Windows/WSL2**：仓库、`.runtime/` 和 `secrets/` 放在 WSL Linux 文件系统中，以保留权限和锁语义。使用 `pwd` 返回的 Linux 路径，不填 Windows 盘符路径；在输出目录执行 `explorer.exe .` 可通过 Windows 文件资源管理器访问。
- **Linux / NAS**：确认输出目录可写。服务器部署时，此路径属于服务器，不是本地电脑。

不要填写 `~`、`/absolute/path/...` 占位值或其他设备上的路径。

### 2. 编辑配置

`.env` 由 Compose 读取，无需 `source .env`。

| 配置项 | 说明 |
|---|---|
| `COURSE_OUTPUT_DIR` | 本学期输出目录的绝对路径 |
| `SEMESTER_KEY` | 本地学期标识，须与初始化的 `--semester` 一致 |
| `CANVAS_TARGET_TERM_NAME` | eLearning 中完整的学期名称，Canvas 数字 Term ID 自动识别 |
| `ICOURSE_TERM_ID` | 经平台核验的 iCourse 学期 ID |
| `DASHSCOPE_API_KEY` | 录课处理必填的 **ModelScope** 推理 API key，并非阿里云 DashScope key |
| `GEMINI_API_KEY` | 可选；配置后优先使用 Gemini 生成摘要 |
| `SMTP_EMAIL` / `SMTP_PASSWORD` / `RECEIVER_EMAIL` | 可选邮件通知；SMTP 密码使用邮件服务授权码，不使用时留空 |
| `ICOURSE_RUN_TIMES` | 录课调度时间，默认 `13:00,22:00` |
| `SENSEVOICE_LANGUAGE` | 默认 `zh`，中文主导并保留英文术语 |
| `SKIP_MODEL_DOWNLOAD` | 首次部署保持 `false`；模型已准备好时可设为 `true` |

ModelScope key 在 [访问令牌页面](https://modelscope.cn/my/myaccesstoken) 获取。当前代码即使配置 Gemini，也仍要求填写 ModelScope key。部署前检查 `icourse/src/config.py` 中的 `LLM_MODELS` / `GEMINI_MODELS`，可用模型及额度以服务商为准。

学期默认值以 2026–2027 秋学期为例，不适用于其他学期。核验 iCourse 学期 ID：

1. 登录 iCourse 课程列表，打开浏览器开发者工具的 Network 面板。
2. 切换目标学期，筛选 `get-course-list` 请求；当前接口为 `/portal/courseapi/v3/multi-search/get-course-list`。
3. 将请求参数中的 `term` 填入 `ICOURSE_TERM_ID`。它不是课程详情 URL 中的 `course_id`，也不是 Canvas 的 Term ID。

若平台接口变化，应重新核验，不能猜测 ID。不要公开 cookie、请求认证头或完整网络记录。

### 3. 可选：补充课程名单

Canvas 尚未发布而 iCourse 已开放时，可使用自己核验过的课程名单：

1. 参考 [示例 JSON](examples/confirmed-courses.example.json)，将实际信息保存到 `.runtime/icourse/<SEMESTER_KEY>/confirmed-courses.json`，权限设为 `0600`。
2. `icourse_id` 取自课程详情 URL 的 `course_id`；代码、名称和教师取自同一页面；名单的 `term_id` 与配置一致。
3. 在 `.env` 中设置容器内路径：

```dotenv
CONFIRMED_COURSES_PATH=/app/data/confirmed-courses.json
```

示例数据不能直接用于运行。程序会核对名称、教师，并与后来发布的 Canvas 清单合并；审核中、延迟发布或已过开放期限的录播仍会跳过。

## 运行方式

### 手动运行

适用于普通电脑，或首次验证。完成配置后执行：

```sh
chmod 600 .env secrets/fudan_username secrets/fudan_password
docker compose config --quiet
docker compose --profile manual build
sh scripts/run-canvas.sh
sh scripts/run-icourse-once.sh
```

顺序运行：先同步课件和课程清单，再处理录课。Canvas 自动刷新 token，iCourse 首次运行自动下载模型；不要同时启动多个录课容器下载模型。

首次会处理目标学期当前可访问的课件，以及成功匹配课程中所有已开放、未处理的录播，并非仅当天内容。后续只需重复执行两个 `sh` 命令。

临时容器完成后自动移除，文件和进度保留；输出和报错显示在当前终端。手动录课任务默认不发送邮件，不会改变已有定时时间。

### 只下载课件

完成 UIS 凭据、学期和输出目录配置后，仅执行：

```sh
docker compose build canvas
sh scripts/run-canvas.sh
```

不启动 iCourse，无需模型 key，也不下载 ASR 模型。

### 定时运行

适合常在线的 NAS、服务器或电脑。首次手动任务完成后启动录课调度：

```sh
docker compose up -d icourse
```

容器启动后等待下一次调度，**不会立即转写**。若直接启动常驻服务，应等待日志出现 `Next run at ...` 后再追加手动任务，避免首次模型下载重叠。

| 任务 | 默认时间 | 调度方式 |
|---|---|---|
| eLearning | 07:00、19:00 | 宿主机计划任务，需自行配置 |
| iCourse | 13:00、22:00 | 容器内置调度，由 `ICOURSE_RUN_TIMES` 配置 |

Canvas 计划任务执行以下命令，替换实际仓库路径：

```sh
sh /absolute/path/to/fudan-courseflow/scripts/run-canvas.sh
```

NAS 使用计划任务界面；Linux 可用 cron / systemd timer；macOS 可用 launchd；Windows 可用任务计划程序调用 WSL 中的脚本。任务环境需能找到 Docker、具备 Docker 权限，并使用正确的 WSL 发行版（如适用）。宿主机与容器时区保持 `Asia/Shanghai`。

本项目不自动安装宿主机计划任务，也不会唤醒电脑。运行期间保持开机、联网且 Docker 可用；退出 Docker Desktop 后任务无法继续执行。不要依赖错过时刻自动补跑，需要时手动同步。进度按已保存阶段复用，不支持按音频秒数续转，中断的未保存课次可能需要重新识别。

## 维护与排错

### 检查结果

```sh
docker compose ps
docker compose logs --tail 80 icourse
```

- **Canvas**：应显示目标学期、下载结果或明确的 `pending`。一次性容器完成后不出现在 `ps` 中是正常情况。
- **iCourse**：常驻容器应在运行，日志包含下一次调度时间；导出成功出现 `[Markdown] Exported`。运行状态或退出码为 0 不代表所有课程成功，仍需查看错误和跳过原因。
- **输出**：课件在 `COURSE_OUTPUT_DIR/<课程目录>/`，转写在其下的 `录课转写/`。远程部署还需检查文件同步是否完成。

### 数据与日志

| 宿主机路径 | 内容 |
|---|---|
| `.runtime/canvas/<SEMESTER_KEY>/` | token、浏览器会话、锁、`sync.log` 及 `log/` 下载记录 |
| 其下 `.state/semester-courses.json` | Canvas 课程清单，供 iCourse 只读使用 |
| `.runtime/icourse/<SEMESTER_KEY>/` | SQLite、课程映射、确认名单、任务锁 |
| `.runtime/models/` | SenseVoice 与 Silero VAD 权重 |
| `secrets/` | 两任务共用的 UIS 凭据 |
| `COURSE_OUTPUT_DIR` | 本学期课件和 Markdown |

相对路径以仓库根目录为准。容器默认以 root 运行，部分运行文件可能为 root 所有；不要用 `chmod -R 777` 解决权限问题。模型应包含 SenseVoice 目录中的 `model.int8.onnx`、`tokens.txt`，以及模型根目录的 `silero_vad.onnx`。

不要删除运行目录重试任务。备份至少包括学期数据库、私有配置和课程输出；SQLite 需停写后备份或使用一致性备份方式。手动录课临时容器的日志在执行终端查看，不会保留在常驻容器日志中。

### 修改配置与停止任务

等待当前任务结束后再操作：

```sh
docker compose up -d icourse                   # 应用 .env 修改，或恢复服务
docker compose up -d --build icourse           # 应用代码或模型列表修改
docker compose up -d --force-recreate icourse  # 更新 secret 文件后重新创建
docker compose stop icourse                   # 停止录课调度
```

以上按需要执行，不必依次运行。仅 `restart` 不会应用新的环境配置。初始化脚本不覆盖已有配置或凭据，更新密码需编辑 secret 文件；Canvas 下次临时运行会读取最新配置。停止或恢复 Canvas 自动任务需在宿主机计划任务中另行操作。

### 常见问题

| 现象 | 检查项 |
|---|---|
| Canvas `pending` / 只有部分课程 | 学期名称是否完整、课程是否对账号发布；不要改用旧学期 ID |
| iCourse 无匹配或审核中 | 核对学期、课程代码和教师，等待平台开放；需要时补充确认名单 |
| token 401 / UIS 登录失败 | 使用正常入口刷新 token；核对密码和账号状态，不要公开 token |
| 模型缺失 | 首次使用 `SKIP_MODEL_DOWNLOAD=false`，检查下载网络和权重路径 |
| 摘要 `unavailable` / `timeout` | 核对服务商模型、权限、额度和网络；修改模型列表后重建 |
| 已转写但没有 Markdown | 当前导出依赖摘要成功，转写仍在数据库，后续重试跳过 ASR |
| NAS 有文件、电脑没有 | 检查自己配置的 Syncthing 或其他文件同步工具 |

### 换学期与迁移

换学期前暂停旧计划任务并备份配置、进度；设置新的 `SEMESTER_KEY`、输出目录和确切学期，运行 `python3 scripts/init_local.py --semester <new-key>`，再自行修改已有 `.env`。新学期使用独立数据库、映射和确认名单，模型可复用。先手动验证，再恢复调度，旧学期资料不删除。

从原来的两个仓库迁移时，顶层 Compose 项目名和目录不同，不能直接再开一套。待旧任务结束、停写并备份后，统一核对数据库、任务锁、映射、确认名单与输出目录，再选择复用挂载或迁移进度。旧清单可能名为 `2026-fall-courses.json`，这里使用 `semester-courses.json`，路径和环境变量必须一致。

验证无重复处理后再切换计划入口，保留旧部署以便回滚；任意时刻只保留一组调度器。仓库不提供自动清空或覆盖数据库的迁移脚本。

## 隐私与安全

- **本地转写，云端摘要**：ModelScope / Gemini 会接收课程标题和转写内容；可选 SMTP 会发送笔记，邮件公式渲染可能请求第三方图片服务。使用前确认课程内容允许这样处理。
- **识别结果需核对**：中文模式不是严格词表限制，噪声和专业术语仍可能误识别。音频连续三次接收不完整后可能保留部分结果，应检查完整性警告。
- **功能限制**：当前 Markdown 自动导出依赖摘要完成，不能留空 API key 直接作为纯转写模式使用；只处理有权访问的课程文件和已开放录播，不提供完整 LMS 备份。
- **私有数据不上传**：凭据、token、cookie、API key、SMTP 授权码、SSH 配置、课程名单、Manifest、数据库（包括加密备份）、课件、转写及运行日志均不应进入公开仓库。
- **权限与日志**：私有文件用 `0600`、目录用 `0700`，只向可信管理员授予 Docker 权限。`.gitignore` 和自动扫描不能替代人工检查；第三方报错可能包含带签名地址，不要直接公开完整日志。
- **泄露处理**：先吊销或轮换凭据；删除文件不能撤回公开历史。安全问题请通过维护者可用的私下渠道沟通，不在公开 Issue / PR 粘贴敏感内容。

本项目不对外开放端口，不包含 NAS 管理入口。模型权重首次从分发站点下载；学校登录和媒体读取使用账号已有权限，不用于绕过平台访问控制。

## 测试与来源

组件测试需安装各自的 `requirements.txt`：

```sh
python3 -m unittest discover -s tests -v
(cd canvas && python3 -m unittest discover -s tests -v)
(cd icourse && python3 -m unittest discover -s tests -v)
```

以上测试在 Linux 环境执行；Windows 使用 Linux 容器或 WSL。Canvas 的真实 Rust 集成测试还需设置 `CANVAS_TEST_BINARY` 为已构建程序的绝对路径。

2026-09-10 整理发布时，Canvas 11 项、iCourse 23 项、部署脚本 4 项，共 38 项测试通过；组件在禁网容器中使用模拟数据测试，另通过 Compose 校验和 Gitleaks 密钥扫描。[Actions 模板](ci/tests.yml.example) 尚未启用，需使用有工作流写入权限的凭据保存为 `.github/workflows/tests.yml`。CI 不运行学校登录或真实课程同步。

源码由以下 NAS 运行提交按白名单导入，未带入 Git 历史、课程数据、旧前端、字体或旧定时工作流：

| 组件 | 来源提交 |
|---|---|
| Canvas | [2255e89](https://github.com/kniphofia1/canvas-downloader/tree/2255e89d2a28fcc1d3c64db90f887c4f4f7bea2d) |
| iCourse | [09c42ac](https://github.com/kniphofia1/Fudan_iCourse_Subscriber/tree/09c42acf3cdf1c0ee7218b455ee80e19ba866c20) |

整理保留核心逻辑和测试、清理行尾空白，新增统一 Compose、初始化及运行入口；Canvas 锁移入共享持久化目录。现有 NAS 服务未因公开仓库发布而自动迁移。

感谢上游作者 [bnjmnt4n](https://github.com/bnjmnt4n/canvas-downloader)、[LeafCreeper](https://github.com/LeafCreeper/Fudan_iCourse_Subscriber)，以及 [SenseVoice](https://github.com/FunAudioLLM/SenseVoice)、[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)、[Silero VAD](https://github.com/snakers4/silero-vad) 项目。

本项目非学校官方项目。来源仓库未提供明确的根 LICENSE，因此未添加统一许可证；公开可见不等于统一授予开源许可，复用与分发前请核实上游授权，依赖和模型遵循各自许可。
