#!/bin/sh
# ============================================================================
# 智能招投标平台 API 容器入口脚本
# 等待所有必需依赖（数据库/Redis/MinIO）就绪后再启动主进程
# 支持：内部 compose 服务 / 外部独立部署的依赖
# ============================================================================
set -e

DB_TYPE="${BMP_DB_TYPE:-postgresql}"
WAIT_TIMEOUT="${DB_WAIT_TIMEOUT:-60}"

# 探测 host:port 是否可连接（用 python socket，镜像内已有 python）
wait_for() {
  host="$1"
  port="$2"
  name="$3"
  echo "[entrypoint] 等待 ${name} ${host}:${port} 就绪 ..."
  i=0
  while [ $i -lt "$WAIT_TIMEOUT" ]; do
    if python -c "import socket,sys; s=socket.create_connection(('${host}', ${port}), timeout=2); s.close()" 2>/dev/null; then
      echo "[entrypoint] ${name} 已就绪（耗时 ${i}s）"
      return 0
    fi
    sleep 2
    i=$((i + 2))
  done
  echo "[entrypoint] 警告：等待 ${name} 超时（${WAIT_TIMEOUT}s）"
  return 1
}

# ── 等待数据库（必需：超时则终止启动）──
case "$DB_TYPE" in
  mysql)
    wait_for "${BMP_MYSQL_HOST:-mysql}" "${BMP_MYSQL_PORT:-3306}" "MySQL" || { echo "[entrypoint] MySQL 不可达，终止启动"; exit 1; }
    ;;
  postgresql|postgres|pg|*)
    pg_host="postgres"
    pg_port="5432"
    if [ -n "$BMP_DATABASE_URL" ]; then
      after_at=$(echo "$BMP_DATABASE_URL" | sed 's#.*@##' | sed 's#/.*##')
      if [ -n "$after_at" ]; then
        pg_host=$(echo "$after_at" | cut -d: -f1)
        pg_port=$(echo "$after_at" | cut -d: -f2)
        [ -z "$pg_port" ] && pg_port="5432"
      fi
    fi
    wait_for "$pg_host" "$pg_port" "PostgreSQL" || { echo "[entrypoint] PostgreSQL 不可达，终止启动"; exit 1; }
    ;;
esac

# ── 等待 Redis ──
# 从 BMP_REDIS_URL 解析 host:port，格式 redis://host:port/db
redis_host="redis"
redis_port="6379"
if [ -n "$BMP_REDIS_URL" ]; then
  # 去掉 redis:// 前缀，取 host:port 部分
  redis_addr=$(echo "$BMP_REDIS_URL" | sed 's#redis://##' | sed 's#/.*##')
  if [ -n "$redis_addr" ]; then
    redis_host=$(echo "$redis_addr" | cut -d: -f1)
    redis_port=$(echo "$redis_addr" | cut -d: -f2)
    [ -z "$redis_port" ] && redis_port="6379"
  fi
fi
wait_for "$redis_host" "$redis_port" "Redis" || echo "[entrypoint] Redis 不可达，以降级模式继续"

# ── 等待 MinIO ──
# 从 BMP_MINIO_ENDPOINT 解析 host:port
minio_host="minio"
minio_port="9000"
if [ -n "$BMP_MINIO_ENDPOINT" ]; then
  minio_host=$(echo "$BMP_MINIO_ENDPOINT" | cut -d: -f1)
  minio_port=$(echo "$BMP_MINIO_ENDPOINT" | cut -d: -f2)
  [ -z "$minio_port" ] && minio_port="9000"
fi
wait_for "$minio_host" "$minio_port" "MinIO" || echo "[entrypoint] MinIO 不可达，以降级模式继续"

# ── 安全检查: 拒绝以默认凭证组合启动 (infra 内置 MinIO 场景) ──
# 仅在未显式关闭检查时执行; 外部 MinIO 自行保证凭证安全
if [ "${SKIP_DEFAULT_CRED_CHECK:-false}" != "true" ]; then
  if [ "${BMP_MINIO_ACCESS_KEY:-}" = "minioadmin" ] || [ "${BMP_MINIO_SECRET_KEY:-}" = "minioadmin" ]; then
    if [ "${BMP_DEBUG:-false}" != "true" ]; then
      echo "[entrypoint] 检测到 MinIO 使用默认凭证 minioadmin, 生产环境禁止启动。"
      echo "[entrypoint] 请在 .env 中设置 MINIO_ROOT_USER / MINIO_ROOT_PASSWORD 后重试,"
      echo "[entrypoint] 或设 BMP_DEBUG=true (开发) / SKIP_DEFAULT_CRED_CHECK=true (明确跳过)。"
      exit 1
    fi
  fi
fi

echo "[entrypoint] 所有依赖就绪，启动主进程：$@"
exec "$@"
