#!/usr/bin/env bash
# Install blender-agent-skills for your AI agent(s).
#   ./install/install.sh [--agent claude|agents|codex|opencode|gemini|copilot|cursor|all]...
#                        [--scope user|project] [--project DIR] [--copy] [--uninstall] [--skills a,b]
# Defaults: --agent claude --agent agents  --scope user  (symlinks; --copy to copy)
# "agents" = ~/.agents/skills, read by Codex, OpenCode, Gemini CLI, GitHub Copilot and Cursor.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS=() SCOPE=user PROJECT="$PWD" MODE=link UNINSTALL=0 ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --agent) AGENTS+=("$2"); shift 2 ;;
    --scope) SCOPE="$2"; shift 2 ;;
    --project) PROJECT="$(cd "$2" && pwd)"; SCOPE=project; shift 2 ;;
    --copy) MODE=copy; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --skills) ONLY="$2"; shift 2 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "unknown arg $1"; exit 1 ;;
  esac
done
[ ${#AGENTS[@]} -eq 0 ] && AGENTS=(claude agents)
[[ " ${AGENTS[*]} " == *" all "* ]] && AGENTS=(claude agents opencode gemini copilot cursor)

target() {  # $1 agent -> skills dir
  local u="$HOME" p="$PROJECT"
  case "$1:$SCOPE" in
    claude:user) echo "$u/.claude/skills" ;;      claude:project) echo "$p/.claude/skills" ;;
    agents:user|codex:user) echo "$u/.agents/skills" ;; agents:project|codex:project) echo "$p/.agents/skills" ;;
    opencode:user) echo "$u/.config/opencode/skills" ;; opencode:project) echo "$p/.opencode/skills" ;;
    gemini:user) echo "$u/.gemini/skills" ;;      gemini:project) echo "$p/.gemini/skills" ;;
    copilot:user) echo "$u/.copilot/skills" ;;    copilot:project) echo "$p/.github/skills" ;;
    cursor:user) echo "$u/.cursor/skills" ;;      cursor:project) echo "$p/.cursor/skills" ;;
    *) echo "unknown agent $1" >&2; exit 1 ;;
  esac
}

for a in "${AGENTS[@]}"; do
  dst="$(target "$a")"; mkdir -p "$dst"; n=0
  for s in "$ROOT"/skills/*/; do
    name="$(basename "$s")"
    [ -n "$ONLY" ] && [[ ",$ONLY," != *",$name,"* ]] && continue
    rm -rf "${dst:?}/$name"
    if [ $UNINSTALL -eq 0 ]; then
      if [ $MODE = link ]; then ln -s "${s%/}" "$dst/$name"; else cp -R "${s%/}" "$dst/$name"; fi
    fi
    n=$((n+1))
  done
  echo "$([ $UNINSTALL -eq 1 ] && echo removed || echo installed) $n skills -> $dst ($a)"
done
