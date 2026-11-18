# 内部应用部署

内部可以连续部署多次，再汇总为一次对外版本。`VERSION` 可沿用开发版本（例如 `0.5.0-beta.1`）；每次部署以完整 Git SHA、镜像 ID、源文件及镜像归档摘要唯一识别。镜像标签包含完整版本与完整 SHA，不覆盖旧标签，不推送 `v*` Tag，也不创建 GitHub Release。公开发行仍遵循[正式发布门槛](./release-and-deployment-identity.md)。

## 第一版范围

此流程用于已有健康实例的**同数据库结构应用更新**，构建目标架构的 API 和网页，复用不变的数据库、Redis、对象存储。执行器只有在对应镜像的来源提交可追溯、Dockerfile、依赖和挂载执行代码完全一致时才能复用。API/网页继续构建，确保两者版本诊断对应本次提交。数据库迁移文件（包括修改已有迁移）、数据库镜像、存储或 Compose 基础定义发生变化时停止，另行准备真实源版本到目标版本的迁移、恢复与切换方案。

它不是公开发布的验收认证，不需要构建所有平台架构或未使用的独立 Gateway/Compute 包，也不绕过失败检查。源代码必须干净且已提交；私有实例配置、凭证、日志及验收资料放在长期保留的 `.private/ops/<实例>/`，不要进入 Git 或构建上下文。

## 准备与验证

在准确候选 checkout 中，用已有部署的完整 SHA 和目标架构准备一个新的私有输出目录：

```bash
python3 deploy/internal/platform-internal.py prepare \
  --base <完整的现运行提交SHA> --platform linux/amd64 \
  --web-origin https://workspace.example.org \
  --output /private/ops/candidate \
  --reuse-executor <已核验的执行器镜像>
```

省略 `--reuse-executor` 会重建执行器。命令不推送源码或镜像，不连接生产服务器。输出包括镜像归档、仅含已提交 API/部署源文件的归档，以及绑定实际字节的 `manifest.json`。构建失败需先查明原因；更换输出目录重试，不覆盖已存在的镜像身份。

源码检查按实际源版本与候选差异选择，至少覆盖版本与锁文件一致性、改动代码的类型/单元检查以及受影响的权限和浏览器工作路径。部署工具自身的检查为 `python3 -m unittest discover -s tests/deployment`。同一准确候选的成功检查不必重复运行；改变提交后不能沿用旧回执。

本地源码检查统一使用共享入口，例如 `node scripts/pre-push.mjs --check types`、`node scripts/pre-push.mjs --check api-tests`。该入口与推送前检查可以复用最近一次成功结果，最长 24 小时；必须是同一干净提交、工作目录、命令、环境、工具程序及已安装依赖元数据。日志按 SHA256 绑定，保存在忽略的 `.cache/local-checks/`，回执不保存环境变量值或凭证。存在未提交或未跟踪源码、配置变化、失败或中断的重试、日志缺失或被修改、结果过期时均重新执行。添加 `--fresh` 可强制重跑。直接执行其他测试命令不会产生可复用回执。

此缓存只用于本地反馈，不是发布认证，也不替代构建产物。CI、远端镜像可用性、真实数据库集成、浏览器和镜像验收、恢复检查均不通过它复用；设置了 `CI`、`GITHUB_ACTIONS` 或 `RESOURCE_TEST_DATABASE_URL` 时不使用缓存。后面的内部产物、迁移和恢复回执仍需分别完成。

GitHub 按改动范围检查 PR 和 `main` 分支推送，并保留手动触发；开发分支推送不再额外启动一份与 PR 重复的检查。合并后的主分支仍独立验证，任务名称及正式发布门槛保持不变。研究集成与网络检查会取消已被新提交取代的运行，正式发布不会因此被取消。内部更新无需等待全部远端工作流；正式对外发布仍要求 `scripts/release-ci.mjs` 定义的准确提交 CI 证据。

在私有运维目录保留可重跑的实例检查脚本，将三个检查的真实执行结果绑定到该产物：

```bash
python3 deploy/internal/platform-internal.py check --bundle /private/ops/candidate --name source -- bash /private/ops/check-source.sh
python3 deploy/internal/platform-internal.py check --bundle /private/ops/candidate --name artifact-acceptance -- bash /private/ops/check-artifacts.sh
python3 deploy/internal/platform-internal.py check --bundle /private/ops/candidate --name recovery -- bash /private/ops/check-recovery.sh
python3 deploy/internal/platform-internal.py ready --bundle /private/ops/candidate
```

检查脚本由维护者审阅；不要用空命令或健康探针冒充完整验收。源码回执必须来自当前干净提交；产物验收必须加载同一镜像归档，在隔离数据上完成登录、权限及受影响的保存/刷新流程。恢复检查须验证当前实例适用的恢复点、数据库恢复、引用文件/协议包完整性和旧应用可用性，记录新增写入的处理方式。失败、缺失、超过 24 小时或摘要不一致的回执均阻止 `ready`；失败重试不会回退采用旧成功结果。

## 实例切换

`ready` 仅表示三类检查通过，工具不会自动切换生产。实例切换脚本属于私有运维适配，复用已有 Compose 和备份方式：

1. 再核对实际运行的源 SHA、配置摘要、数据库版本及基础服务镜像，拒绝准备之后出现的漂移。
2. 校验归档和镜像 ID；需要挂载源码执行器的部署，核对从该源码归档提取的文件，不能挂载任意工作区。
3. 取得最终一致恢复点；如需停写，记录时间。保存原配置、镜像和源文件，不更换数据库、存储或网络。
4. 使用准确镜像 ID，仅更新应用服务，禁止隐式拉取/构建或自动覆盖数据。启动失败时，在结构兼容的前提下恢复旧应用；不自动还原数据库、丢弃新增写入。
5. 核对版本、SHA、健康状态、原有数据及受影响用户路径。将实际结果写入私有部署记录。测试写入只能在明确隔离的合成测试资产中进行。

保留源码提交的可恢复副本、部署归档和配置的独立加密备份。此流程不负责替代备份系统；仅有同机文件不代表灾备。对外发版时再整理正式版本号、双语说明和完整公开产物。

## 新增数据表的内部更新

经核对的增量数据结构升级可在 `prepare` 时传入 `--migration-plan /private/ops/migration-plan.json`，走独立的迁移验证流程。计划必须写明准确的 `base_commit`、`target_commit`、`source_revision`、`target_revision`、全部 `changed_paths`，以及具体的 `backup_plan`、`migration_validation`、`rollback_policy` 和 `write_impact`。当前只允许新增迁移文件和修改模型注册；修改旧迁移、基础设施仍需另行制定过程。

计划完整保存在部署清单中，并额外要求 `check --name migration` 成功凭据：独立恢复原数据库、核对版本和原数据，使用候选镜像及源码执行升级，再验证数据与权限。缺少此验证不能部署。恢复方案也须核对应用权限：创建了受限会议后，不能退回不认识会议权限的旧应用；不能自动降级已有会议的数据表，也不能用旧备份覆盖更新后的新增资料。
