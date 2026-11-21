# 外部 Agent 接入

用户可以让 Codex 或其他 MCP 客户端访问本人获授权的项目。Platform 统一执行权限、严格数据校验和 Record 修订留痕。这些确定性操作不依赖 Aira、Masterbrain 或模型服务是否开启。

本功能覆盖 [Issue #11](https://github.com/airalogy/platform/issues/11) 和 [Issue #22](https://github.com/airalogy/platform/issues/22) 的科研闭环：限权读取、导入和修订、不可变分析快照、私有外部分析成果与经确认的 Protocol 发布。项目登记、经营收支和文件下载各有独立权限。

## 开启与连接

1. 组织所有者或管理员在**组织管理 → 设置 → 外部工具访问策略**开启访问，默认关闭。需先确认组织允许外部工具及其模型提供方处理返回的数据。
2. 可填写禁止外部读取的顶层 Record 变量 ID，每行一个，适用于整个 Lab，包括公共 Project。修改策略会使尚未执行的确认失效。
3. 进入**项目 → 分析 → 分析报告 → 连接外部 AI**，当前 Project 自动带入。选择**只读查看**、**分析并回存报告**或**编写协议**，核对显示的权限、填写授权名称及 1–90 天有效期。额外操作可通过**自定义权限**选择；**账号设置 → 外部 AI 工具**仍可跨项目管理连接。用户必须仍是 Lab 成员并有权访问该 Project；令牌不会扩大本人权限。
4. 令牌只显示一次，请安全保存。服务端仅保存 SHA-256 摘要。不要使用网页登录令牌或旧 API Key 替代。
5. 在客户端私密配置令牌。同源部署的 MCP 地址为 `https://your-platform.example/api/mcp`，设置页面会生成当前实例的连接命令：

```sh
codex mcp add airalogy --url https://your-platform.example/api/mcp --bearer-token-env-var AIRALOGY_PLATFORM_TOKEN
```

通过客户端的安全环境配置设置 `AIRALOGY_PLATFORM_TOKEN`。不要把令牌粘贴进对话、代码仓库、共享文档或连接命令。桌面应用不一定继承已打开终端的环境变量，配置后需从正确环境重启。客户端配置详见 [Codex MCP 文档](https://developers.openai.com/codex/mcp/)。

撤销后，后续调用立即失效，未执行请求同时取消。服务端每次重新检查令牌到期、账号凭据失效、Lab/Project 成员关系和策略。撤销前已经提交的操作仍是普通 Record，历史保留。

个人 SDK 密钥用于文件和实验记录接口。连接外部 AI 时请单独授权。在个人设置或 OAuth 确认页可选择单个项目、同一组织内的指定项目，或明确选择持续授权。「全选当前项目」只保存本次名单。「持续授权」在连接到期或撤销前，自动纳入账号以后在该组织获得访问权的项目。已有连接保留原授权范围。多项目连接先调用 `list_authorized_projects`，再将选定的 `project_id` 传给项目工具。每次调用都检查当前账号的项目权限，财务操作还会检查对应项目的账簿角色。

## 为自己的账号连接外部 AI

组织开关允许成员建立连接。每位成员在自己的账号设置中授权，连接使用该成员当前的项目和业务权限。客户端共用同一个 MCP 地址，各成员分别登录授权或私下配置自己的令牌。请勿共用令牌。可以先调用 `access_context` 核对账号、目标和授权范围。在客户端刷新工具列表可查看连接目前支持的操作。服务端会在每次调用时重新校验，即使客户端还保留着旧工具列表。

| 要做的事 | 设置入口及权限 | 调用 |
| --- | --- | --- |
| 查项目、建私有项目 | 账号设置 → 外部 AI 工具 → 组织建项。组织所有者或管理员选择一个组织，勾选查找、创建所需权限 | `find_organization_project`、`create_private_project` |
| 查项目收支、净现金 | 为目标项目创建连接，选择「查看项目收支」。账号须有项目访问权和已启用账本的经营角色 | `list_project_cash` |
| 登记实际到账或付款 | 财务成员在同一项目的「自定义权限」中勾选「登记项目收支」 | `record_project_cash` |

例如先用 `{"by":"contract_number","query":"DEMO-001"}` 查重。支持精确项目名、标识和已登记的合同号。建项需要稳定的 UUID 格式 `request_id`、项目 `uid` 和 `name`，可附 `description`、`contract_number`。合同号用于查重和查找，签约状态仍由商务流程记录。成功后打开返回的项目链接核对，按需在平台启用账本和分配财务角色。

同一账号需要同时处理合同和收支时，在该项目的经营设置选择「负责人兼财务」。在原有 MCP 连接上重新授权同一项目，勾选「查看项目合同及收款汇总」「登记已签合同」「查看项目收支」和「关联已有收入到合同」。还要录入新流水时再勾选「登记实际收付款」。先用 `list_project_contracts` 按合同号查重，再用 `register_project_contract` 填入含税金额及实际签署日期。通过 `list_project_cash` 取得已有客户收入的 ID 和版本，调用 `link_project_receipt` 后回读原流水及合同汇总。每次写入使用独立的 request_id，重试原操作时沿用该 ID。

收支金额使用人民币整数分。例如收到 100 元，发送 `{"request_id":"11111111-1111-4111-8111-111111111111","cash":{"kind":"cash","title":"示例收款","day":"2025-01-10","direction":"in","receipt_purpose":"customer_receipt","amount":10000}}`。每笔新业务生成新的 UUID；网络重试沿用原请求与 UUID。相同请求返回原结果，修改内容后复用 UUID 会被拒绝。客户回款用途为 `customer_receipt`，押金退回等其他收入用 `other_income`，并计入现金流。支出方向用 `out`。核对返回的账本链接，或用 `list_project_cash` 检查总收款、总付款及净现金。

支持 MCP 的客户端连接当前实例的 `/api/mcp`。使用受限令牌的 HTTP 客户端也可以向 `/api/external-access/tools/<工具名>` POST 同一份 JSON。OAuth 客户端在发起授权时分别请求组织权限 `projects:find projects:create` 或项目权限 `cash:read cash:create`，在浏览器完成个人授权。管理员撤销成员角色或关闭账本后，原连接的相应操作立即失效。

## 查看报告和确认操作

回到**项目 → 分析 → 分析报告**，按时间倒序查看报告，按标题搜索已加载结果，或点击**加载更早的报告**继续浏览。打开报告即可查看方法、局限、准确来源快照并下载附件。报告仍仅提交者本人可见；入口放在项目内不代表自动向所有项目成员共享。

待确认操作显示在报告列表上方。工具返回的确认链接会直接打开当前项目中的对应请求，保存结果链接会打开对应报告。已完成操作可单独展开查看。通过**管理连接**撤销当前项目凭据，或到账号设置跨项目管理。连接检查仅证明令牌能访问平台，不代表外部客户端已经配置完成；请在客户端使用向导提供的只读探索任务开始验证。

## 完成一次导入

让已连接工具依次执行：

1. 调用 `access_context`、`list_protocols` 和 `get_protocol`，确认保存位置并取得标准 CSV 表头。
2. 按准确的 `var.<id>` 表头整理 CSV。显示名称、近似名称不能作为自动映射；不得猜测补值、缺失分数补零或放宽 Protocol 校验。
3. 调用 `preview_import`，传入 Protocol ID、CSV 文本和唯一 `request_key`。平台复用现有导入器逐行校验；失败时返回有限的错误行、字段及类型，**不创建任何 Record**。
4. 用户本人打开返回的确认链接，在 Platform 登录创建令牌的同一账号，核对保存位置、记录数、Protocol 版本和完整 CSV，然后确认或拒绝。**外部令牌不能自行确认写入。**
5. 回到外部工具，以操作 ID 调用 `execute_operation`。执行时不能替换输入；成功返回已保存的 Record ID 和页面链接。

确认请求从预览开始 15 分钟后失效，用户确认不延长有效期。这是临时操作请求，不是 Record 草稿。修改输入需重新预览并使用新请求键；相同请求键和相同输入返回同一请求，换输入会返回 `409`。重复执行已完成操作返回原结果，不会再次导入。遇到网络中断应先查状态，不要直接创建新的导入请求。

## 修订记录

`list_records` 仅返回本人有权读取的最新版本。调用 `preview_revision`，提供 `record_id`、`protocol_id`、`expected_version`、待修改变量 `changes`、有意义的修订原因 `reason` 和新 `request_key`。保持现有 Platform 规则：只有原记录者可以修订自己的记录。 若最新版本已删除，列表也会隐藏该 Record 保留的历史版本。

用户在网页核对修改前后值并确认，执行后生成修订版本，保留原版本和原因。如果期间产生了新修订，执行会失败，需读取最新状态重新预览。外部通道没有删除操作。

## 范围与限制

- 项目连接可以授权单个项目、固定名单或同一组织内持续可访问的项目。组织建项使用单独的组织授权。每项操作都需要相应权限，例如修订实验记录同时需要 `records:read` 和 `records:revise`。
- API 同时检查 Lab 字段限制及现有 Protocol/Record 权限。公共可见性不能绕过 Lab 成员资格或外部访问策略。
- Protocol 读取只提供字段 ID、标题、必填状态、基本类型和支持的校验限制。不返回 AIMD、执行代码、环境变量、模型提示、默认值或示例值。CSV 模板仅含表头。
- Record 默认开放基本类型变量及支持的日期时间字符串。明确授权 `records:complex` 后，可读取具有明确结构的数组和对象，最多四层；不支持的引用、资源、文件类型和值仍不返回。附件走独立文件接口，不返回长期下载地址。含文件地址的字符串被省略，并在 `withheld_fields` 标明，不会改写成科学意义上的空值。工具不得推测被省略内容。
- Protocol 含受限或不支持的复杂变量时，必须回到正常网页导入或修订，首期不对这类 Protocol 做部分写入。外部导入不会向校验器注入用户的完整旧 API Key 或 Protocol 环境机密；依赖这些凭据的校验需使用正常网页路径。
- CSV 最大 1 MiB，完整请求体最大 2 MiB，流式上传同样受限。保留现有行数限制。列表每页 50 条，通过 `next_offset` 翻页。每个令牌最多 10 个待确认/已确认请求，每个用户最多 50 个有效授权；已认证工具调用按用户限制为每分钟 120 次已记录活动。
- 外部 API 日志不记录令牌或 CSV/Record 请求正文。审计记录包含用户、授权、操作及结果引用，不包含输入值。校验错误只公开有限的行/字段位置和类别，不透传自定义校验器可能包含机密的文本。
- 执行、拒绝、撤销后清除确认请求正文；过期正文在访问过期请求时延迟清除。修订摘要仍是私有数据，读取需重新鉴权，不属于公开活动流。

## 接口约定

公开反向代理在以下应用路径前加 `/api`：

| 接口 | 认证 | 用途 |
| --- | --- | --- |
| `GET /external-access/dashboard` | 网页 `Auth-Token` | 本人授权、确认状态与审计 |
| `GET/PUT /external-access/labs/{id}/policy` | 网页，Lab Owner/Manager | 读取策略、携带期望版本更新 |
| `POST /external-access/grants` | 网页 | 一次性签发限权令牌 |
| `DELETE /external-access/grants/{id}` | 网页，令牌所属用户 | 撤销及取消待执行写入 |
| `GET /external-access/operations/{id}` | 网页，令牌所属用户 | 查看完整预览 |
| `POST /external-access/operations/{id}/decision` | 网页，令牌所属用户 | 以准确 `digest` 和 `approve` 确认/拒绝 |
| `POST /external-access/tools/{name}` | 限权 Bearer 令牌 | JSON 参数调用确定性工具 |
| `POST /mcp` | 限权 Bearer 令牌 | 无状态 Streamable HTTP MCP |

MCP 工具有 `access_context`、`list_protocols`、`get_protocol`、`list_records`、`preview_import`、`preview_revision`、`operation_status`、`execute_operation`。客户端通过发现接口获取参数结构；额外参数会被拒绝，执行工具只能携带操作 ID。发现工具不等于获得相应权限。

MCP 使用 JSON 响应，客户端需接受 `application/json, text/event-stream`；Origin 必须与 `SITE_URL` 一致，协商支持的协议版本，支持的通知返回 `202`。不创建会话 ID，不提供旧 SSE 通道或主动服务端请求，GET/DELETE 返回 `405`。工具失败以 `isError: true` 返回；直接 HTTP 调用使用 `401`、`403`、`404`、`409`、`413`、`422`、`429` 等状态。执行器的非标准错误提示用户回到正常网页检查，避免透传机密异常文本。

写入、幂等结果和审计在同一事务提交。锁定顺序为用户调用门控 → Lab 策略共享锁 → 令牌 → 操作 → Protocol → Record；普通网页 Record 修订同样锁定稳定的 Protocol，并可传入 `expected_version`。不同 Lab 成员的调用不需竞争整个实验室的独占锁。外部工具不能发送 SQL、指定任意服务端请求地址、修改成员或权限、执行仪器。

## 部署与后续

完整功能上线需执行至 `0097_external_project_coverage` 迁移，并部署匹配的前后端构建，遵循现有发布、备份和验证流程。本文不代表已授权或已完成线上升级。既有 Lab 默认仍关闭外部访问。独立 `mcp` 客户端仅是开发/测试依赖，生产传输使用现有 FastAPI。

集成测试覆盖真实迁移往返、CSV 校验、失败回滚、并发重试、修订历史、权限变化、过期、数据限制及独立 MCP SDK。浏览器测试覆盖中英文、手机/桌面下创建授权、确认和撤销；无需生产或客户数据。

变更通知采用 `snapshot_changes` 主动查询，不自动启动重跑。推送 Webhooks、动态 OAuth 客户端注册、刷新令牌、远程任务执行和自动公开到共享 Knowledge 不在当前范围；它们是独立扩展，不影响下述分析和 Protocol 闭环。

## 外部分析与成果回存

从**项目 → 更多 → 连接外部 AI**进入，也可在账号设置进入。创建凭据前可确认目标项目及操作范围；令牌显示期间可点击测试连接。

| 新增权限 | 能力及实际权限要求 |
| --- | --- |
| `records:export` | 创建数据快照，同时要求 `records:read` 及已有导出权限（Lab Owner 或 Project Owner/Manager）。能读取不代表能导出。 |
| `analysis:write` / `analysis:read` | 提议保存/读取本人的外部成果，仍需数据导出权限及当前来源读取权限。 |
| `protocols:source` | 下载准确版本的源码，与字段结构读取独立。源码本身可能包含保密研究文本。 |
| `protocols:candidate` / `protocols:publish` | 校验候选/确认后发布；须有源码权限及常规创建、修改协议权限。 |
| `records:complex` | 有明确结构和深度上限的数组、对象；不隐含附件内容读取。 |
| `knowledge:read`、`documents:read`、`materials:read` | 当前 Project 的知识、文档或资料。个人、其他项目和 Restricted 内容保持原有权限。 |
| `files:read` | 显式选择并按校验和读取附件，还须有父对象能力与读取权限；Record 附件另需导出权限。 |

1. 检查上下文和字段字典。以新 `request_key` 和 `sources: [{protocol_id, fields, records?}]` 调用 `create_snapshot`。`records` 可明确选择 `{id, version}`；省略时取创建瞬间的可读最新修订。最多 16 个 Protocol，每个选择 100 个字段，共 2,000 条 Record、16 MiB。每页 50 行，始终来自同一快照，带准确 Record/Protocol 版本、字段字典、缺失/不支持/受限状态及摘要。未确认快照 24 小时到期，每人最多 20 个有效快照。
2. 由外部工具实际计算。不同 Protocol 默认分开，合并分析须明确连接键、单位和一对一/一对多关系。`list_context_assets` / `read_context_asset` 读取另行授权的上下文，后续文本页须携带原摘要。`list_record_files` 和 `read_research_file` 先取元数据，再以 `expected_sha256` 分块下载：单文件最多 16 MiB，每块 256 KiB。不提供任意 URL 抓取和带机密的执行环境。
3. 调用 `preview_analysis`，传入快照 ID/摘要、标题、问题、报告、方法、参数、环境、执行工具、限制、`execution: computed | interpretation_only`、新请求键和可选文件 `{filename, kind, content_base64, sha256}`。最多 20 个文件、总计 1 MiB，支持 `.py`、`.json`、`.csv`、`.txt`、`.md`、`.png`、`.jpg/.jpeg`。代码仅保存，不在此接口执行。重跑时用 `rerun_of_id` 关联原成果。
4. 用户在 Platform 阅读完整报告、来源、限制和可下载文件，并确认准确版本。随后 `execute_operation` 在同一事务保存普通私有 `AnalysisRun`、版本化 `AnalysisPipeline` 方法和文件引用。重跑生成新成果，保留旧成果；相同方法复用版本，方法改变生成下一版。网络中断后可安全重试，不重复创建。
5. 通过返回链接查看成果。保留来源摘要、文件校验和、环境和重跑关系。明确标记**外部计算，平台尚未复现验证**；缺少代码或环境时显示复现信息不完整。公共项目中的成果同样默认仅提交者可见；来源权限撤销后，报告和下载都不可继续读取。单独读取的上下文不会自动纳入 Record 快照，应在回存方法/报告中保留相关来源标识与摘要。暂不允许通过现有发布接口自动扩散到共享 Knowledge，待有明确的来源感知发布流程后再扩展。

已确认快照与成果一同保留，到期不会删除正式科研资产。撤销令牌阻止进一步委托调用，不删除用户本人已接受的成果。Lab 策略改变后，继续外部分析需新建快照。`snapshot_changes` 查询后续修订/新增，不改变旧快照、不自动启动工作；已删除或不可访问的来源会拒绝读取。

## 本地编写 Protocol

以 `{protocol_id, version, format: "aira" | "zip"}` 调用 `download_protocol_source`。归档来自不可变的已发布版本，不读取执行器工作目录。源码读取不等于有权发布。

使用官方 Airalogy Python 语法/Assigner 检查及下述本地预览，然后调用 `preview_protocol_candidate`。输入新请求键、`files`（相对路径的 UTF-8 文本）和可选 `binary_files`（base64 图片/PDF），或用 `archive_base64` 提交 `.aira`/ZIP。最多 50 个文件、解压后 1 MB；拒绝隐藏路径、符号链接、重复/危险路径和伪装图片。修改已有 Protocol 必须带 `protocol_id` 和准确 `base_version_id`，新建时两者都省略。

平台执行官方静态检查和隔离执行器校验，不注入委托用户的旧 API Key 或 Protocol 环境机密。网页展示源码差异、二进制附件摘要与下载、保存位置、目标版本和结构兼容报告。确认和执行再次核对来源摘要、权限和基础版本；并发发布产生冲突时须重新预览。发布生成普通 Protocol 新版本，已有 Records 保持原协议版本。外部工具无法自行确认或发布未经审阅的输入。

## 本地客户端与预览

Platform 源码中的标准库 Python 客户端既可 `from tools.airalogy_agent import Client` 导入，也可直接运行。要求 Python 3.11+；`check`、`candidate` 另需官方 `airalogy` 包。为保持一致，可使用 API 环境（在 `apps/api` 下用 `uv run`）。本地静态检查不会导入执行用户的 Protocol Python。

```sh
python3 tools/airalogy_agent.py --instance https://your-platform.example context
python3 tools/airalogy_agent.py --instance https://your-platform.example snapshot selection.json snapshot.json
python3 tools/airalogy_agent.py check ./my-protocol
python3 tools/airalogy_agent.py --instance https://your-platform.example candidate ./my-protocol --protocol-id UUID --base-version-id UUID
python3 tools/airalogy_agent.py --instance https://your-platform.example status OPERATION_UUID
# 用户已在网页确认后：
python3 tools/airalogy_agent.py --instance https://your-platform.example execute OPERATION_UUID
pnpm agent:preview:build
pnpm agent:preview
```

具体参数见 `--help`。`call TOOL request.json` 调用与 MCP 相同的类型化 HTTP 工具。凭据来自 `AIRALOGY_PLATFORM_TOKEN` 或私有 `AIRALOGY_PLATFORM_TOKEN_FILE`，不接受命令行明文令牌。除本机回环开发地址外要求 HTTPS，拒绝重定向，下载校验摘要且不覆盖已有文件。

预览地址为 `http://127.0.0.1:3109/agent-preview.html`，复用官方 `AimdEditor`、`AimdRecorder` 和示例数据生成，支持打开、编辑、下载 AIMD 与测试内联字段，不上传、不创建 Record。Python 模型和服务端 Assigner 仍需平台校验。服务器仅监听回环地址，禁用目录浏览和外部连接，不应对公网开放。

## 浏览器授权（OAuth + PKCE）

在账号设置注册公共客户端名称和准确回调地址。回调要求 HTTPS 或字面量本机回环 HTTP 地址，不允许用户名密码、查询参数、片段。返回客户端 ID，不生成客户端机密。在受控本地终端执行：

```sh
python3 tools/airalogy_agent.py --instance https://your-platform.example login --client-id CLIENT_UUID --scopes 'protocols:read records:read records:export analysis:read analysis:write' --token-file /private/path/platform-token.json
```

默认 CLI 回调须注册 `http://127.0.0.1:8765/callback`。网页展示客户端、实例、操作范围、Project、1–7 天有效期并要求显式确认。采用 S256 PKCE、state 校验、准确回调/资源绑定、5 分钟单次授权码和资源限定令牌。凭据文件以仅本人可读写权限独占创建；拒绝过期、其他用户拥有或权限过宽的文件。撤销客户端同时撤销其关联令牌和待执行操作。不提供自动刷新或动态注册；不支持预注册的客户端可用限权 Bearer 令牌接入。

发现接口位于 `/.well-known/oauth-authorization-server` 和 `/.well-known/oauth-protected-resource/api/mcp`。除 `/api/*` 外，反向代理还须将这两条路径转发 API；随附 Caddy 配置和开发代理已包含。`SITE_URL` 须与实例公开 origin 一致。为 `/api/mcp` 签发的令牌不能调用 `/api/external-access`，反之亦然。HTTP 与 MCP 共用校验、权限、确认、审计和幂等规则；特定桌面客户端能否直接使用 OAuth，取决于其预注册客户端支持。

## 真实 Codex 验收（手动启用）

`pnpm agent:codex:test` 使用本机已安装并登录的 Codex CLI，通过真实 MCP 连接独立的本地 Platform。这项验收与单元测试分开，不自动加入提交、推送或 CI 检查。模型调用会消耗当前账号用量，账号、网络或模型服务不可用时也可能失败。

前提：安装锁定的工作区依赖、Playwright Chromium 和 `apps/api/.venv` 中的 API Python 环境；Codex CLI 支持 `exec --ignore-user-config --ephemeral`；独立开发实例已准备标准 `dev_owner` / `dev_lab` / `quickstart` 虚构夹具。只在该**测试实验室**启用外部访问，并保持屏蔽字段为空。脚本拒绝非本机回环地址和未启用开发夹具的实例，不自行修改实验室策略；网页地址必须与实例的 `SITE_URL` 一致。Platform 的 AI 可保持关闭，以验证外部工具路径能够独立工作。

```sh
pnpm agent:codex:guards
AIRALOGY_CODEX_LIVE=1 \
E2E_API_URL=http://127.0.0.1:4108 \
E2E_WEB_URL=http://127.0.0.1:3108 \
pnpm agent:codex:test
```

测试新建私有的虚构项目，验证以下流程：

1. 真实 Codex 发现已授权的 Protocol，建立不可变数据快照，并用 Python 对返回值实际计算。
2. 未确认的写入被拒绝；独立浏览器会话代表测试用户查看并确认报告，然后由 Codex 保存、读回报告与代码附件。
3. Codex 下载指定 Protocol 版本，在本地修改并运行官方语法检查，提交候选版本；浏览器确认后通过 MCP 发布。重复执行得到相同回执，原有 Records 仍绑定原版本。
4. 撤销令牌后 MCP 拒绝访问。成功或普通失败结束时，脚本都会撤销本次创建的授权。

只有夹具准备和独立断言使用直接 HTTP，Codex 对 Platform 的访问必须经过 MCP。测试用户的自动点击仅用于这组虚构夹具，不代表允许外部 Agent 替真实用户确认写入。脚本不修改 Codex 全局配置，不把 Platform 令牌放入模型提示或 Shell 子进程；保留虚构资产供检查，并输出私有临时证据目录，含回执、脱敏客户端事件和浏览器截图。不要将该目录提交到仓库。如果进程被强制终止，请先在测试账号设置中撤销残留的 `Synthetic Codex` 授权，再重试。

## 日常会议与研发事项

连接用途中的“会议与研发事项”授予当前项目的 `collaboration:read` 与 `collaboration:write`。这两项独立于 Protocol 权限，不要求先建协议或启用 AI。已有连接不会自动取得新权限，需要另建相应授权。

可用工具包括 `list_projects`（仅返回此连接授权的项目）、`list_project_people`、 `create_project_person`、会议的查询/读取/创建/更新，以及研发事项的查询/读取/创建/更新。 `create_meeting_with_actions` 原子保存纪要和行动项；`save_meeting_actions` 批量创建或关联已有事项。写入返回实际保存对象、版本和可打开的链接。

普通协作写入在明确授权范围内直接保存。先读再改，更新需携带当前版本；创建和批量请求使用稳定 UUID，重试复用原 ID，遇到冲突先重新读取，不生成新 ID 来掩盖失败。账号关联、权限调整和删除仍在平台中单独处理。Protocol、Record 与分析结果的既有预览/确认流程保持不变。

平台页面的授权检查只证明平台和凭据可用。客户端是否已连接，应由客户端成功列出工具并调用 `access_context` 来验证；该结果同时说明实际项目、权限、部署版本及可用协作工具。
