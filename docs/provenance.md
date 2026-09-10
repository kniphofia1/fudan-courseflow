# 来源与运行版本

整理日期：2026-09-10。本仓库从以下精确提交按白名单导入源码，未导入 Git 历史。
发布前已通过 NAS 镜像 revision 与部分源码校验确认运行版本。

| 组件 | 作者维护分支 | NAS 运行提交 |
|---|---|---|
| Canvas | [kniphofia1/canvas-downloader](https://github.com/kniphofia1/canvas-downloader/tree/codex/2026-fall-nas) | `2255e89d2a28fcc1d3c64db90f887c4f4f7bea2d` |
| iCourse | [kniphofia1/Fudan_iCourse_Subscriber](https://github.com/kniphofia1/Fudan_iCourse_Subscriber/tree/codex/2026-fall-nas) | `09c42acf3cdf1c0ee7218b455ee80e19ba866c20` |

更早的上游来源：

- [bnjmnt4n/canvas-downloader](https://github.com/bnjmnt4n/canvas-downloader)：Canvas Rust 下载器。
- [LeafCreeper/Fudan_iCourse_Subscriber](https://github.com/LeafCreeper/Fudan_iCourse_Subscriber)：iCourse 订阅、转写与摘要流程。
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)、[SenseVoice](https://github.com/FunAudioLLM/SenseVoice)、[Silero VAD](https://github.com/snakers4/silero-vad)：语音识别和语音活动检测。

本次整理保留组件的运行逻辑和测试，仅清理行尾空白，新增顶层通用 Compose、初始化脚本、
运行入口、文档和纯模拟 CI 模板（待启用）。顶层部署不使用作者 NAS 的绝对路径：

- 两个分散 Compose 改为一个项目；现有 NAS **没有因此自动迁移**。
- Canvas 手动/定时互斥锁放入共享持久化目录，避免跨用户打开宿主机锁文件的权限问题。
- 原 NAS 沿用系统计划入口；通用版本提供脚本，要求用户显式配置计划任务。
- 保留每次刷新 token、07:00/19:00 与 13:00/22:00 的节奏。
- 不附带字体、旧前端、课程截图、加密数据库、GitHub 定时导出/清空进度工作流。
- 模型列表与推理参数是快照，不代表这些模型目前全部可用。

发布前验证：Canvas 11 项（包含真实 Rust 程序 + 模拟接口），iCourse 23 项，
部署脚本 4 项，共 38 项测试通过；NAS 独立测试目录中的 Compose 配置校验通过。
组件测试容器使用 `--network none`，未使用学校账号或真实课件。另做 Gitleaks 密钥扫描
和文件白名单检查；自动扫描不能替代运行日志分享前的人工脱敏。

没有加入统一 LICENSE：两个直接来源及更早上游的 GitHub license 元数据均为空，
导入文件中也没有根许可证文件。这一事实不构成额外授权；保留原作者归属，
不把第三方代码或模型重新声明为本仓库独立所有。
