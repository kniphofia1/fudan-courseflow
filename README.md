# Fudan CourseFlow

面向复旦 eLearning（Canvas）与 iCourse 的课程资料自动化工具，支持课件增量下载、录课转写和 AI 摘要，按学期与课程统一归档。

项目源于实际课程学习中的长期使用需求，在现有课件下载与录课处理工具的基础上，补充复旦认证适配、跨平台课程关联和持久化调度，将分散的同步流程整合为统一的课程资料工作流。

**NAS 不是必需条件。** 项目使用 Linux 容器，可在 NAS、普通电脑或 Linux 服务器上部署。

> [!IMPORTANT]
> 本项目为非官方的个人学习辅助工具，仅用于已获授权的课程资料整理与复习。能够登录或播放不等于获得下载、转写、上传第三方或传播的许可；部署前请阅读下方[使用声明](#使用声明)。

> [!WARNING]
> 请勿在树洞、班级群或其他大型群组中大规模推广自动抓取用途，也不要组织批量部署、共享账号或集中抓取。请控制请求频率，避免影响教学平台的正常服务。

> [!CAUTION]
> 语音识别在本地运行，但 AI 摘要会将课程标题和转写文本发送至第三方模型服务。凭据文件、运行数据库与导出的笔记并非加密存储，不应上传到公开仓库或公开网盘。

[功能](#功能) · [项目改造与贡献](#项目改造与贡献) · [使用声明](#使用声明) · [新用户使用流程](#新用户使用流程) · [环境准备](#环境准备) · [初始化与配置](#初始化与配置) · [运行方式](#运行方式) · [维护与排错](#维护与排错) · [隐私与安全](#隐私与安全) · [测试与来源](#测试与来源) · [许可证](#许可证)

## 功能

- **课件下载**：在原有下载器之上增加复旦 UIS 自动登录、短期 token 刷新与目标学期识别，保留课程文件夹结构。
- **课程匹配**：基于课程代码、教学班、名称和教师匹配 iCourse 课程，跳过歧义及未开放录播。
- **录课转写**：SenseVoice Small INT8 + sherpa-onnx + Silero VAD，本机 CPU 识别，默认中文主导，保留英文术语。
- **资料归档**：流式处理音频，不保存音视频文件；输出完整转写与 AI 摘要 Markdown。
- **增量处理**：独立学期进度、互斥锁与失败重试；目标学期未发布时等待，不回退至旧学期。

每次运行时，Canvas 更新目标学期的课程清单并下载新增或更新的课件；iCourse 根据清单及人工确认名单检查已开放的录播，依次完成音频流读取、语音识别、AI 摘要与 Markdown 归档。定时任务可选邮件通知，手动单次转写默认不发送邮件。

本仓库采用 Docker 部署，不提供上游 V2 的 GitHub Actions 课程同步、PPT OCR、多 ASR 后端、加密分片数据库或 GitHub Pages 查看器。下文配置以本仓库实际实现为准，不可直接套用上游 V2 的 Secrets 和升级流程。

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

## 项目改造与贡献

本项目的主要工作是围绕实际使用场景进行平台适配、流程整合与部署工程化，保留上游下载和录课处理能力，并补齐长期运行所需的认证、配置、调度与归档环节。

### 认证适配与 token 刷新

实际使用中发现，Canvas 访问 token 存在过期或失效的情况，依赖静态 token 的定时任务会因此中断。为减少人工维护，本项目增加了基于复旦 UIS 单点登录的 token 获取、有效性校验与自动刷新机制，在每次同步前更新短期访问凭据，再调用原有 Rust 下载器执行增量下载。

该改造保留了上游的文件下载逻辑，将认证维护从手工配置纳入运行流程；同时补充凭据文件隔离、日志脱敏与私有临时配置清理。自动刷新不能替代有效的 UIS 凭据，也不能绕过账号风控或平台权限限制。

### 跨平台联动与长期运行

| 实际需求 | 本项目新增或改造 |
|---|---|
| 新学期开始后需修改固定学期 ID，容易继续扫描旧课程 | 按 Canvas 学期名称发现真实 ID；目标学期未发布时进入等待状态，并为不同学期隔离进度与输出目录 |
| 课件与录播分属两个平台，需要重复维护课程信息 | 以不含凭据的课程 Manifest 连接 Canvas 与 iCourse，增加课程代码、教学班、名称和教师匹配及映射缓存 |
| Canvas 与 iCourse 的课程发布时间不一致 | 增加人工确认名单，并与后续发布的 Canvas 清单合并，支持提前处理已开放的录播 |
| 录课笔记与课件分散，查找和复习不便 | 增加完整转写、AI 摘要和课次索引的 Markdown 导出，统一归档到课程目录 |
| 脚本需要在 NAS 上持续运行，也需要便于迁移 | 增加 Docker 部署、共享凭据、调度器、互斥锁和进程失败重试，整理统一 Compose 与初始化入口 |
| 平台返回字段与实际课堂信息存在差异 | 修正课次日期解析，补充延迟开放与有效期判断、联合授课教师适配，并增加中文主导的识别配置 |

课程匹配仍需人工核验：当前实现对明确的教学班冲突、人工名单中课程 ID 的真实学期归属校验尚不充分。互斥锁与重试也不代表所有课次失败都能被调度器识别，具体限制见运行检查说明；上述改造不构成完全无人值守的保证。

### 可复用部署与验证

在个人 NAS 部署基础上，进一步整理了不含运行数据的公开代码快照、配置示例、初始化脚本和模拟测试，补充普通电脑与服务器的使用流程，以及 AI 辅助部署和截图整理课程名单的方法。实际运行验证以 NAS 为主，桌面环境的支持范围与限制见下文。

项目由维护者提出需求、组织整合并进行实际使用验证，开发与文档整理使用了 AI 辅助。Canvas Rust 下载器、iCourse 的 WebVPN 访问、流式语音识别、模型摘要及邮件主体来自上游；本项目未自行训练 ASR 或大语言模型，具体来源与授权范围见[测试与来源](#测试与来源)及[许可证](#许可证)。

## 使用声明

本项目仅面向具有相应课程访问权限、且已获得必要处理授权的使用者，用于个人学习、复习和不涉及受保护课程内容的技术交流。不用于替代课堂学习、规避考勤或传播教学资源。

1. **遵守平台与课程要求**：使用前自行确认学校、教学平台的现行使用规范及教师要求。账号可见范围不等同于资源使用授权范围；无法确认是否允许自动下载、转写或云端摘要时，应先取得许可，不要运行相关功能。
2. **不得擅自二次分发**：未经相应权利人许可，不得将课件、录播、转写、摘要、笔记或包含这些内容的数据库转发给他人，或发布到群聊、公开仓库、网盘及其他公共平台。邮件推送和文件同步也应限于本人受控设备与账号。
3. **不得绕过访问限制**：不得借助本项目访问无权查看的课程、绕过录播审核或平台访问控制；不得修改代码进行未经授权的音视频下载、保存、批量采集或商业利用。默认不保存音视频文件不代表无需取得处理许可，也不代表所有衍生文本均可自由使用。
4. **尊重课堂隐私**：录播可能包含教师与同学的姓名、发言及其他个人信息。未经必要授权，不得向模型服务、邮件服务或其他第三方传输这些内容；不要把课堂数据用于公开数据集或模型训练。
5. **合理使用服务**：保留限频、互斥锁和重试间隔，不要部署多套任务重复抓取。出现权限拒绝、认证异常或平台限制时，应停止相关任务并核查原因，不通过更换账号或网络规避限制。

项目不保证持续可用、资料完整或生成内容准确，也不承诺账号不会受到平台限制。使用者应自行评估自动化登录、第三方处理、资源消耗及数据保管风险。项目代码的开源许可不授予任何课程资源的使用权，也不能代替学校或权利人的许可。

## 新用户使用流程

首次使用按以下五步进行，无需 NAS，也不需要 Fork 仓库或提供 GitHub token：

1. **准备环境，选择功能**：在自己的电脑、NAS 或 Linux 服务器上安装 Git、Python 3、Docker 和 Compose。先决定只下载课件，还是同时转写录课；后者还需模型服务 key，并确认允许将转写文本发送到第三方生成摘要。具体环境见[环境准备](#环境准备)。
2. **下载项目，输入账号**：按[初始化](#1-初始化)中的命令克隆仓库、执行初始化脚本，通过隐藏输入填写自己的 UIS 学号和密码，再创建资料输出目录。所有命令在实际运行设备上执行，Windows 使用 WSL 终端。
3. **填写配置，确认课程**：编辑 `.env`，设置输出目录绝对路径、本地学期标识和 Canvas 完整学期名称。只下载课件无需模型 key；转写录课还需核验 iCourse 学期 ID、填写 ModelScope key，首次保持自动下载模型。一般无需逐门填写课程；Canvas 未发布时可[补充课程名单](#3-可选补充课程名单)，不想手填可用下方的[截图辅助配置](#用截图整理课程名单)。
4. **手动运行并检查结果**：只需课件时按[只下载课件](#只下载课件)执行；两项都需要时按[手动运行](#手动运行)依次同步 Canvas、处理 iCourse。首次会处理本学期已有、可访问且未处理的资料，审核中的录播会跳过。首次构建、模型下载和 CPU 转写需要时间；完成后检查输出文件及错误日志，不只看退出码。
5. **按需开启定时**：手动验证正常后，再按[定时运行](#定时运行)启用 iCourse 常驻调度，并自行设置 Canvas 的宿主机计划任务。普通电脑也可以不设定时，需要时手动执行脚本。运行期间保持开机、联网且 Docker 可用，项目不会自动唤醒电脑。

结果保存在 `COURSE_OUTPUT_DIR/<课程代码 课程名>/`，转写与摘要位于其中的 `录课转写/`。本机部署直接打开文件夹；远程部署需自行配置文件共享、SFTP 或 Syncthing。后续运行复用进度，不要删除数据库来重复启动任务。

安装 Docker、准备模型 key、核验学期以及设置课件计划任务仍需使用者配合；其余步骤可交给具备终端能力的 AI 助手按本文执行。

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

### 使用 AI 辅助部署（可选）

可使用具备终端执行能力的 AI 编程助手，在实际运行设备上打开本仓库；远程部署需先由你配置好 SSH 访问。将下面的提示词交给助手，并补充设备类型、目标学期和输出目录：

```text
请按照本仓库 README 和实际代码部署 Fudan CourseFlow。先阅读使用声明与安全警告，检查 Docker、Compose、Python 和网络环境，再确认我的目标学期、输出目录，以及只下载课件还是同时转写录课。不要猜测学期 ID，不要覆盖已有配置、数据库或课程资料。账号密码和 API key 由我在本机隐藏输入或私有配置文件中填写，不要读取、回显或上传这些凭据，也不要把课程内容和完整日志发送到 AI 对话中。先校验配置并手动运行一次，报告脱敏结果；经我确认后再启用定时任务。安装软件、修改系统设置或启动会上传课程文本的摘要流程前，先向我确认。
```

AI 辅助不会免除 Docker、课程授权和模型服务配置要求，也不能保证自动部署成功。仅提供脱敏错误信息供排查；不要把 `.env`、`secrets/`、`.runtime/` 或课件与笔记目录加入 AI 的上下文。

#### 用截图整理课程名单

不想手动抄课程名称、代码和教师，或不熟悉 JSON 配置时，可以把**允许提供给 AI 的、已裁剪脱敏的课程列表或课程详情截图**交给支持图片识别的 AI 助手，让它整理配置草稿：

1. 截取 eLearning 的目标学期课程列表，以及需要补充的 iCourse 课程详情。尽量保留完整学期名称、课程代码与教学班、课程名称和教师；列表文字被截断时，补充详情页截图。
2. 需要生成 iCourse 确认名单时，另外提供对应课程详情链接中的 `course_id`，或保留只含课程链接的地址栏截图。数字学期 ID 仍需按下文从请求参数核验；课程名称和学期文字不能直接推算出 ID。
3. 让 AI 按 [JSON 示例](examples/confirmed-courses.example.json)生成草稿，逐项核对后再保存到私有配置目录。缺失、模糊或存在同名教学班的信息应先补充确认，不能猜测后直接运行。

可追加以下提示词：

```text
我不想手动填写课程名单，请根据这些已脱敏截图和课程链接，提取学期、课程代码（含教学班）、课程名称和教师，并按仓库示例整理确认名单草稿。只使用截图和链接里明确存在的信息，不要把课程代码当作 course_id，也不要猜数字学期 ID。先列出识别结果和缺失字段让我确认，再生成配置；不要改变默认课程范围或覆盖已有私有配置。账号密码和 API key 仍由我自己在本机填写。
```

截图只用于辅助整理配置，**不是程序直接读取截图进行订阅**，也不是“截图中有哪几门就只处理哪几门”的筛选开关；默认仍处理目标学期账号下的全部 Canvas 课程，确认名单用于补充 iCourse 匹配。截图不要包含学号、头像、成绩、密码、key、cookie、认证头或带凭据的地址，也不要上传课件正文或课堂发言；课程与教师信息同样应先确认允许交给第三方处理。

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

只下载课件时，完成 UIS 凭据配置后，重点填写 `COURSE_OUTPUT_DIR`、`SEMESTER_KEY` 和 `CANVAS_TARGET_TERM_NAME` 即可，不启动 iCourse。需要录课转写时，再配置 iCourse 学期和模型 key；Gemini 与邮件通知均为可选。

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

### 账号与第三方服务

- **自动登录风险**：程序会使用 UIS 凭据完成学校认证及 WebVPN 访问。服务器出口、异地 IP、频繁重试或多个设备同时登录可能触发安全校验或访问限制；不保证云端部署不会触发账号风控。遇到异常先暂停任务，再通过学校官方渠道核查。
- **本地转写不等于全程离线**：ModelScope / Gemini 会接收课程标题和完整转写文本，按配置和回退逻辑可能涉及不止一家服务商。使用前确认内容允许上传，并了解服务商的数据保留与使用政策。
- **邮件与同步边界**：可选 SMTP 会发送笔记，邮件公式渲染可能请求第三方图片服务；Syncthing、网盘或备份工具会增加数据副本。仅同步到本人受控设备，不要开启公开分享，也不要向他人邮箱发送课程内容。

### 存储与泄露防护

- **数据库未加密**：`.runtime/` 中的 SQLite 数据库保存转写、摘要及处理进度，并非仅保存课次编号。`.env`、`secrets/` 和导出的 Markdown 也以明文保存；Compose 的文件型 secrets 挂载及 `0600` 权限不等于磁盘加密。需要静态加密时，应另外配置设备磁盘与备份加密。
- **不留存媒体不等于不留存内容**：默认音视频只做流式读取，不输出媒体文件，但转写与摘要会持久化。容器退出不会自动删除挂载目录中的课程数据，不能将本项目视为“阅后即焚”。
- **私有数据不上传**：凭据、token、cookie、API key、SMTP 授权码、SSH 配置、课程名单、Manifest、数据库（包括加密备份）、课件、转写及运行日志均不应进入公开仓库。不要因为存在加密或访问密码就公开课程数据库。
- **权限与日志**：私有文件用 `0600`、目录用 `0700`，仅向可信管理员授予 Docker 权限，并限制输出目录、备份与同步目录的访问。`.gitignore` 和自动扫描不能替代人工检查；第三方报错可能包含带签名地址，不要直接公开完整日志。
- **泄露处理**：先吊销或轮换凭据，并关闭公开分享、检查副本和访问记录。删除文件或提交不能撤回已公开的 Git 历史及他人副本。安全问题请通过维护者可用的私下渠道沟通，不在公开 Issue / PR 粘贴密码、日志原文或课程内容。

### 识别与运行限制

- 中文模式不是严格词表限制，噪声、公式、姓名和专业术语仍可能误识别。AI 摘要可能遗漏、误解或编造内容；作业、考试、考勤等事项应以教师和学校的正式通知为准。
- 音频连续三次接收不完整后可能保留部分结果，应检查完整性警告。任务正常退出不代表每门课程都成功处理。
- 当前 Markdown 自动导出依赖摘要完成，不能留空 API key 直接作为纯转写模式使用；如果课程不允许上传第三方，请不要启用现有录课流程。只需课件时可单独运行 Canvas。
- 本项目只处理有权访问且获准处理的课程文件和已开放录播，不提供完整 LMS 备份。接口变更、网络中断、设备休眠或服务额度耗尽均可能导致任务失败；不保证零成本或无人维护。

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

本项目非学校官方项目。

## 许可证

本仓库由 kniphofia1 原创的整合与部署部分采用 [MIT License](LICENSE)，包括顶层 `scripts/`、`tests/`、`ci/`、`examples/` 及新编写的部署配置和文档。

`canvas/` 与 `icourse/` 中继承的上游内容不在上述授权范围内。本许可证不代表替上游作者重新授权；复用这些内容前需核实相应授权。第三方依赖和模型遵循各自许可证。
