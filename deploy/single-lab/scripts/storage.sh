# Sourced by platformctl and lifecycle commands.
storage_root_check() {
  local root identity binding
  root="$(env_value AIRALOGY_DATA_ROOT)"
  binding="$(deployment_state_dir)/data-root"
  if [[ -f "$binding" && "$(cat "$binding")" != "$root" ]]; then
    die "Configured data root differs from this deployment's registered data disk"
  fi
  [[ -n "$root" ]] || return 0
  identity="$(env_value AIRALOGY_DEPLOYMENT_ID)"
  [[ -f "$binding" && "$root" = /* && "$root" != / && -n "$identity" && -f "$root/.airalogy-instance" && "$(cat "$root/.airalogy-instance")" == "$identity" ]] || die "Data disk is missing or belongs to another deployment"
}

prepare_storage() {
  require_env_file
  local root identity project contents volume
  root="$(env_value AIRALOGY_DATA_ROOT)"
  identity="$(env_value AIRALOGY_DEPLOYMENT_ID)"
  project="$(env_value COMPOSE_PROJECT_NAME)"
  [[ "$root" = /* && "$root" != / && -d "$root" && -n "$identity" && -n "$project" ]] || die "Set AIRALOGY_DATA_ROOT to an existing dedicated absolute directory"
  local binding="$(deployment_state_dir)/data-root"
  if [[ -f "$binding" ]]; then
    storage_root_check
    return
  fi
  contents="$(ls -A -- "$root")"
  [[ -z "$contents" ]] || die "The new data directory must be empty"
  local existing
  existing="$(docker volume ls -q --filter "label=com.docker.compose.project=$project")"
  [[ -z "$existing" ]] || die "Existing project volumes found. Back up and restore to a clean deployment before switching storage."
  for volume in api_logs api_protocols caddy_config caddy_data minio_data postgres_data; do
    mkdir "$root/$volume"
  done
  printf '%s\n' "$identity" > "$root/.airalogy-instance"
  mkdir -p "$(deployment_state_dir)"
  (umask 077; set -C; printf '%s\n' "$root" > "$binding")
}

capture_estimate() {
  local database objects
  database="$(compose exec -T db psql -At -v ON_ERROR_STOP=1 -U "$(env_value POSTGRES_USER)" -d "$(env_value POSTGRES_DB)" -c 'SELECT pg_database_size(current_database())')"
  objects="$(compose exec -T minio du -sk /data | awk '{print $1}')"
  [[ "$database" =~ ^[0-9]+$ && "$objects" =~ ^[0-9]+$ ]] || die "Cannot estimate backup size"
  printf '%s\n' "$((database + objects * 1024))"
}
