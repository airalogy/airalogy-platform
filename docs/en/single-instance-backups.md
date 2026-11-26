# Single-organization storage and backups

## Choose a data disk

On a Linux Docker host, mount the disk and create an empty application directory. Set `AIRALOGY_DATA_ROOT` in the generated deployment environment to its absolute path. From `deploy/single-lab`, run `./platformctl storage-init` and then `./platformctl install`. PostgreSQL, MinIO, protocol work files, application logs and Caddy state use separate subdirectories. The lifecycle tools check the disk identity. Existing named-volume installations can continue unchanged. To move an existing installation, capture a backup and restore on a clean target. Retain the source until acceptance.

## Register backup destinations

`platformctl backup` continues to write a portable directory under `BACKUP_DIR`. On a dedicated disk, put an identifying string in `BACKUP_DIR/.airalogy-backup-disk` and configure the same `BACKUP_DISK_ID`. Manual and pre-upgrade backups are outside automatic retention. These portable directories contain plaintext deployment credentials.

Install restic on the operator host. Register independent encrypted restic repositories on local or mounted remote filesystems. Check the disk mount before initializing the repository. For example:

```bash
umask 077
mkdir -p /etc/airalogy-backup /srv/airalogy/staging
chmod 700 /etc/airalogy-backup /srv/airalogy/staging
openssl rand -base64 32 > /etc/airalogy-backup/disk.key
restic -r /mnt/backup/airalogy --password-file /etc/airalogy-backup/disk.key init
sha256sum /mnt/backup/airalogy/config
```

Store the following as an operator-only file such as `/etc/airalogy-backup/targets.json`. Escrow the key, deployment identity and configuration separately.

```json
{
  "staging": "/srv/airalogy/staging",
  "reserve_mib": 256,
  "targets": {
    "disk_b": {
      "name": "Backup disk B",
      "repository": "/mnt/backup/airalogy",
      "password_file": "/etc/airalogy-backup/disk.key",
      "config_sha256": "<64-character checksum of repository config>"
    }
  }
}
```

Add a separate repository for each additional destination. For removable staging storage, set top-level `staging_disk_id` and place the matching text in `staging/.airalogy-backup-disk`. Staging needs room for one full logical dump and the captured objects plus the reserve. The repository deduplicates unchanged files. The API pauses until the database dump and object copy finish. Measure this interval with representative data before choosing hourly captures. Encryption, readback and retention run after the API resumes.

## Schedule and operate

Set `BACKUP_OPERATOR_IDS` to a comma-separated list of account UUIDs and recreate the API container through the deployment workflow. Operators must also be owners or managers of the configured single organization. Run `./platformctl backup-tick /etc/airalogy-backup/targets.json --now` once. Schedule one tick per minute using the Docker operator's crontab, substituting your installation path. Ensure docker, python3 and restic are on cron's PATH.

```cron
* * * * * /opt/airalogy/deploy/single-lab/platformctl backup-tick /etc/airalogy-backup/targets.json
```

Under **Organization management → Settings → Storage and backups**, select destinations and frequency. Defaults are 02:00 server time with seven daily and four weekly points. Overlapping rules keep one snapshot. Hourly mode additionally keeps 24 hourly points. Manual-only mode accepts explicit requests. Each destination shows capacity, latest success, errors and recovery dates. Missing disks and low space fail independently. Retry the affected destination after correcting it. A new snapshot is read back and compared to its source before older managed snapshots may be rotated.

## Recover on another host

1. At cutover, stop accepting changes on the source and take the final backup. Record the version, deployment identity and full snapshot ID. List IDs with `restic -r REPOSITORY --password-file KEY snapshots --host SOURCE_DEPLOYMENT_ID --tag airalogy-managed --json`.
2. Run `./platformctl backup-export /etc/airalogy-backup/targets.json disk_b FULL_ID /private/recovery-point` with the source deployment identity. On a recovery host, register the path of the offline copy and its password file with the original repository checksum. Export is independent of the original API and staging disk. Supply a new directory, protect the exported credentials and encrypt transfers.
3. Prepare the same Platform version on the target and start from the exported `secrets.env`. Preserve the AES key, review the host-specific network, data/state paths, release image references and site address. Run `storage-init` for a new data root. Run `./platformctl restore /private/recovery-point`. This command also accepts earlier format-1 backups.
4. Sign in, verify project access, open protocols and records and compare downloaded attachments before switching traffic. After a successful independent drill, record the result on the managed instance with `./platformctl backup-drill /etc/airalogy-backup/targets.json disk_b FULL_ID`. The UI distinguishes a verified snapshot from an operator-confirmed drill.

Accounts, permissions and records are in PostgreSQL. Attachments and published protocol packages are in object storage. Reacquirable protocol work files, images, logs, TLS state, cron settings and host-side repository registrations/passwords have a separate lifecycle. Keep an independent copy of the host configuration and keys.
