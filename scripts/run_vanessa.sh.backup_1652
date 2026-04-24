#!/usr/bin/env bash
# Wrapper для запуска Vanessa-Automation с гарантированным завершением процессов.
# Проблема: тест-клиент может не закрыться после генерации JUnit (баг Vanessa в headless).
# Решение: мониторим файлы результата и принудительно убиваем процессы 1С после их появления.

set -u

FEATURE_PATH="${1:?Usage: $0 <feature_path>}"
IB_PATH="${2:-/home/filimonov/1c-devops-pipeline/build/ib_managed}"
MAX_WAIT="${3:-180}"  # Таймаут в секундах

PROJECT_ROOT="/home/filimonov/1c-devops-pipeline"
JUNIT_DIR="$PROJECT_ROOT/reports/vanessa/junit"
STATUS_FILE="$PROJECT_ROOT/reports/vanessa/logs/status.txt"
VANESSA_EPF="$PROJECT_ROOT/tools/vanessa/vanessa-automation/vanessa-automation.epf"
VANESSA_SETTINGS="$PROJECT_ROOT/tests/VAParams.json"

echo "═══ run_vanessa.sh: запуск ═══"
echo "  feature = $FEATURE_PATH"
echo "  ib      = $IB_PATH"
echo "  timeout = $MAX_WAIT сек"
echo

# Чистим старые результаты
mkdir -p "$JUNIT_DIR" "$(dirname "$STATUS_FILE")"
rm -f "$JUNIT_DIR"/*.xml 2>/dev/null
rm -f "$STATUS_FILE" 2>/dev/null
rm -f /tmp/v8_*.tmp 2>/dev/null

# Убеждаемся что старые процессы 1С не висят
pkill -9 -f "1cv8c.*TESTCLIENT" 2>/dev/null || true

# Запускаем vrunner в фоне
cd "$PROJECT_ROOT"
vrunner vanessa \
    --ibconnection "/F$IB_PATH" \
    --db-user "Администратор" \
    --db-pwd "" \
    --path "$FEATURE_PATH" \
    --pathvanessa "$VANESSA_EPF" \
    --vanessasettings "$VANESSA_SETTINGS" \
    > /tmp/vrunner-output.log 2>&1 &
VRUNNER_PID=$!

echo "vrunner PID: $VRUNNER_PID. Жду появления JUnit..."

# Ждём JUnit.xml или timeout
START=$(date +%s)
while true; do
    NOW=$(date +%s)
    ELAPSED=$(( NOW - START ))

    # Проверяем что vrunner ещё жив
    if ! kill -0 "$VRUNNER_PID" 2>/dev/null; then
        echo "vrunner процесс завершился самостоятельно за $ELAPSED сек"
        break
    fi

    # JUnit готов + status готов?
    if [ -f "$JUNIT_DIR/junit.xml" ] && [ -f "$STATUS_FILE" ]; then
        # Ещё 2 секунды чтобы Vanessa финализировала status.txt
        sleep 2
        echo "JUnit обнаружен за $ELAPSED сек. Завершаем процессы 1С."
        break
    fi

    # Таймаут?
    if [ "$ELAPSED" -gt "$MAX_WAIT" ]; then
        echo "ТАЙМАУТ: $MAX_WAIT сек прошло, результатов нет"
        break
    fi

    sleep 2
done

# Прибиваем всё связанное с 1С и vrunner
echo "Принудительное завершение процессов 1С и Vanessa..."
kill "$VRUNNER_PID" 2>/dev/null || true
pkill -9 -f "1cv8c.*TESTCLIENT" 2>/dev/null || true
pkill -9 -f "1cv8" 2>/dev/null || true
pkill -9 -f "oscript.*vanessa" 2>/dev/null || true
sleep 2

# Последние 30 строк вывода vrunner (для диагностики)
echo
echo "═══ Последние строки vrunner ═══"
tail -30 /tmp/vrunner-output.log 2>/dev/null || echo "(лог пуст)"
echo

# Результат
if [ ! -f "$STATUS_FILE" ]; then
    echo "✗ run_vanessa.sh: status.txt не создан → FAIL"
    exit 2
fi

STATUS=$(python3 -c "print(open('$STATUS_FILE', encoding='utf-8-sig').read().strip())")
echo "═══ Результат ═══"
echo "Status.txt: '$STATUS'"

if [ -f "$JUNIT_DIR/junit.xml" ]; then
    echo "JUnit: $(wc -c < "$JUNIT_DIR/junit.xml") байт"
    echo "Сценариев: $(grep -c '<testcase' "$JUNIT_DIR/junit.xml")"
    echo "Failures:  $(grep -oE 'failures="[0-9]+"' "$JUNIT_DIR/junit.xml" | head -1)"
else
    echo "JUnit: НЕ СОЗДАН"
fi

# Exit code
if [ "$STATUS" = "0" ]; then
    echo "✓ run_vanessa.sh: SUCCESS"
    exit 0
else
    echo "✗ run_vanessa.sh: FAIL (status=$STATUS)"
    exit 1
fi
