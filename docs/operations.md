# 维护、排错与迁移

## 学期与课程标识

这三个值含义不同，不能互相替代：

| 配置 | 获取方式 |
|---|---|
| `SEMESTER_KEY` | 自定义的本地目录标识，如 `2026-fall`；与初始化脚本参数一致 |
| `CANVAS_TARGET_TERM_NAME` | 从 eLearning 课程列表的学期栏获取完整名称；Canvas 数字 Term ID 由程序识别 |
| `ICOURSE_TERM_ID` | iCourse 课程列表请求中的 `term` 参数，需核对所选学期 |

核验 iCourse 学期 ID：

1. 在浏览器登录 iCourse，打开课程列表，并打开开发者工具的 Network（网络）面板。
2. 切换到目标学期，筛选 `get-course-list` 请求。当前代码使用的接口路径为
   `/portal/courseapi/v3/multi-search/get-course-list`。
3. 读取该请求 Query String Parameters 中的 `term`，确认页面所选学期正确后填入 `.env`。
   不要把浏览器 cookie、请求认证头或完整网络记录公开分享。若平台接口已变更，应重新核验，不能猜测 ID。

私有确认名单中的 `icourse_id` 则取自课程详情页 URL 的 `course_id`；课程代码、名称、教师
取自同一课程页面，名单的 `term_id` 须与 `.env` 一致。示例文件中的 ID 仅用于展示格式。

## 首次配置与修改

重新创建或构建服务前，应等待当前任务结束，避免中断正在处理的录课。

- `.env` 中的输出路径应替换为真实、可写、专用于本学期的 NAS 目录；不要保留 `/absolute/path/...` 占位值。
- UIS 凭据由初始化脚本写入 `secrets/fudan_username` 与 `secrets/fudan_password`，不用填写到 `.env`。
- `.env` 使用 dotenv 格式，不是 shell 脚本。由 Compose 读取即可，不需要 `source .env`。
- 重新运行初始化不会修改已有 `.env` 或凭据；换学期或更新密码时需要自行编辑相应文件。
- 修改 `.env` 后运行 `docker compose up -d icourse`；修改程序或模型列表后运行
  `docker compose up -d --build icourse`。仅执行 `restart` 不会重新读取配置或构建镜像。
- 更新 secret 文件后，确认没有正在处理的任务，再执行 `docker compose up -d --force-recreate icourse`。
  Canvas 每次启动新的临时容器，会读取当前配置和 secret。
- `ICOURSE_RUN_TIMES` 控制录课调度时间，Canvas 的时间则在 NAS 计划任务中修改。
- 恢复录课服务使用 `docker compose up -d icourse`；恢复 Canvas 需重新启用 NAS 计划任务。

## 持久化目录

| 宿主机 | 容器内 | 内容 |
|---|---|---|
| `.runtime/canvas/<SEMESTER_KEY>` | Canvas `/data` | token、浏览器会话、同步日志、锁 |
| 其下 `.state` | iCourse `/app/canvas-state`（只读） | `semester-courses.json` |
| `.runtime/icourse/<SEMESTER_KEY>` | `/app/data` | SQLite、课程映射、确认名单、任务锁 |
| `.runtime/models` | `/app/models` | 可复用的 ASR 权重 |
| `COURSE_OUTPUT_DIR` | `/downloads` 或 `/app/exports` | 本学期课件与 Markdown |
| `secrets/` | `/run/secrets/` | 两任务共用 UIS 凭据 |

所有路径均由仓库根目录解释。NAS 容器默认以 root 运行；运行后私有文件可能变成 root 所有，
不要通过 `chmod -R 777` 解决。由管理员通过只读容器检查必要文件，或制定明确的用户映射策略。
Syncthing 在宿主机需要读取输出目录，私有凭据目录则不应加入同步。

Canvas 的运行日志位于 `.runtime/canvas/<SEMESTER_KEY>/sync.log`，每轮下载记录位于
同目录下的 `log/`。iCourse 的常驻日志通过 `docker compose logs icourse` 查看。
`run-icourse-once.sh` 使用临时容器，完成后删除容器，其输出需在执行终端查看。
备份时至少保留学期数据库、配置与课程输出；SQLite 应在停写后备份或使用一致性备份方式。
不要把整个 `.runtime/` 加入公开仓库或无访问控制的文件分享。

## 常见情况

- **Canvas pending**：在当前账号可访问课程中未找到完整学期名称。检查课程是否已发布，
  学期名称是否完全一致；不要临时改成旧 Term ID。新学期出现后会自动选取真实 ID。
- **只有部分课程**：未发布课程对学生 API 不一定可见；iCourse 可以使用私有确认名单补充。
- **iCourse 审核中**：程序尊重平台延迟开放时间，不因获取到媒体信息就提前转写。
- **token 401**：短期 token 可能已失效；正常 Canvas 入口会先刷新，不必把 token 发给维护者。
- **UIS 登录失败**：先手工确认账号状态；在 NAS 本地更新共享 secret，并重新创建相关容器。
- **摘要模型 unavailable / timeout**：核对服务商当前模型列表、权限和额度，修改
  `icourse/src/config.py` 的 `LLM_MODELS` / `GEMINI_MODELS` 后重新构建。转写已保存就不会重复 ASR。
- **有转写但没 Markdown**：这个运行快照的导出依赖摘要成功。先查模型服务错误，
  不要删除数据库强迫重转写。诊断时不要公开数据库内容。
- **模型缺失**：首次部署使用 `SKIP_MODEL_DOWNLOAD=false`；已有模型应包含
  `model.int8.onnx`、`tokens.txt`、`silero_vad.onnx`，目录布局见 Compose。
- **文件没到电脑**：先检查 NAS 输出，再检查自己配置的 Syncthing。文件下载成功不等于电脑已收到。

## 换学期

1. 停止或暂停旧学期计划入口，记录现有版本和挂载路径。
2. 换新的 `SEMESTER_KEY`、输出目录和确切学期名；iCourse 学期 ID 以平台核验为准。
3. `python3 scripts/init_local.py --semester <new-key>` 创建新私有目录。
   初始化**不覆盖已有 `.env`**，需自行编辑 `.env` 中相应值。
4. 使用本学期确认名单，不复用旧名单、SQLite 或课程映射；模型权重可以复用。
5. 先手动运行核验输出，确认只处理新学期，再恢复计划任务。

## 从原来的两个 NAS 部署迁移

本公开仓库的源码快照与运行版本对应，但顶层目录与 Compose 项目名不同。
迁移并非发布仓库的附带动作：不要同时启动旧、新调度器。

迁移前需备份脚本、Compose、私有配置，并为 SQLite 做一致性备份；记录镜像 revision。
等当前任务结束，暂停旧任务，再决定使用外部挂载 override 复用原有数据，还是复制已停写的进度。
必须把 **DB、任务锁、课程映射、确认名单和输出路径** 作为一组核对。
旧 Canvas manifest 名可能是 `2026-fall-courses.json`，通用版本是 `semester-courses.json`，
挂载和环境变量必须保持一致。模型不必重新下载。

先用手动任务验证无重复下载/转写，再把原 NAS 计划入口指向新脚本；保留旧部署用于回滚。
回滚时同样只保留一组调度器，不能让两套不同锁的任务写入同一数据库。

不附带自动清空、删除、迁移或覆盖数据库的脚本。
