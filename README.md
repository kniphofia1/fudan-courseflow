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

环境要求：Linux NAS、Docker Engine、Docker Compose v2、Python 3，以及有效的复旦 UIS 账号。首次构建需下载依赖和模型。

```sh
git clone https://github.com/kniphofia1/fudan-course-nas.git
cd fudan-course-nas
python3 scripts/init_local.py --semester 2026-fall --credentials
```

初始化脚本通过隐藏输入读取凭据，不覆盖已有配置。编辑生成的 `.env`：

| 配置项 | 说明 |
|---|---|
| `COURSE_OUTPUT_DIR` | 本学期输出目录的绝对路径，需提前创建 |
| `SEMESTER_KEY` | 学期标识，用于隔离运行数据 |
| `CANVAS_TARGET_TERM_NAME` | Canvas 中完整的学期名称，Term ID 自动识别 |
| `ICOURSE_TERM_ID` | 经平台核验的 iCourse 学期 ID |
| `DASHSCOPE_API_KEY` | ModelScope 推理 API key，变量名沿用历史配置 |
| `GEMINI_API_KEY` | 可选；配置后优先使用 Gemini 生成摘要 |
| SMTP 相关配置 | 可选邮件通知，不使用时留空 |

部署前请确认 `icourse/src/config.py` 中的摘要模型仍可用。

```sh
chmod 600 .env secrets/fudan_username secrets/fudan_password
docker compose config --quiet
docker compose --profile manual build
sh scripts/run-canvas.sh
docker compose up -d icourse
```

首次运行自动刷新 Canvas token 并下载 ASR 模型。已有模型可设置 `SKIP_MODEL_DOWNLOAD=true`。从旧部署迁移时，请先阅读 [迁移说明](docs/operations.md)，避免重复调度和数据冲突。

## 运行

默认时区为 `Asia/Shanghai`。

| 任务 | 时间 | 调度方式 |
|---|---|---|
| eLearning | 07:00、19:00 | 在 NAS 计划任务中配置 |
| iCourse | 13:00、22:00 | 容器内置调度 |

NAS 计划任务入口：

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

Canvas 尚未发布而 iCourse 已开放时，可使用 [课程确认名单](examples/confirmed-courses.example.json)。将核验后的名单保存至 `.runtime/icourse/<SEMESTER_KEY>/confirmed-courses.json`，权限设为 `0600`，并配置：

```dotenv
CONFIRMED_COURSES_PATH=/app/data/confirmed-courses.json
```

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
