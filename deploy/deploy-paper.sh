#!/usr/bin/env bash
# 安装到服务器 /usr/local/bin/deploy-paper
# 由 GitHub Actions 通过受限 SSH 钥匙调用：stdin 为打包好的程序（tar.gz）
set -Eeuo pipefail
APP=/opt/apps/paper
PORT=4303
exec 9>/home/ubuntu/.paper-deploy.lock
if ! flock -n 9; then echo 'Another paper deployment is already running' >&2; exit 1; fi

STAGE=$(mktemp -d /home/ubuntu/.paper-stage.XXXXXX)
trap 'rm -rf "$STAGE"' EXIT
tar -xz -C "$STAGE"
[ -f "$STAGE/serve.py" ] || { echo 'bad bundle: serve.py missing' >&2; exit 1; }

mkdir -p "$APP/data" "$APP/backups"
[ -f "$APP/.env" ] || printf 'HOST=127.0.0.1\nPORT=%s\nBACKUP_DIR=%s/backups\n' "$PORT" "$APP" > "$APP/.env"

# 1. Python 虚拟环境；依赖有变化才重新安装
[ -x "$APP/.venv/bin/python" ] || python3 -m venv "$APP/.venv"
if ! cmp -s "$STAGE/requirements.txt" "$APP/.venv/.requirements.txt"; then
  "$APP/.venv/bin/pip" install --quiet --upgrade pip
  "$APP/.venv/bin/pip" install --quiet -r "$STAGE/requirements.txt"
  cp "$STAGE/requirements.txt" "$APP/.venv/.requirements.txt"
fi

# 2. 升级前先备份个人数据库
if [ -f "$APP/data/user.db" ] && [ -f "$APP/scripts/backup.py" ]; then
  (cd "$APP" && set -a && . ./.env && set +a && .venv/bin/python scripts/backup.py pre-deploy)
fi

# 3. 替换程序文件，保留 data/（数据库、论文库、PDF 缓存）、backups/、.env、config.local.json、.venv
for d in backend web scripts deploy; do rm -rf "${APP:?}/$d"; done
for d in backend web scripts deploy; do cp -a "$STAGE/$d" "$APP/$d"; done
cp -a "$STAGE"/serve.py "$STAGE"/config.json "$STAGE"/requirements.txt "$STAGE"/README.md "$APP"/
cp -a "$STAGE/.deploy-rev" "$APP/" 2>/dev/null || true
# 第一次部署：带上仓库里的论文库作为初始数据（之后由服务器每天自己更新）
[ -f "$APP/data/papers.json" ] || cp "$STAGE/seed/papers.json" "$APP/data/papers.json"

# 4. 重启
sudo -n systemctl restart app-paper.service

for _ in {1..20}; do
  if curl --fail --silent -o /dev/null "http://127.0.0.1:$PORT/api/health"; then
    echo "deployed $(cat "$APP/.deploy-rev" 2>/dev/null || echo '?')"
    exit 0
  fi
  sleep 1
done
echo 'paper health check failed after deployment' >&2
systemctl status app-paper.service --no-pager -l >&2 || true
exit 1
