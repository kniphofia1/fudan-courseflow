# Fudan Course NAS

面向复旦 eLearning（Canvas）与 iCourse 的 NAS 自动化工具，支持课件增量下载、录课转写和 AI 摘要，按学期与课程统一归档。

## 功能

- **课件下载**：UIS 自动登录、短期 token 刷新、目标学期识别，保留课程文件夹结构。
- **课程匹配**：基于课程代码、教学班、名称和教师匹配 iCourse 课程，跳过歧义及未开放录播。
- **录课转写**：使用 SenseVoice Small INT8、sherpa-onnx 和 Silero VAD，在 NAS CPU 上进行中文主导的语音识别，保留英文术语。
- **资料归档**：流式处理音频，不保存音视频文件；输出完整转写与 AI 摘要 Markdown。
- **定时运行**：支持互斥锁、失败重试、增量处理和独立学期进度。

输出目录示例：

```text
26-27秋学期/
└── CS99999.01 示例课程/
    ├── 讲义/
    │   └── chapter-1.pptx
    └── 录课转写/
        ├── README.md
        └── 2026-09-01_123456_课次标题.md
```

可通过 Syncthing 将输出目录同步至电脑，需自行配置。

## 部署

环境要求：Linux NAS、Git、Docker Engine、Docker Compose v2、Python 3，以及可访问目标课程的复旦 UIS 账号。无需 GPU；NAS 需能访问学校认证、课程平台、模型服务和依赖下载站点。

以下命令均在 **NAS 终端**执行，操作账号需有 Docker 权限。克隆后保持在仓库根目录；本项目通过命令行和文件目录使用，不提供 Web 管理界面。

```sh
git clone https://github.com/kniphofia1/fudan-course-nas.git
cd fudan-course-nas
python3 scripts/init_local.py --semester 2026-fall --credentials
```

初始化脚本通过隐藏输入读取凭据，保存到 `secrets/`，不覆盖已有配置。编辑生成的 `.env`；其中 `SEMESTER_KEY` 必须与初始化时的 `--semester` 一致：

| 配置项 | 说明 |
|---|---|
| `COURSE_OUTPUT_DIR` | 本学期输出目录的绝对路径，需提前创建 |
| `SEMESTER_KEY` | 学期标识，用于隔离运行数据 |
| `CANVAS_TARGET_TERM_NAME` | Canvas 中完整的学期名称，Term ID 自动识别 |
| `ICOURSE_TERM_ID` | 经平台核验的 iCourse 学期 ID |
| `DASHSCOPE_API_KEY` | 录课处理必填的 ModelScope 推理 API key，并非阿里云 DashScope key |
| `GEMINI_API_KEY` | 可选；配置后优先使用 Gemini 生成摘要 |
| SMTP 相关配置 | 可选邮件通知，不使用时留空 |

学期配置默认以 2026–2027 秋学期为例，不适用于所有学期。Canvas 学期名称取自 eLearning；iCourse 学期 ID 的核验方法见 [配置说明](docs/operations.md#学期与课程标识)。

ModelScope key 可在 [访问令牌页面](https://modelscope.cn/my/myaccesstoken) 获取。当前代码即使配置 Gemini，也仍要求填写 ModelScope key；额度与模型可用性以服务商为准。部署前检查 `icourse/src/config.py` 中的摘要模型列表。

```sh
chmod 600 .env secrets/fudan_username secrets/fudan_password
docker compose config --quiet
docker compose --profile manual build
sh scripts/run-canvas.sh
docker compose up -d icourse
```

Canvas 首次运行自动刷新 token；iCourse 首次启动下载 ASR 模型，随后等待定时时间，**不会立即转写**。如需首次补处理，等待日志出现 `Next run at ...` 后执行下方的手动录课命令，避免并发下载模型。已有模型可设置 `SKIP_MODEL_DOWNLOAD=true`。

首次处理范围为目标学期当前可访问的课件，以及成功匹配课程中所有已开放、未处理的录播，并非仅当天内容。批量转写耗时取决于录课长度和 NAS 性能。

仅需课件下载时，可只执行 `docker compose build canvas` 和 `sh scripts/run-canvas.sh`，不启动 iCourse，也无需填写模型 key。从旧部署迁移时，请先阅读 [迁移说明](docs/operations.md)，避免重复调度和数据冲突。

## 运行

默认时区为 `Asia/Shanghai`，NAS 宿主机的计划任务时区也需保持一致。

| 任务 | 时间 | 调度方式 |
|---|---|---|
| eLearning | 07:00、19:00 | 在 NAS 计划任务中配置 |
| iCourse | 13:00、22:00 | 容器内置调度 |

NAS 计划任务入口（替换为实际仓库路径，任务账号需有 Docker 权限）：

```sh
sh /absolute/path/to/fudan-course-nas/scripts/run-canvas.sh
```

手动运行与状态检查：

```sh
sh scripts/run-canvas.sh              # 追加一次课件同步
sh scripts/run-icourse-once.sh        # 追加一次录课处理，本次不发送邮件
docker compose ps
docker compose logs --tail 80 icourse
```

手动任务与定时任务共享进度和锁，不改变定时安排。目标学期未发布时返回 `pending`，不回退至旧学期。

### 验证运行结果

- **课件**：日志应显示目标学期与课程、下载结果，或明确的 `pending` 状态。Canvas 为一次性任务，完成后容器被移除，未出现在 `docker compose ps` 中属于正常情况。
- **录课**：常驻容器应处于运行状态，日志包含下一次调度时间；成功导出时出现 `[Markdown] Exported`。容器运行或退出码为 0 本身不代表所有课程处理成功，仍需检查错误、跳过原因和输出文件。
- **文件**：课件位于 `COURSE_OUTPUT_DIR/<课程目录>/`，转写位于其下的 `录课转写/`；电脑端是否收到取决于另行配置的同步工具。

### 补充课程名单

Canvas 尚未发布而 iCourse 已开放时，可使用 [课程确认名单](examples/confirmed-courses.example.json)。将核验后的名单保存至 `.runtime/icourse/<SEMESTER_KEY>/confirmed-courses.json`，权限设为 `0600`，并配置：

```dotenv
CONFIRMED_COURSES_PATH=/app/data/confirmed-courses.json
```

这是容器内路径，不要填成 NAS 路径。示例中的课程信息需全部替换；iCourse 课程 ID 取自课程页面地址中的 `course_id`，不是学期 ID。修改 `.env` 后执行 `docker compose up -d icourse` 使常驻任务采用新配置。

待当前任务结束后，可执行 `docker compose stop icourse` 停止录课调度；停止 Canvas 自动同步需另行暂停 NAS 计划任务。进度、token 和模型保存在 `.runtime/`，凭据保存在 `secrets/`，不要通过删除这些目录重试任务。

## 注意事项

- 语音识别在本地运行；AI 摘要会将课程名称和转写文本发送至配置的模型服务。
- 当前版本的 Markdown 自动导出依赖摘要完成。摘要失败时转写保留在数据库，后续重试跳过识别；不支持直接留空 API key 作为纯转写模式。
- 自动识别可能存在错误；音频连续重试后仍不完整时可能保留部分结果，请检查完整性警告。
- 仅处理账号有权访问的课程文件及已开放录播，不提供完整 LMS 备份。请勿提交凭据、运行数据或课程内容。

## 文档

- [部署维护与故障排查](docs/operations.md)
- [隐私与安全](SECURITY.md)
- [源码来源、版本与测试记录](docs/provenance.md)
- [GitHub Actions 测试模板（未启用）](ci/tests.yml.example)

## 致谢与许可

整合自 [canvas-downloader](https://github.com/kniphofia1/canvas-downloader) 与 [Fudan_iCourse_Subscriber](https://github.com/kniphofia1/Fudan_iCourse_Subscriber) 的 NAS 运行分支。感谢上游作者 [bnjmnt4n](https://github.com/bnjmnt4n/canvas-downloader)、[LeafCreeper](https://github.com/LeafCreeper/Fudan_iCourse_Subscriber)，以及 SenseVoice、sherpa-onnx、Silero VAD 项目。

本项目非学校官方项目。来源仓库未提供明确的根 LICENSE，因此未添加统一许可证；复用与分发前请核实上游授权，第三方依赖与模型遵循各自许可。
