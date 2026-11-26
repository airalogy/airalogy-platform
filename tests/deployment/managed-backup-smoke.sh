#!/usr/bin/env bash
# Run only after acceptance-test.sh on the isolated Linux deployment-smoke runner.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && -n "${RUNNER_TEMP:-}" ]] || exit 2
source deploy/single-lab/scripts/lib.sh
test_dir="$(mktemp -d "$RUNNER_TEMP/managed-backup-XXXXXXXX")"
source_env="$ENV_FILE"
source_id="$(env_value AIRALOGY_DEPLOYMENT_ID)"
work="$test_dir/staging"
repo="$test_dir/repository"
key="$test_dir/key"
config="$test_dir/targets.json"
umask 077
mkdir "$work"
openssl rand -base64 32 > "$key"
restic -r "$repo" --password-file "$key" init
jq -n --arg staging "$work" --arg repo "$repo" --arg key "$key" \
  --arg hash "$(sha256sum "$repo/config" | awk '{print $1}')" \
  '{staging:$staging,targets:{disk:{name:"Test disk",repository:$repo,password_file:$key,config_sha256:$hash}}}' > "$config"

# Capture a known object alongside the accounts, project and permissions from acceptance.
object() {
  compose exec -T minio sh -ec '
    mc alias set smoke http://localhost:9200 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
    mc "$1" "smoke/$2/acceptance/managed-backup.txt"
  ' sh "$1" "$(env_value MINIO_BUCKET)"
}
url="$(env_value SITE_URL)/api"
owner_token() {
  curl --fail --silent -H 'Content-Type: application/json' --data '{"email":"owner@acceptance.example.com","password":"AcceptanceOwner123"}' "$url/signin_by_email" | jq -er .token
}
token="$(owner_token)"
project_id="$(curl --fail --silent -H "Auth-Token: $token" "$url/projects?lab_uid=$(env_value SINGLE_LAB_UID)&page_size=100" | jq -er '.projects[] | select(.uid == "structured_access_test").id')"
python3 - "$test_dir/inspection.zip" <<'PYZIP'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "w") as archive:
    archive.writestr("protocol.toml", '[airalogy_protocol]\nid="backup_inspection"\nname="Backup inspection"\nversion="0.1.0"\n')
    archive.writestr("protocol.aimd", "# Inspection\n{{var|label: str}}")
PYZIP
protocol_id="$(curl --fail --silent -H "Auth-Token: $token" -F "project_id=$project_id" -F "file=@$test_dir/inspection.zip;type=application/zip" "$url/protocols" | jq -er '.data.id')"
record_id="$(curl --fail --silent -H "Auth-Token: $token" -H 'Content-Type: application/json' --data '{"var":{"label":"recovery fixture"},"step":{},"check":{},"report":""}' "$url/protocols/$protocol_id/records" | jq -er .id)"
read_record() {
  curl --fail --silent -H "Auth-Token: $token" "$url/protocols/$protocol_id/records/$record_id?version=1" | jq -eS '{record_id,record_version,data}'
}
read_record > "$test_dir/original-record.json"
printf 'synthetic attachment' | object pipe
"$DEPLOY_DIR/platformctl" backup-tick "$config" --now
id="$(restic -r "$repo" --password-file "$key" snapshots --host "$source_id" --tag airalogy-managed --json | jq -er '.[0].id')"
"$DEPLOY_DIR/platformctl" backup-export "$config" disk "$id" "$test_dir/point"
# Reuse the service ports and subnet with fresh, differently named volumes.
# Leave the source volumes intact so the subsequent upgrade test uses the original.
compose down
export AIRALOGY_ENV_FILE="$test_dir/target.env"
ENV_FILE="$AIRALOGY_ENV_FILE"
cp "$test_dir/point/secrets.env" "$ENV_FILE"
set_env_value COMPOSE_PROJECT_NAME airalogy-managed-restore-smoke
set_env_value AIRALOGY_STATE_DIR "$test_dir/target-state"
set_env_value AIRALOGY_DATA_ROOT "$test_dir/mounted-disk/platform"
data_disk="$test_dir/target.ext4"
mount_point="$test_dir/mounted-disk"
truncate -s 2G "$data_disk"
mkfs.ext4 -q -F "$data_disk"
mkdir "$mount_point"
cleanup() {
  if [[ -f "$test_dir/mounted-disk/platform/.airalogy-instance" ]]; then
    compose down --volumes || true
  fi
  if mountpoint -q "$mount_point"; then sudo umount "$mount_point"; fi
  export AIRALOGY_ENV_FILE="$source_env"
  ENV_FILE="$source_env"
  compose up -d
  wait_for_service api-server 300
}
trap cleanup EXIT
sudo mount -o loop "$data_disk" "$mount_point"
sudo install -d -o "$(id -u)" -g "$(id -g)" "$mount_point/platform"
"$DEPLOY_DIR/platformctl" storage-init
"$DEPLOY_DIR/platformctl" install
# Confirm both live services actually mounted the newly registered data root.
for pair in db:postgres_data minio:minio_data; do
  service="${pair%:*}"
  backing="${pair#*:}"
  volume="$(docker inspect --format '{{range .Mounts}}{{println .Name}}{{end}}' "$(compose ps -q "$service")" | grep -Fx "$(env_value COMPOSE_PROJECT_NAME)_disk_$backing")"
  [[ "$(docker volume inspect --format '{{index .Options "device"}}' "$volume")" == "$test_dir/mounted-disk/platform/$backing" ]]
done
"$DEPLOY_DIR/platformctl" restore "$test_dir/point" --yes
[[ "$(object cat)" == "synthetic attachment" ]]
token="$(owner_token)"
curl --fail --silent -H "Auth-Token: $token" "$url/projects?lab_uid=$(env_value SINGLE_LAB_UID)&page_size=100" | jq -e --arg id "$project_id" '.projects | any(.id == $id)' >/dev/null
curl --fail --silent -H "Auth-Token: $token" "$url/protocols/$protocol_id?version=0.1.0" >/dev/null
read_record > "$test_dir/restored-record.json"
cmp "$test_dir/original-record.json" "$test_dir/restored-record.json"
[[ "$(curl --silent --output /dev/null --write-out '%{http_code}' "$url/protocols/$protocol_id/records/$record_id?version=1")" != 200 ]]
# Both checks must stop before replacing live data or stopping the API.
if AES_KEY=wrong-fixture-key "$DEPLOY_DIR/platformctl" restore "$test_dir/point" --yes >"$test_dir/key-check.log" 2>&1; then
  exit 1
fi
grep -q 'AES_KEY differs' "$test_dir/key-check.log"
cp -R "$test_dir/point" "$test_dir/corrupt"
printf 'changed' >> "$test_dir/corrupt/objects/acceptance/managed-backup.txt"
if "$DEPLOY_DIR/platformctl" restore "$test_dir/corrupt" --yes >"$test_dir/corrupt-check.log" 2>&1; then
  exit 1
fi
grep -q 'Object inventory or content checksum mismatch' "$test_dir/corrupt-check.log"
read_record > "$test_dir/after-rejected-restores.json"
cmp "$test_dir/original-record.json" "$test_dir/after-rejected-restores.json"
# Recreate containers on the requested disk and check the record and object again.
sudo find "$test_dir/mounted-disk/platform/postgres_data" -name PG_VERSION -print -quit | grep -q .
compose down
sudo umount "$mount_point"
if (compose up -d) >"$test_dir/missing-disk.log" 2>&1; then exit 1; fi
grep -q "Data disk is missing" "$test_dir/missing-disk.log"
[[ ! -e "$mount_point/platform" ]]
sudo mount -o loop "$data_disk" "$mount_point"
compose up -d
wait_for_service api-server 300
wait_for_service web 180
token="$(owner_token)"
read_record > "$test_dir/recreated-record.json"
cmp "$test_dir/original-record.json" "$test_dir/recreated-record.json"
[[ "$(object cat)" == "synthetic attachment" ]]
