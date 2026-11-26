# 单机构存储与备份

## 安装时选择数据盘

在 Linux 部署主机上挂载数据盘，在盘上建一个空的专用目录，例如 `/srv/airalogy/data`。生成部署配置后，在 `deploy/single-lab/.env` 设置 `AIRALOGY_DATA_ROOT=/srv/airalogy/data`，在该目录下的部署命令均从 `deploy/single-lab` 执行：

```bash
./platformctl storage-init
./platformctl install
```

根目录下的 `postgres_data` 存放数据库，`minio_data` 存放对象，另有协议工作目录、应用日志和 Caddy 状态。控制工具会核对部署标记。已有命名卷部署继续沿用原配置。迁移已有实例时先备份，再在干净的新部署选择数据盘并恢复。请保留旧实例到新实例验收通过。

## 登记备份盘

现有 `platformctl backup` 继续在 `BACKUP_DIR` 生成可搬走的完整目录。专用备份盘可在该目录放置 `.airalogy-backup-disk` 文本文件，将其内容设置为部署配置的 `BACKUP_DISK_ID`。盘未挂载或身份不符时，本次备份会停止。手工目录含部署密钥，应限制读取并加密离机保存。手工和升级回退备份由运维保管，不参与下述轮换。

定时备份使用主机上的 **restic**。每个目标是一个独立的加密仓库，可以放在第二块物理盘，也可以放在已经挂载的异机存储上。本机两个目录可能共用同一物理盘。请先在操作系统确认盘已正确挂载，再初始化仓库。以下路径仅作示例：

```bash
umask 077
mkdir -p /etc/airalogy-backup /srv/airalogy/staging
chmod 700 /etc/airalogy-backup /srv/airalogy/staging
openssl rand -base64 32 > /etc/airalogy-backup/disk.key
restic -r /mnt/backup/airalogy --password-file /etc/airalogy-backup/disk.key init
sha256sum /mnt/backup/airalogy/config
```

将校验值和路径写入部署主机上的 `/etc/airalogy-backup/targets.json`，限制为运维账号可读。请独立保存密钥和部署标识。仓库密码无法从仓库本身找回。

```json
{
  "staging": "/srv/airalogy/staging",
  "reserve_mib": 256,
  "targets": {
    "disk_b": {
      "name": "本地备份盘",
      "repository": "/mnt/backup/airalogy",
      "password_file": "/etc/airalogy-backup/disk.key",
      "config_sha256": "<上一步的 64 位校验值>"
    }
  }
}
```

增加目标时在 `targets` 中登记另一个仓库。若临时采集目录也在可拆卸磁盘，在该目录放置 `.airalogy-backup-disk` 标记，并在 JSON 顶层填写匹配的 `staging_disk_id`。临时目录需要容纳一次完整数据库导出、对象副本和预留空间。仓库只写入新增数据。每次采集会暂停 API，直到数据库导出和对象复制完成。暂停时间取决于数据库、附件总量和磁盘速度。先在维护窗口完成一次采集并记录用时，再选择合适的频率。加密、回读校验及清理旧备份在服务恢复后进行。

## 开启定时任务与管理页面

在部署配置的 `BACKUP_OPERATOR_IDS` 中填入获授权账号的 UUID（多个用逗号分隔），并按正常运维流程重新创建 API 容器以加载配置。账号还须是该单机构的所有者或管理员。多组织部署不提供整机备份界面。

先执行一次 `./platformctl backup-tick /etc/airalogy-backup/targets.json --now`。在具备 Docker 权限的运维账号的 crontab 中每分钟执行以下命令，将示例替换为实际安装路径，确保 cron 的 PATH 包含 docker、python3 和 restic。每分钟仅检查任务，采集频率由页面的策略决定。每个实例只配置一个调度器：

```cron
* * * * * /opt/airalogy/deploy/single-lab/platformctl backup-tick /etc/airalogy-backup/targets.json
```

在 **组织管理 → 设置 → 存储与备份** 选择目标、频率和保留份数。默认每天服务器时间 02:00，在每个有备份的日子留一份，保留最近 7 个日点和 4 个周点；同一恢复点只占一份。每小时模式额外保留最近 24 个小时点。仅手动模式仍可点击立即备份。页面显示各目标的容量、最近成功和失败原因。断盘或可用空间不足时，先处理该目标，再单独重试。新恢复点逐文件回读校验成功后才清理该仓库中的旧自动备份。

## 换机与恢复演练

1. 计划换机时，在旧机停止业务录入，执行最后一次备份并核对结果。记录部署 ID、版本和快照完整 ID。可通过 `restic -r <仓库> --password-file <密钥文件> snapshots --host <原部署ID> --tag airalogy-managed --json` 获取完整 ID。
2. 在能读取备份仓库的运维主机上执行 `./platformctl backup-export /etc/airalogy-backup/targets.json disk_b <完整快照ID> /private/recovery-point`。导出使用源部署的 `AIRALOGY_DEPLOYMENT_ID`，无需源 API 或原临时盘在线。在新机的注册配置里填入离线副本的实际仓库路径和密钥文件路径，沿用原仓库校验值。目标目录须尚未存在。导出结果包含解密后的部署密钥和业务数据，使用私有目录和加密传输。
3. 在新服务器准备相同版本的 Platform，将导出的 `secrets.env` 作为配置起点，保留 AES 密钥，核对新机的数据盘、状态目录、网段、镜像和站点地址。若配置新的数据根目录，先执行 `storage-init`。运行 `./platformctl restore /private/recovery-point`。旧版完整备份目录也可使用同一恢复命令。
4. 用原账号登录，核对项目权限、打开协议和记录、下载附件并比对内容。确认后再切换入口。完成独立恢复演练后，由运维在受管实例执行 `./platformctl backup-drill /etc/airalogy-backup/targets.json disk_b <完整快照ID>` 登记实际验收结果。页面分别记录备份校验和人工恢复演练。

数据库包含账号、权限和记录，对象仓库包含附件与协议包。可重新下载的协议工作副本、镜像、日志、TLS 运行状态及主机的 cron、仓库注册配置与备份密钥另行管理。部署管理员应保管独立的配置副本并定期演练离机恢复。
