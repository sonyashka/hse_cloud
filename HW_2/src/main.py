from fastapi import FastAPI, HTTPException, Request
import aiohttp
from pydantic import BaseModel
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Конфигурация через переменные окружения
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "10.0.1.30")
CLICKHOUSE_PORT = os.getenv("CLICKHOUSE_PORT", "8123")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "default")
CLICKHOUSE_TABLE = os.getenv("CLICKHOUSE_TABLE", "logs")

# Критические настройки буфера
BUFFER_FLUSH_INTERVAL = int(os.getenv("BUFFER_FLUSH_INTERVAL", "1"))  # секунды
BUFFER_MAX_SIZE = int(os.getenv("BUFFER_MAX_SIZE", "1000"))  # максимум логов в буфере

# Настройки приложения
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8080"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Пути для хранения буфера
BUFFER_DIR = Path("buffer")
PENDING_DIR = BUFFER_DIR / "pending"
SENT_DIR = BUFFER_DIR / "sent"

# Создаем директории при старте
BUFFER_DIR.mkdir(exist_ok=True)
PENDING_DIR.mkdir(exist_ok=True)
SENT_DIR.mkdir(exist_ok=True)



# Модели данных
class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    service: str = "logbroker"
    extra: Dict[str, Any] = {}


# Глобальные переменные для буфера и флагов
buffer: List[LogEntry] = []
buffer_lock = asyncio.Lock()
is_running = True
last_flush_time = time.time()


# ClickHouse клиент
class ClickHouseClient:
    def __init__(self, host: str, port: str):
        self.base_url = f"http://{host}:{port}"

    async def insert_batch(self, logs: List[LogEntry]) -> bool:
        """Вставка батча логов в ClickHouse"""
        if not logs:
            return True

        # Счетчик попыток для retry-логики
        max_retries = 3
        retry_delay = 1  # секунды

        for attempt in range(max_retries):
            try:
                logger.debug(f"Inserting batch of {len(logs)} logs to ClickHouse (attempt {attempt + 1}/{max_retries})")

                # Формируем данные для ClickHouse
                data_lines = []
                for log in logs:
                    # Безопасное экранирование для ClickHouse CSV
                    timestamp_escaped = log.timestamp.replace("'", "''")
                    level_escaped = log.level.replace("'", "''")
                    message_escaped = log.message.replace("'", "''").replace("\\", "\\\\")
                    service_escaped = log.service.replace("'", "''")
                    extra_json = json.dumps(log.extra, ensure_ascii=False)
                    extra_escaped = extra_json.replace("'", "''").replace("\\", "\\\\")

                    data_lines.append(
                        f"'{timestamp_escaped}','{level_escaped}','{message_escaped}',"
                        f"'{service_escaped}','{extra_escaped}'"
                    )

                data = "\n".join(data_lines)

                query = f"""
                INSERT INTO {CLICKHOUSE_DB}.{CLICKHOUSE_TABLE} 
                (timestamp, level, message, service, extra) 
                FORMAT CSV
                """

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                            f"{self.base_url}/",
                            params={
                                "query": query,
                                "database": CLICKHOUSE_DB,
                                "default_format": "CSV"
                            },
                            data=data,
                            headers={
                                "Content-Type": "text/csv",
                                "X-ClickHouse-Format": "CSV"
                            },
                            timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status == 200:
                            inserted_count = len(logs)
                            logger.info(f"✅ Successfully inserted {inserted_count} logs to ClickHouse "
                                        f"({CLICKHOUSE_HOST}:{CLICKHOUSE_PORT})")

                            # Помечаем файлы как отправленные
                            files_moved = 0
                            for log in logs:
                                if hasattr(log, '_filename'):
                                    try:
                                        old_path = PENDING_DIR / log._filename
                                        new_path = SENT_DIR / log._filename
                                        if old_path.exists():
                                            old_path.rename(new_path)
                                            files_moved += 1
                                    except Exception as e:
                                        logger.warning(f"Failed to move sent file {log._filename}: {e}")

                            if files_moved > 0:
                                logger.debug(f"Moved {files_moved} files from pending to sent")

                            return True
                        else:
                            error_text = await response.text()
                            logger.warning(
                                f"⚠️ ClickHouse returned error (attempt {attempt + 1}/{max_retries}): "
                                f"HTTP {response.status} - {error_text[:200]}"
                            )

                            # Если это серверная ошибка 5xx, пробуем снова
                            if 500 <= response.status < 600 and attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay * (attempt + 1))
                                continue
                            else:
                                logger.error(
                                    f"❌ Failed to insert batch after {attempt + 1} attempts. "
                                    f"Last error: HTTP {response.status}"
                                )
                                return False

            except asyncio.TimeoutError:
                logger.warning(
                    f"⌛ Timeout connecting to ClickHouse (attempt {attempt + 1}/{max_retries})"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error("❌ All connection attempts to ClickHouse timed out")
                    return False

            except aiohttp.ClientConnectorError:
                logger.warning(
                    f"🔌 Cannot connect to ClickHouse at {self.base_url} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"❌ ClickHouse is unreachable at {self.base_url}")
                    return False

            except Exception as e:
                logger.error(
                    f"💥 Unexpected error during ClickHouse insertion "
                    f"(attempt {attempt + 1}/{max_retries}): {type(e).__name__}: {str(e)[:200]}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"❌ Failed after {max_retries} attempts: {e}")
                    return False

        # Не должно сюда дойти, но на всякий случай
        return False

clickhouse = ClickHouseClient(CLICKHOUSE_HOST, CLICKHOUSE_PORT)

def save_log_to_disk_sync(log: LogEntry) -> str:
    """Синхронное сохранение лога на диск (для гарантии persistence)"""
    try:
        # Создаем уникальное имя файла с timestamp
        filename = f"log_{int(time.time() * 1000)}_{os.urandom(4).hex()}.json"
        filepath = PENDING_DIR / filename

        # Сохраняем лог
        with open(filepath, 'w') as f:
            json.dump(log.dict(), f, ensure_ascii=False)

        return filename
    except Exception as e:
        logger.error(f"Failed to save log to disk: {e}")
        raise


async def flush_buffer():
    """Отправка буфера в ClickHouse"""
    global buffer, last_flush_time

    async with buffer_lock:
        if not buffer:
            return

        current_buffer = buffer.copy()
        buffer = []

    if current_buffer:
        # Пытаемся отправить в ClickHouse
        success = await clickhouse.insert_batch(current_buffer)

        if success:
            # Помечаем файлы как отправленные
            for log in current_buffer:
                if hasattr(log, '_filename'):
                    try:
                        old_path = PENDING_DIR / log._filename
                        new_path = SENT_DIR / log._filename
                        if old_path.exists():
                            old_path.rename(new_path)
                    except Exception as e:
                        logger.warning(f"Failed to move sent file: {e}")
        else:
            # Возвращаем логи обратно в буфер при ошибке
            async with buffer_lock:
                buffer = current_buffer + buffer
            logger.warning("Failed to send batch, keeping in buffer")


async def flush_loop():
    """Фоновая задача для периодической отправки буфера"""
    while is_running:
        await asyncio.sleep(1)

        # Отправляем, если прошла хотя бы секунда с последней отправки
        if time.time() - last_flush_time >= 1:
            await flush_buffer()


def load_pending_logs():
    """Загрузка неотправленных логов с диска при старте"""
    loaded_logs = []

    for filepath in PENDING_DIR.glob("*.json"):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                log = LogEntry(**data)
                log._filename = filepath.name
                loaded_logs.append(log)
        except Exception as e:
            logger.error(f"Failed to load pending log {filepath}: {e}")

    return loaded_logs


@app.on_event("startup")
async def startup_event():
    """Инициализация при старте"""
    global buffer, is_running

    # Загружаем неотправленные логи
    pending_logs = load_pending_logs()
    if pending_logs:
        async with buffer_lock:
            buffer = pending_logs + buffer
        logger.info(f"Loaded {len(pending_logs)} pending logs from disk")

    # Запускаем фоновую задачу
    asyncio.create_task(flush_loop())

    # Создаем таблицу в ClickHouse если её нет
    await create_clickhouse_table()

    logger.info("Logbroker started")


@app.on_event("shutdown")
async def shutdown_event():
    """Обработка завершения работы"""
    global is_running

    logger.info("Shutting down...")
    is_running = False

    # Пытаемся отправить оставшиеся логи
    await flush_buffer()

    # Сохраняем состояние
    with open("shutdown.log", "w") as f:
        f.write(f"Shutdown at {datetime.now().isoformat()}\n")

    logger.info("Shutdown complete")


async def create_clickhouse_table():
    """Создание таблицы в ClickHouse если не существует"""
    try:
        query = f"""
        CREATE TABLE IF NOT EXISTS {CLICKHOUSE_DB}.{CLICKHOUSE_TABLE}
        (
            timestamp DateTime,
            level String,
            message String,
            service String,
            extra String
        )
        ENGINE = MergeTree()
        ORDER BY (timestamp, service, level)
        """

        async with aiohttp.ClientSession() as session:
            async with session.post(
                    f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/",
                    params={"query": query},
                    timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    logger.info("ClickHouse table created or already exists")
                else:
                    error = await response.text()
                    logger.warning(f"Could not create table: {error}")
    except Exception as e:
        logger.warning(f"Failed to create ClickHouse table: {e}")


@app.post("/write_log")
async def write_log(request: Request):
    """Основной endpoint для приёма логов"""
    try:
        # Парсим JSON из запроса
        data = await request.json()

        # Проверяем обязательные поля
        if not all(k in data for k in ["timestamp", "level", "message"]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Создаем объект лога
        log_entry = LogEntry(**data)

        # Сохраняем на диск СНАЧАЛА (гарантия persistence)
        filename = save_log_to_disk_sync(log_entry)
        log_entry._filename = filename

        # Добавляем в буфер
        async with buffer_lock:
            buffer.append(log_entry)

        logger.debug(f"Log received and buffered: {log_entry.message[:50]}...")

        return {"status": "ok", "message": "Log accepted"}

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing log: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "logbroker",
        "buffer_size": len(buffer),
        "pending_files": len(list(PENDING_DIR.glob("*.json"))),
        "sent_files": len(list(SENT_DIR.glob("*.json"))),
        "clickhouse": f"{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}",
        "timestamp": datetime.now().isoformat()
    }
@app.get("/")
async def root():
    return {"message": "Logbroker Service", "version": "1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)