#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Hetzner-Web All-in-One Installer (Modular Docker Edition)
# =============================================================================

REPO_URL="${REPO_URL:-https://github.com/liuweiqiang0523/Hetzner-Web.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/hetzner-web}"
ALLOW_UPDATE="${ALLOW_UPDATE:-0}"

info() { printf '\033[0;32m[install] %s\033[0m\n' "$1"; }
warn() { printf '\033[0;33m[warn] %s\033[0m\n' "$1"; }
error() { printf '\033[0;31m[error] %s\033[0m\n' "$1" >&2; exit 1; }

need_cmd() { if ! command -v "$1" >/dev/null 2>&1; then error "Missing command: $1. Please install it first."; fi; }

if [[ "${EUID}" -ne 0 ]]; then error "Please run as root (sudo)."; fi

need_cmd git
need_cmd docker

if docker compose version >/dev/null 2>&1; then COMPOSE='docker compose'; else COMPOSE='docker-compose'; fi

# 1. 代码拉取与更新
if [ ! -d "$INSTALL_DIR" ]; then
  info "Cloning Hetzner-Web to $INSTALL_DIR..."
  git clone --depth 1 -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
elif [ -d "$INSTALL_DIR/.git" ]; then
  if [ "$ALLOW_UPDATE" = "1" ]; then
    info "Updating existing repository in $INSTALL_DIR..."
    git -C "$INSTALL_DIR" pull --ff-only
  else
    warn "Install directory already exists. Use ALLOW_UPDATE=1 to update."; exit 0
  fi
fi

cd "$INSTALL_DIR"

# 2. 基础配置文件初始化
if [ ! -f config.yaml ]; then
  info "Creating config.yaml from example..."
  cp config.example.yaml config.yaml
fi

# 3. 环境变量注入
if [[ -n "${HETZNER_API_TOKEN:-}" ]]; then
  sed -i "s/YOUR_HETZNER_API_TOKEN/${HETZNER_API_TOKEN}/g" config.yaml
fi

# 4. 启动容器
info "Building and starting Hetzner-Web containers..."
$COMPOSE up -d --build

info "================================================================="
info "  Successfully installed Hetzner-Web!"
info "  Web UI: http://YOUR_SERVER_IP:1227"
info "  Config: $INSTALL_DIR/config.yaml"
info "================================================================="
