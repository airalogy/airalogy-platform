# 组织与单机构工作空间

Airalogy Platform 的组织可以是公司、研究机构或独立实验室。组织负责成员、项目归属和权限边界；Project 是日常工作的主要入口。组织单元用于可选的人员分组，不要求经过部门或实验室才能进入项目。类型不限制 Protocol、文档、知识或场景套件能力。

这是 Issue #25 的首期兼容实现。研发任务、里程碑与团队协作工作台由 #26 继续实施；此功能不要求安装 BD 或身份中心。

## 新建公司部署

复用同一套单实例部署服务与操作脚本，无需公司版分支。目录名 `deploy/single-lab` 暂时保留以兼容已有运维流程。

```sh
bash deploy/single-lab/scripts/generate-env.sh \
  --organization-name 'Example R&D' \
  --organization-uid example_rd \
  --organization-type company \
  --site-url https://research.example.org \
  --tls-email admin@example.org
```

随后按[单实例部署指南](./single-lab-deployment.md)完成网络预检、备份与启动。生成配置使用 `DEPLOYMENT_MODE=single_organization`；前后端通过 `/instance` 的能力信息决定行为。首次访问 `/setup` 时可确认名称与类型并创建首位管理员；标志可在“组织管理 → 设置”上传。

组织名称是可修改的显示名称；组织标识（UID，例如 `example_rd`）由部署配置 `SINGLE_ORGANIZATION_UID` 确定，默认 `main`。初始化页展示只读标识供管理员确认，提交时核对当前部署值；配置若已变化会拒绝初始化，且不创建账号或组织。需要调整标识时，应在首次初始化前修改配置并重启服务。组织创建后标识只读，用于链接及 Protocol 标识；数据库内部 UUID 自动生成，无需填写。该页面不支持在线修改部署配置或重命名已有组织标识。

- 登录后直接进入最近项目和个人工作，不再选择唯一组织。
- 默认项目为私有的 `workspace`（Team Workspace）；可创建自己的研发项目。
- 新公司模式的邀请默认授予项目“协作者”，管理员可以在确认邀请前选择其他角色；旧 `single_lab` 的默认“记录者”保留。已有成员角色不会变化。
- 个人文档仍仅自己可见；组织类型不会把个人资料或 Restricted 内容公开。组织管理员与项目角色的既有权限规则继续由 API 执行。
- 公司、机构使用组织文案；实验室类型仍使用实验室文案。名称、标志、组织类型可在设置中修改，依旧由既有所有者权限控制。
- AI 关闭时仍可创建项目、编写文档、使用 Protocol 和填写 Record。

## 旧部署如何升级

先完成备份及隔离升级演练，再按正常发布流程升级。**不要重新初始化已有实例，不要更改原来的 UID，也不要重新创建用户。**

迁移 `0085_organization_foundation` 给原 `labs` 表增加有约束的 `organization_type`，所有原有数据默认 `laboratory`。UUID、成员、外键、项目与科研资产不搬迁，权限表不改写。首次初始化在任何用户或组织已存在时仍被拒绝。

若把已有单实验室实例用作公司工作空间，可以在升级验证后把模式改为 `single_organization`，保留原 UID 和默认项目 UID；组织类型在设置中显式改为“公司”。已有实例的类型以数据库为准，环境配置只提供初始化默认值。切换部署模式会改变以后邀请的默认项目角色，应在发邀请前核对；不会修改已签发邀请或现有授权。

| 通用配置                                   | 兼容旧配置                        |
| ------------------------------------------ | --------------------------------- |
| `SINGLE_ORGANIZATION_UID`                  | `SINGLE_LAB_UID`                  |
| `SINGLE_ORGANIZATION_NAME`                 | `SINGLE_LAB_NAME`                 |
| `SINGLE_ORGANIZATION_DESCRIPTION`          | `SINGLE_LAB_DESCRIPTION`          |
| `SINGLE_ORGANIZATION_DEFAULT_PROJECT_UID`  | `SINGLE_LAB_DEFAULT_PROJECT_UID`  |
| `SINGLE_ORGANIZATION_DEFAULT_PROJECT_NAME` | `SINGLE_LAB_DEFAULT_PROJECT_NAME` |
| `ORGANIZATION_STRUCTURE_MODE`              | `LAB_STRUCTURE_MODE`              |

两种名称不能配置不同值；应用启动将明确报错。`SINGLE_ORGANIZATION_TYPE` 接受 `company`、`institution`、`laboratory`、`other`。原配置不必改名即可运行；多组织 `community` 模式和旧实验室导航保持兼容。

## 接口与存储契约

- 新代码可用 `Organization`、`OrganizationMember`、`OrganizationRole`；它们与原 Lab 使用**同一 ORM 映射**。`Project.organization_id` 和成员的 `organization_id` 是原 `lab_id` 的映射别名，不是第二套归属。
- `/organizations` 支持列表、创建、按 UUID/UID 读取、更新；`/{organization_id}/members` 支持成员读取与维护，复用原有授权处理函数。单机构仍须通过邀请加入，不能利用成员接口绕过邀请。
- `/projects` 创建请求接受 `organization_id` 或 `lab_id`；两者同时传入且不同则拒绝。项目响应保留 `lab_id` 并提供同值 `organization_id`。
- `/instance` 增加 `single_organization`、`organization`、组织结构与默认值，同时保留 `single_lab`、`lab` 作为能力兼容字段。`single_lab=true` 也表示新单机构模式，不再仅代表组织的业务类型。
- 旧 `/labs` API、前端深链、scope 值 `lab`、SDK、MCP、队列键与审计记录暂时保留，仍指向相同资产。专项资源接口继续使用现有路径。
- `airalogy.id.lab.…` 的已发布协议标识、包、历史 Record 引用**不改写**。引入 `.org.` 格式需要先协调 SDK 读写能力，单独验收；当前不需要升级 Airalogy 包。

## 迁移影响与恢复

| 范围                                  | 首期处理                                          |
| ------------------------------------- | ------------------------------------------------- |
| 数据表、索引、外键                    | 新增类型字段与约束，保留物理 `labs`/`lab_id` 名称 |
| 权限、组织单元、个人／Restricted 范围 | 保留原授予关系与判断，不因类型切换增加权限        |
| API、前端、配置                       | 增加明确兼容适配；旧入口保留                      |
| Protocol 公开 ID、归档、SDK、MCP      | 继续原格式和引用，后续协调                        |
| 队列、缓存、持久事件、审计正文        | 不全局替换 `lab` 字符串                           |
| 备份及部署身份                        | 继续同一备份机制，配置摘要覆盖新增组织配置        |

在隔离副本上对比 UUID、项目/成员数量、权限与版本引用后再切换生产。恢复使用验证过的数据库恢复点与匹配应用制品；新增组织类型为非实验室时，降级迁移会阻止丢弃类型信息。应先评估切换后的新增写入，再决定恢复备份或明确调整类型，不能把切换旧镜像当作完整数据库回滚。

本地验收包含旧 schema 升降级、UUID/外键保留、新旧 API 同权、首次公司初始化、邀请默认值、个人文档隔离、公司/实验室浏览器回归。生产恢复演练仍需使用目标实例的真实备份，不能由本地合成数据测试替代。

组织名称去除首尾空白后允许 1–64 个字符；组织标识和个人用户名仍使用各自的规则。所有者与管理员可从页头的“组织管理”进入，手机端在菜单第一级；普通成员保留原有成员查看入口。个人账号设置与系统运维仍分别管理。
