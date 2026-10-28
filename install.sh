#!/bin/bash
# 我的新闻 Linux 一键安装：下载二进制 → 安装 systemd 服务 → 自动启动。数据库默认用 SQLite（轻量，不用装 MySQL）
# 用法：curl -fsSL https://raw.githubusercontent.com/suyijun8182/mynews/main/install.sh | sudo bash
# 可用环境变量：MYNEWS_PORT（默认 8844）、MYNEWS_DIR（默认 /opt/mynews）
# 自定义配置（ADMIN_PASSWORD、DATABASE_URL 等）写在 /etc/mynews.env，重装 / 升级都不会覆盖
set -euo pipefail

REPO="suyijun8182/mynews"
PORT="${MYNEWS_PORT:-8844}"
DIR="${MYNEWS_DIR:-/opt/mynews}"
BIN="$DIR/bin/mynews"          # 放在安装目录下，服务账号可写：网页上的一键更新要原地替换它
LINK="/usr/local/bin/mynews"
ENV_FILE="/etc/mynews.env"
SVC_USER="mynews"

[ "$(id -u)" = 0 ] || { echo "请用 root 运行（curl ... | sudo bash）"; exit 1; }

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ASSET="mynews-linux-amd64.tar.gz" ;;
  aarch64 | arm64) ASSET="mynews-linux-arm64.tar.gz" ;;
  *) echo "不支持的架构：$ARCH"; exit 1 ;;
esac

echo "==> 获取最新版本号"
# 不用 grep -P（BusyBox / 部分发行版的 grep 不支持），sed 取 "tag_name": "vX.Y.Z"
TAG=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1 || true)
[ -n "$TAG" ] || { echo "取不到最新版本（网络问题？）"; exit 1; }
echo "    最新版本 $TAG"

echo "==> 下载 $ASSET"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
BASE="https://github.com/${REPO}/releases/download/${TAG}"
curl -fsSL "$BASE/${ASSET}" -o "$TMP/${ASSET}"

echo "==> 校验 SHA256"
curl -fsSL "$BASE/SHA256SUMS" -o "$TMP/SHA256SUMS" || { echo "该版本没有 SHA256SUMS 校验文件，为安全起见停止安装"; exit 1; }
grep -q " [*]\{0,1\}${ASSET}\$" "$TMP/SHA256SUMS" || { echo "SHA256SUMS 里没有 ${ASSET}，停止安装"; exit 1; }
(cd "$TMP" && grep " [*]\{0,1\}${ASSET}\$" SHA256SUMS | sha256sum -c -) || { echo "校验失败：下载的文件已损坏或被篡改"; exit 1; }
tar -xzf "$TMP/${ASSET}" -C "$TMP"

echo "==> 安装"
REINSTALL=0
[ -f /etc/systemd/system/mynews.service ] && REINSTALL=1
# 专用系统账号运行服务：不能登录、没有家目录
if ! id "$SVC_USER" >/dev/null 2>&1; then
  NOLOGIN=$(command -v nologin || echo /bin/false)
  if command -v useradd >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --home-dir "$DIR" --shell "$NOLOGIN" "$SVC_USER"
  else   # BusyBox / Alpine
    addgroup -S "$SVC_USER" 2>/dev/null || true
    adduser -S -D -H -h "$DIR" -s "$NOLOGIN" -G "$SVC_USER" "$SVC_USER"
  fi
fi
mkdir -p "$DIR/bin" "$DIR/data"
install -m 755 "$TMP/mynews" "$BIN"
ln -sfn "$BIN" "$LINK"
# 数据目录里的 SQLite 库存着登录签名密钥和各类密钥（加密后）：只给服务账号读写
chown -R "$SVC_USER:$SVC_USER" "$DIR/bin" "$DIR/data"
chmod 700 "$DIR/data"

# 用户配置单独放在 EnvironmentFile：只在不存在时创建（全是注释示例），重装 / 升级都不覆盖
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<'ENVF'
# 我的新闻 自定义配置：取消注释并修改后执行 systemctl restart mynews
# 本文件不会被 install.sh 覆盖；FreshRSS、早晚报、推送渠道都在网页上配置
#
# 管理员 admin 的初始密码（留空则首次打开网页时设置）：
# ADMIN_PASSWORD=
# 早晚报的时区：
# TZ=Asia/Shanghai
# 想用 MySQL 代替默认的 SQLite：
# DATABASE_URL=mysql+pymysql://mynews:密码@127.0.0.1:3306/mynews?charset=utf8mb4
ENVF
fi
chmod 600 "$ENV_FILE"

# 以专用账号运行。一键更新只需要写 $DIR/bin，重启靠进程退出后 Restart=always 拉起，不需要 systemctl 权限
cat > /etc/systemd/system/mynews.service <<UNIT
[Unit]
Description=我的新闻 FreshRSS 早晚报推送
After=network-online.target
Wants=network-online.target

[Service]
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$DIR
Environment=HTTP_PORT=$PORT
Environment=DATA_DIR=$DIR/data
Environment=TZ=Asia/Shanghai
EnvironmentFile=-$ENV_FILE
ExecStart=$BIN
Restart=always
RestartSec=3
UMask=0077
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=$DIR/bin $DIR/data
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable mynews >/dev/null 2>&1
if [ "$REINSTALL" = 1 ]; then systemctl restart mynews; else systemctl start mynews; fi
sleep 2
systemctl is-active mynews >/dev/null && STATE="运行中" || STATE="启动失败（journalctl -u mynews 查看）"

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "==> 完成：$STATE"
echo "    浏览器打开 http://${IP:-本机IP}:$PORT ，按安装向导设置管理员、连接 FreshRSS、选择推送渠道"
echo "    数据目录 $DIR/data（SQLite）；自定义配置在 $ENV_FILE"
echo "    从公网地址打开安装向导时需要安装码：journalctl -u mynews | grep 安装码"
