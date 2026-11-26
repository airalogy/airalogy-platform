#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

lock_maintenance "$@"

require_command docker
require_command tar
require_env_file

postgres_user="$(env_value POSTGRES_USER)"
postgres_db="$(env_value POSTGRES_DB)"
minio_user="$(env_value MINIO_ROOT_USER)"
minio_password="$(env_value MINIO_ROOT_PASSWORD)"
minio_bucket="$(env_value MINIO_BUCKET)"
backup_root="$(absolute_path "$(env_value BACKUP_DIR)")"
# Use the expected marker before creating directories on a dedicated backup disk.
expected_marker="$(env_value BACKUP_DISK_ID)"
if [[ -n "$expected_marker" ]]; then
  [[ -f "$backup_root/.airalogy-backup-disk" && "$(cat "$backup_root/.airalogy-backup-disk")" == "$expected_marker" ]] || die "Backup disk is missing or has the wrong identity"
fi
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
label="${1:-manual}"
[[ "$label" =~ ^[a-zA-Z0-9._-]+$ ]] || die "backup label contains unsupported characters"
final_dir="$backup_root/${timestamp}-${label}"
format="${AIRALOGY_CAPTURE_FORMAT:-1}"
[[ "$format" == 1 || "$format" == 2 ]] || die "Unsupported capture format"

umask 077
mkdir -p "$backup_root"
wait_for_service db 60
wait_for_service minio 60
size="$(capture_estimate)"
reserve="$(env_value BACKUP_RESERVE_MIB)"
python3 - "$backup_root" "$size" "$format" "${reserve:-256}" <<'PYSPACE'
import shutil, sys
root, size, fmt, reserve = sys.argv[1:]
if int(reserve) < 0 or shutil.disk_usage(root).free < int(size) * (2 if fmt == "1" else 1) + int(reserve) * 1024**2:
    sys.exit("Insufficient backup staging space (including temporary files and free-space reserve)")
PYSPACE
[[ ! -e "$final_dir" ]] || die "backup directory already exists: $final_dir"
backup_dir="$(mktemp -d "$backup_root/.partial-XXXXXXXX")"
mkdir "$backup_dir/objects"
chmod 700 "$backup_dir"

pause_marker="$(deployment_state_dir)/backup-paused-api"
api_was_running=false
resume_api() {
  if [[ "$api_was_running" == true ]]; then
    compose start api-server >/dev/null
    wait_for_service api-server 300
    rm -f -- "$pause_marker"
    api_was_running=false
  fi
}
cleanup() {
  rm -rf -- "$backup_dir"
  resume_api
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
api_container="$(compose ps -q api-server)"
runtime_payload=""
if [[ -n "$api_container" && "$(docker inspect --format '{{.State.Running}}' "$api_container")" == "true" ]]; then
  api_was_running=true
  runtime_payload="$(running_version_payload 2>/dev/null || true)"
  info "Pausing API writes for a consistent backup..."
  printf '%s\n' "$api_container" > "$pause_marker.tmp"
  mv "$pause_marker.tmp" "$pause_marker"
  compose stop api-server >/dev/null
fi

info "Creating PostgreSQL backup..."
compose exec -T db pg_dump \
  --username "$postgres_user" \
  --dbname "$postgres_db" \
  --format custom \
  --no-owner \
  --no-acl >"$backup_dir/database.dump"

info "Mirroring object storage..."
network="$(minio_network)"
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --env MC_CONFIG_DIR=/tmp/airalogy-mc \
  --network "$network" \
  --volume "$backup_dir/objects:/backup" \
  --env "MINIO_ROOT_USER=$minio_user" \
  --env "MINIO_ROOT_PASSWORD=$minio_password" \
  --env "MINIO_BUCKET=$minio_bucket" \
  --entrypoint /bin/sh \
  "$(mc_image)" \
  -c 'mc alias set source http://minio:9200 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc mirror --overwrite source/"$MINIO_BUCKET" /backup' \
  >&2

# The logical dump and mirrored objects now describe the same point in time.
resume_api
if [[ "$format" == 2 ]]; then
  python3 "$SCRIPT_DIR/backup_files.py" index "$backup_dir"
  object_index=objects.jsonl
else
  tar -C "$backup_dir/objects" -czf "$backup_dir/objects.tar.gz" .
  rm -rf "$backup_dir/objects"
  object_index=objects.tar.gz
fi

cp "$ENV_FILE" "$backup_dir/secrets.env"
chmod 600 "$backup_dir/secrets.env"

platform_version="$(printf '%s\n' "$runtime_payload" | json_string_field version)"
platform_version="${platform_version:-$(env_value PLATFORM_VERSION)}"
git_commit="$(printf '%s\n' "$runtime_payload" | json_string_field commit)"
git_commit="${git_commit:-$(env_value GIT_COMMIT)}"
cat >"$backup_dir/manifest.env" <<EOF
BACKUP_FORMAT_VERSION=$format
CREATED_AT=$timestamp
PLATFORM_VERSION=$platform_version
GIT_COMMIT=$git_commit
DATABASE_REVISION=$(printf '%s\n' "$runtime_payload" | json_string_field database_revision)
AIRALOGY_DEPLOYMENT_ID=$(env_value AIRALOGY_DEPLOYMENT_ID)
AIRALOGY_RELEASE_MANIFEST_SHA256=$(env_value AIRALOGY_RELEASE_MANIFEST_SHA256)
CONFIGURATION_REVISION=$(configuration_revision)
COMPOSE_PROJECT_NAME=$(env_value COMPOSE_PROJECT_NAME)
POSTGRES_DB=$postgres_db
MINIO_BUCKET=$minio_bucket
EOF

(
  cd "$backup_dir"
  sha256_file database.dump
  sha256_file "$object_index"
  sha256_file secrets.env
  sha256_file manifest.env
) >"$backup_dir/SHA256SUMS"
chmod 600 "$backup_dir/"{database.dump,secrets.env,manifest.env,SHA256SUMS} "$backup_dir/$object_index"
verify_checksums "$backup_dir" >&2

mv "$backup_dir" "$final_dir"
trap - EXIT
info "Backup complete: $final_dir"
printf '%s\n' "$final_dir"
