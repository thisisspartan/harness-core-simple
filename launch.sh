#!/usr/bin/env bash
# launch.sh — вропер для harness-core-simple: бинарь 2.1.311 + ЭТОТ плагин + env локального сервера.
# От старого HARNESS-launch-tune311.sh намеренно НЕ наследуется: у простого харнесса нет
# merge-оверрайдов, trap-файлов и role-промпта — только бинарь, --plugin-dir и --settings.
# Запускать ВНУТРИ проекта (cd в проект, потом ~/.../launch.sh [claude аргументы]).
# Переопределения: CLAUDE_BIN=<бинарь>, SETTINGS=<settings.json>, HARNESS_MODEL/URL через свой settings.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
SETTINGS="${SETTINGS:-$DIR/settings.json}"
[ -x "$CLAUDE_BIN" ] || { echo "launch: no binary $CLAUDE_BIN (set CLAUDE_BIN=...)" >&2; exit 1; }
[ -f "$SETTINGS" ] || { echo "launch: no $SETTINGS (cp settings.example.json settings.json and fill it)" >&2; exit 1; }
echo "launch: $CLAUDE_BIN  plugin=$DIR/v1  settings=$SETTINGS  cwd=$PWD"
exec "$CLAUDE_BIN" --plugin-dir "$DIR/v1" --settings "$SETTINGS" "$@"
