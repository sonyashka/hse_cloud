#!/bin/bash

# Проверяем наличие обязательных переменных окружения
if [ -z "$CLICKHOUSE_HOST" ]; then
    echo "ERROR: CLICKHOUSE_HOST is not set"
    exit 1
fi

echo "Starting Logbroker with configuration:"
echo "  ClickHouse: $CLICKHOUSE_HOST:$CLICKHOUSE_PORT"
echo "  Database: $CLICKHOUSE_DB.$CLICKHOUSE_TABLE"
echo "  Buffer flush interval: ${BUFFER_FLUSH_INTERVAL}s"
echo "  App host: $APP_HOST:$APP_PORT"

# Запускаем приложение
# shellcheck disable=SC2086
exec uvicorn main:app --host "$APP_HOST" --port "$APP_PORT" --log-level $LOG_LEVEL