# Fudan Course NAS

把复旦 eLearning（Canvas）课件下载与 iCourse 录课转写整理成一套可在 NAS 上部署的流程。

这是作者 NAS 运行版本的**脱敏源码快照 + 通用部署入口**，不是学校官方项目。
不包含账号、课程资料、转写结果、数据库、模型权重或服务器连接配置。

## 做什么

- **eLearning**：UIS 登录并刷新短期 token，按完整学期名称识别课程，下载新增或更新文件，保留 Canvas 文件夹分类。
- **iCourse**：读取 Canvas 课程清单，按课程代码/教学班优先匹配，名称和教师辅助匹配；不接受有歧义的课程。
- **录课转写**：ffmpeg 流式音频 → Silero VAD → sherpa-onnx SenseVoice Small INT8，本地 CPU 识别；默认中文主导，保留英文术语。
- **学习资料**：生成完整转写与 AI 摘要 Markdown，写到对应课程的 `录课转写/`。不持久保存音频或视频。
- **自动运行**：Canvas 由 NAS 计划任务在 07:00 / 19:00 启动；iCourse 常驻容器在 13:00 / 22:00 运行。两边都有互斥锁和失败重试。
- **学期隔离**：目标学期未发布时正常 `pending`，不回退到旧学期。每学期独立进度、映射缓存和输出目录。

目录示例（虚构课程）：

```text
26-27秋学期/
└── CS99999.01 示例课程/
    ├── 讲义/
    │   └── chapter-1.pptx
    └── 录课转写/
        ├── README.md
        └── 2026-09-01_123456_课次标题.md
```

Canvas → 无凭据课程清单 → iCourse 课程匹配；两者共用 UIS secret 和输出根目录。
Syncthing 可另行配置在 NAS 和电脑之间同步该目录，本仓库不安装或配置 Syncthing。

## 快速开始（新部署）

需要 Linux NAS、Docker Engine + Compose v2、Python 3、可正常访问的复旦 UIS 账号。
首次构建需要访问容器镜像、Python/Rust 包源和模型下载站点。

```sh
git clone https://github.com/kniphofia1/fudan-course-nas.git
cd fudan-course-nas
python3 scripts/init_local.py --semester 2026-fall --credentials
```

脚本在本地隐藏输入账号和密码，创建权限为 `0600` 的 secret 文件；不会覆盖已有配置。
编辑 `.env`：

1. 把 `COURSE_OUTPUT_DIR` 改为**本学期专用目录的绝对路径**，并在宿主机创建该目录。
2. 确认 `SEMESTER_KEY`、`CANVAS_TARGET_TERM_NAME`、`ICOURSE_TERM_ID` 与自己的学期一致。
3. 填写 `DASHSCOPE_API_KEY`。这是沿用的变量名，实际对应 **ModelScope 推理 API key**。
4. 检查 `icourse/src/config.py` 中的模型列表是否仍由服务商提供；快照中的模型名称不保证持续可用。
5. 邮件通知可选，不用时保留 SMTP 字段为空。填写 `GEMINI_API_KEY` 后会优先尝试 Gemini。

```sh
chmod 600 .env secrets/fudan_username secrets/fudan_password
docker compose config --quiet
docker compose --profile manual build
sh scripts/run-canvas.sh
docker compose up -d icourse
```

第一次 Canvas 运行会用 UIS 刷新占位 token；无需手工复制真实 token。
首次 iCourse 启动会下载模型，已准备好模型时可设置 `SKIP_MODEL_DOWNLOAD=true`。

**不要把这些命令直接用于替换已经运行的老部署。** 新目录默认拥有新的数据库和锁，
与旧任务并行会重复处理。已有部署先看 [迁移与维护](docs/operations.md)。

## 定时与手动运行

在 NAS 计划任务界面配置每天 07:00、19:00 执行：

```sh
sh /absolute/path/to/fudan-course-nas/scripts/run-canvas.sh
```

NAS 的宿主机时区也应设为 Asia/Shanghai。本仓库**不会自动修改系统 crontab**。
同一部署的手动和定时 Canvas 任务共享容器内持久化文件锁。

```sh
# 定时之外追加一次课件同步
sh scripts/run-canvas.sh

# 定时之外追加一次录课处理；共享进度锁，默认关闭本次邮件
sh scripts/run-icourse-once.sh

# 查看录课调度和运行状态
docker compose ps
docker compose logs --tail 80 icourse
```

手动执行不会改变下一次定时时间。已经保存的转写不会因为再次运行而重新识别。

## Canvas 未发布，但录课已开放

把自己的确认名单保存在 `.runtime/icourse/<SEMESTER_KEY>/confirmed-courses.json`，
格式参考 [虚构示例](examples/confirmed-courses.example.json)，并在 `.env` 设置：

```dotenv
CONFIRMED_COURSES_PATH=/app/data/confirmed-courses.json
```

只填写自己核验过的 iCourse 课程 ID、课程代码、名称、教师和学期，勿原样使用示例。
启用前将名单权限设为 `0600`。程序会检查名称和教师，并与后来发布的 Canvas 清单合并。
有录制文件不等于已开放：审核中、延迟发布、未开始、已过开放期限的课次不会提前处理。

## 数据与运行边界

- **本地转写不等于全流程离线。** AI 摘要会发送课程名称和转写文本至配置的云端模型服务；可选邮件会发送课程笔记。先阅读 [隐私与安全](SECURITY.md)。
- 中文模式是语言提示，不是严格中英词表限制；噪声、术语、口音仍会产生误识别，输出不是人工校对稿。
- 此快照中 Markdown 自动导出依赖摘要阶段完成；摘要失败时转写已保存在数据库，后续重试会跳过 ASR，但 Markdown 可能尚未生成。没有配置模型 key 时不能直接当作“纯转写模式”启动。
- 音频接收不足会尝试重连；现有代码在连续三次不完整后可能使用最后一次部分结果，阅读时应检查日志中的完整性警告。
- 只同步账号有权访问的 Canvas 文件；不是整个 LMS 的完整备份，不保证覆盖页面正文、外链、测验等资源。
- Canvas token 即使配置了有效期，也可能提前失效；每次运行强制刷新。UIS 密码过期或学校登录流程变化仍可能导致失败。
- 已测试的是源码单元测试、模拟接口集成测试和部署配置。不是对所有 NAS 架构、学校接口或模型服务可用性的保证。

## 仓库布局与测试

| 路径 | 内容 |
|---|---|
| `canvas/` | Rust 下载器、UIS token 刷新、学期发现与测试 |
| `icourse/` | 登录、课程匹配、流式 ASR、摘要、Markdown、调度与测试 |
| `compose.yaml` | 通用 NAS 部署，共享 secrets 和学期目录 |
| `scripts/` | 私有目录初始化、手动执行入口、Canvas 锁与重试 |
| `docs/` | 部署维护、来源与版本记录 |
| `.runtime/`、`secrets/` | 仅运行后在本地产生，始终排除出 Git |

```sh
python3 -m unittest discover -s tests -v
# 组件测试需要各自 requirements.txt
(cd canvas && python3 -m unittest discover -s tests -v)
(cd icourse && python3 -m unittest discover -s tests -v)
```

Canvas 的真实 Rust 集成测试还需要设置 `CANVAS_TEST_BINARY` 为已构建程序的绝对路径。

提供 [GitHub Actions 模板](ci/tests.yml.example)，但当前未启用：发布账号的 OAuth 授权
没有 `workflow` scope。维护者可使用具有工作流写入权限的凭据，把模板保存为
`.github/workflows/tests.yml` 后提交。模板仅运行模拟测试和密钥扫描，不执行真实课程同步。

## 来源与许可

整理自 [canvas-downloader](https://github.com/kniphofia1/canvas-downloader) 和
[Fudan_iCourse_Subscriber](https://github.com/kniphofia1/Fudan_iCourse_Subscriber) 的 NAS 运行分支。
精确提交、上游作者和此次整理差异见 [来源记录](docs/provenance.md)。

**公开可见不等于已获得统一开源许可证。** 来源仓库在整理时未提供明确的根 LICENSE；
本仓库没有擅自为上游代码添加 MIT 等许可。复用、分发前请自行核实上游授权；
第三方依赖和模型遵循各自许可证。仅访问自己有权使用的课程，不公开分发课程内容。
