# Fudan Course NAS

我上学期在 NAS 上分别跑了两套东西：一套自动下载 eLearning 的课件，另一套处理 iCourse 的录课。新学期开始，顺便把学期识别、目录、凭据和定时任务一起整理了，放到这个仓库里。

我想要的其实很简单：老师上传课件，NAS 自动下载；录课放出来，自动转写、生成摘要。最后都放在本学期的文件夹里，按课程分好，再用 Syncthing 同步到电脑，不用每天自己去两个网站翻。

这里整理的是我 NAS 上实际在跑的版本，另外补了一套通用的 Docker 部署入口。账号、密钥、课程内容和运行数据都没放进来。个人自用项目，跟学校官方没有关系。

## 现在是怎么跑的

**课件这边**，用 UIS 登录 eLearning，每次运行先刷新 token，再按完整学期名称找课程。只下载新增或更新的文件，保留老师原来建的文件夹。新学期还没发布就等，不会因为找不到课程又跑去下载上学期的东西。

**录课这边**，读 eLearning 生成的课程清单，去 iCourse 匹配对应的课。优先看课程代码和教学班，再看名称、教师；匹配不确定就跳过。两边共用一份 UIS 凭据，不用各存一遍密码。

转写用的是 **SenseVoice Small INT8 + sherpa-onnx**，在 NAS 的 CPU 上跑，前面用 Silero VAD 切分语音。现在设为中文主导，保留夹杂的英文。音频通过 ffmpeg 管道流式处理，不把整节课的视频、音频存下来，最终留下完整转写和 AI 摘要的 Markdown。

我现在的时间安排是：

- eLearning：每天 **07:00、19:00**，由 NAS 的计划任务启动。
- iCourse：每天 **13:00、22:00**，容器常驻，到点执行。

两边都有锁和失败重试。每个学期单独保存进度，已经转写过的课不会因为再跑一次就重新识别。

文件最后长这样，下面的课程名是示例：

```text
26-27秋学期/
└── CS99999.01 示例课程/
    ├── 讲义/
    │   └── chapter-1.pptx
    └── 录课转写/
        ├── README.md
        └── 2026-09-01_123456_课次标题.md
```

我自己再用 Syncthing 把这个目录同步到电脑。这个仓库只管下载和处理，Syncthing 要另外配。

## 想自己部署的话

需要一台能跑 Docker 的 Linux NAS，装好 Docker Compose v2 和 Python 3，再准备自己的复旦 UIS 账号。首次构建要下载镜像、依赖和模型，先确认 NAS 能访问这些站点。

下面是**从零部署**的步骤。如果你已经在跑之前的两个仓库，先看 [迁移说明](docs/operations.md)，别直接再开一套，两个任务用不同的锁写同一份数据会出问题。

```sh
git clone https://github.com/kniphofia1/fudan-course-nas.git
cd fudan-course-nas
python3 scripts/init_local.py --semester 2026-fall --credentials
```

初始化时在自己的终端输入账号和密码，输入不会显示出来。脚本会创建私有配置，已有文件不会覆盖。

然后编辑 `.env`，有几个地方要改：

1. `COURSE_OUTPUT_DIR`：课件和转写放哪里，填本学期目录的**绝对路径**，先在 NAS 上建好。
2. `SEMESTER_KEY`、`CANVAS_TARGET_TERM_NAME`、`ICOURSE_TERM_ID`：确认是自己的目标学期。Canvas 的 Term ID 会自动识别，iCourse 的学期 ID 要自己核对，别混着用。
3. `DASHSCOPE_API_KEY`：名字是以前沿用下来的，实际填的是 **ModelScope 推理 API key**，不是阿里云 DashScope 的 key。
4. `icourse/src/config.py`：检查里面的模型列表。服务商可能下架或调整模型，不能保证这些名字一直能用。
5. 邮件通知不用就把 SMTP 几项留空；如果填了 `GEMINI_API_KEY`，摘要会先尝试 Gemini。

配置好以后：

```sh
chmod 600 .env secrets/fudan_username secrets/fudan_password
docker compose config --quiet
docker compose --profile manual build
sh scripts/run-canvas.sh
docker compose up -d icourse
```

第一次跑 Canvas 会自己登录、刷新 token，不需要手工复制。iCourse 首次启动会下载模型；如果你已经把模型放好了，可以设 `SKIP_MODEL_DOWNLOAD=true`。

## 定时之外，也可以手动跑

Canvas 的定时需要自己在 NAS 计划任务里加，设为每天 07:00、19:00 执行：

```sh
sh /absolute/path/to/fudan-course-nas/scripts/run-canvas.sh
```

NAS 时区记得设成 Asia/Shanghai。脚本不会替你改系统 crontab；iCourse 的 13:00、22:00 则由容器里的调度器负责。

如果老师刚发了课件，不想等下一次定时，直接跑一次就行：

```sh
# 定时之外追加一次课件同步
sh scripts/run-canvas.sh

# 定时之外追加一次录课处理；共享进度锁，默认关闭本次邮件
sh scripts/run-icourse-once.sh

# 查看录课调度和运行状态
docker compose ps
docker compose logs --tail 80 icourse
```

手动跑和定时跑共用进度、共用锁，不会改掉下一次定时。手动录课脚本默认不发邮件。

## eLearning 还没发布，iCourse 已经有录课了怎么办

这学期我就碰到了这种情况，所以加了一个手动确认名单。

把自己核对过的课程放在 `.runtime/icourse/<SEMESTER_KEY>/confirmed-courses.json`，格式参考 [这个示例](examples/confirmed-courses.example.json)，然后在 `.env` 里加：

```dotenv
CONFIRMED_COURSES_PATH=/app/data/confirmed-courses.json
```

示例里的课程是虚构的，别原样拿去跑。填自己的课程 ID、代码、名称、教师和学期，文件权限设成 `0600`。

程序会再核对名称和教师。后面 eLearning 发布了，自动发现的课程会和这份名单合并，不用二选一。录课还是要等平台开放，审核中、延迟发布或已过开放期限的都不会提前处理。

## 几个需要提前说的事

**语音识别在本地，摘要不在。** 生成摘要时，会把课程名称和转写文本发给你配置的模型服务。邮件通知也会把笔记发出去。介意这点的话，先看 [隐私说明](SECURITY.md)，确认课程内容可以这样处理再用。

转写也不是逐字准确的。我之前就遇到过噪声被识别成日语、韩语，所以改成了中文主导。但这个设置不是严格的中英词表限制，专业词和听不清的地方还是可能错，别把自动稿当成校对过的原文。

目前还有一个不太方便的地方：**Markdown 自动导出要等摘要阶段完成**。模型服务报错时，转写会留在数据库里，下次不用重转，但文件夹里可能还看不到 Markdown。这个版本也不能把 API key 留空，就直接当纯转写工具用。

另外，网络不好时音频会重试；连续三次都没接收完整，现有代码可能保留最后一次的部分结果。看到完整性警告，要回去核对录课，不能只看“有文件了”。

课件下载只覆盖账号有权限访问的 Canvas 文件，不是把整个网站备份下来，页面正文、外链、测验这些不保证覆盖。UIS 密码过期、学校改登录方式、模型接口下架，也都可能让任务停下来。具体排查放在 [维护文档](docs/operations.md) 里。

## 代码放在哪

| 路径 | 内容 |
|---|---|
| `canvas/` | Rust 下载器、UIS token 刷新、学期发现与测试 |
| `icourse/` | 登录、课程匹配、流式 ASR、摘要、Markdown、调度与测试 |
| `compose.yaml` | 整理后的统一部署入口 |
| `scripts/` | 私有目录初始化、手动执行入口、Canvas 锁与重试 |
| `docs/` | 部署维护、来源与版本记录 |
| `.runtime/`、`secrets/` | 仅运行后在本地产生，始终排除出 Git |

```sh
python3 -m unittest discover -s tests -v
# 组件测试需要各自 requirements.txt
(cd canvas && python3 -m unittest discover -s tests -v)
(cd icourse && python3 -m unittest discover -s tests -v)
```

整理发布时跑过 38 项测试，包括模拟接口下的学期识别、重复运行、课程匹配和部署脚本。Canvas 的真实 Rust 集成测试需要把 `CANVAS_TEST_BINARY` 设为已构建程序的绝对路径。这些测试过了，不代表所有 NAS 和后续学校接口变化都能覆盖。

[Actions 模板](ci/tests.yml.example) 也放了，目前还没启用，发布时的授权缺少 `workflow` 权限。要启用的话，用有对应权限的凭据，把它放到 `.github/workflows/tests.yml` 再提交。里面只有模拟测试和密钥扫描，不会拿学校账号跑真实同步。

## 从哪来的

不是从零写的。上学期用的是我 fork 的 [canvas-downloader](https://github.com/kniphofia1/canvas-downloader) 和 [Fudan_iCourse_Subscriber](https://github.com/kniphofia1/Fudan_iCourse_Subscriber)，这次把 NAS 上的改动和部署方式整到一起。

感谢原作者 [bnjmnt4n](https://github.com/bnjmnt4n/canvas-downloader)、[LeafCreeper](https://github.com/LeafCreeper/Fudan_iCourse_Subscriber)，以及 SenseVoice、sherpa-onnx、Silero VAD 这些项目。具体来源、对应提交和整理差异在 [这里](docs/provenance.md)。

上游没有明确的根 LICENSE，所以我没有直接给整套代码挂一个 MIT。仓库公开不等于统一授予了开源许可，复用和分发前请核对上游授权，依赖和模型也按各自的许可来。

最后，只处理自己有权访问的课程。这个仓库分享的是工具，不分享老师的课件和录课。
