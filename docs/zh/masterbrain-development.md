# Masterbrain 同仓开发

Masterbrain 的维护源码位于 Platform 仓库。AI 核心、平台业务和前端可以在同一次修改中完成测试与交付，无需先发布 Python 或 npm 包。

## 目录与职责

| 目录                          | 职责                                                      |
| ----------------------------- | --------------------------------------------------------- |
| `packages/masterbrain`        | Python 模型适配、科研 AI 流程、提示词、服务端点与测试     |
| `packages/masterbrain-client` | TypeScript 客户端和从 Python 生成的修改契约               |
| `packages/masterbrain-vue`    | Vue 交互和修改审核组件                                    |
| `apps/api`、`apps/web`        | Platform 身份、权限、业务工具、存储、审计和 Aira 产品界面 |

模型输出由 Platform 校验后执行。共用源码不改变模型、工具与平台权限之间的边界。外部 MCP 与内置 Aira 继续复用 Platform 业务服务。

## 安装与开发

在仓库根目录运行：

```sh
corepack pnpm install --frozen-lockfile
uv --directory apps/api sync --locked
corepack pnpm masterbrain:build
```

API 的 `tool.uv.sources` 指向 `../../packages/masterbrain`，开发环境使用可编辑安装；前端消费者使用 `workspace:*`。`pnpm api:dev` 同时监听 API 和 AI Python 源码；修改前端 AI 组件后运行 `pnpm masterbrain:build`。无需发布或升级独立 Masterbrain 版本。Python 运行环境统一使用 `apps/api/uv.lock`。依赖变化仍需更新对应锁文件。

```sh
corepack pnpm masterbrain:test
```

Studio 停止主动维护，源码作为历史快照保留在原 Masterbrain 仓库。本次不迁移其前端、桌面启动器、打包流程、本地工作区和资料库端点。Platform 的 Aira 使用平台自己的身份、权限与业务存储。

共享结构有变化时运行 `pnpm masterbrain:contract:generate`，提交生成的 schema；`masterbrain:contract:check` 检查两端一致。`masterbrain:test` 默认排除标记为 `openai`、`qwen`、`e2e`、`integration` 的真实模型测试，并阻止未标记测试访问网络；通过离线测试不等于已验证某个模型服务在线可用。

## 构建、版本与部署

API Dockerfile 从仓库根目录构建：

```sh
docker build -f apps/api/Dockerfile -t platform-api-local .
```

生产安装使用锁定依赖和 `--no-editable`，将同仓 Python 源码构建成 wheel 安装进镜像；运行时不挂载开发目录，也不依赖相邻 Masterbrain 仓库。Web 镜像先构建同仓客户端和 Vue 组件，再构建 Platform。

产品发布身份为 Platform `VERSION` 与 Git SHA。迁入模块保留原包名及兼容版本元数据；不要求每次 AI 功能修改递增这些内部版本。两个 npm 包已标记为私有，Python 包标记为禁止公开上传，不从本仓库延续旧仓库的独立发布工作流。已发布的旧包不会被删除或覆盖。

外部 `MASTERBRAIN_CALL_MODE=external` 兼容路径保留。采用此模式的实例仍需要兼容的远端服务，更新 Platform 不会自动升级远端进程。默认包模式随 Platform 镜像一起更新。

迁移不改变现有数据库结构，也不重写聊天、Protocol 或 Record。源码迁移、提交、部署与旧仓库归档是不同操作。生产交付继续执行现有检查、备份和恢复要求。

## 来源与后续维护

来源是 `airalogy/masterbrain` 的 `fda4d56` 提交及迁移时已存在的字段填写修复。准确提交、初始文件哈希与路径映射见 `packages/masterbrain/migration-source.json`；该清单记录迁入基线，后续修改由 Platform Git 历史管理。迁移时保留的原始说明与变更日志位于 `packages/masterbrain/history`，属于历史资料，不是当前发版指引。Apache-2.0 许可证随源码保留。

今后的 AI 开发统一在本仓库进行。原 Masterbrain 仓库在迁移提交、验证及交接说明完成后归档，停止独立发版；Studio 保留历史代码，不再主动开发或接收 Platform 更新。历史提交、标签和已发布包继续保留。本次源码迁移不会自动更新公司实例。
