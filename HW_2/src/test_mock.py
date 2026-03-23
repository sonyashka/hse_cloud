import asyncio
import json
import sys
import os

# Добавляем путь к src в sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


async def test_logbroker():
    """Тестируем отправку логов"""

    # Импортируем из main.py
    from main import app
    from fastapi.testclient import TestClient

    # Создаем тестового клиента
    client = TestClient(app)

    print("🚀 Тестируем Logbroker с мок-режимом...")
    print("=" * 50)

    # 1. Тест health endpoint
    print("1. Проверяем health endpoint:")
    response = client.get("/health")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    print()

    # 2. Отправляем несколько тестовых логов
    print("2. Отправляем тестовые логи:")

    test_logs = [
        {
            "timestamp": "2024-01-15T12:00:00",
            "level": "INFO",
            "message": "Пользователь залогинился",
            "service": "auth",
            "extra": {"user_id": 123, "ip": "192.168.1.1"}
        },
        {
            "timestamp": "2024-01-15T12:00:01",
            "level": "WARNING",
            "message": "Медленный запрос к базе",
            "service": "database",
            "extra": {"query_time": 2.5, "query": "SELECT * FROM users"}
        },
        {
            "timestamp": "2024-01-15T12:00:02",
            "level": "ERROR",
            "message": "Ошибка подключения к Redis",
            "service": "cache",
            "extra": {"host": "redis://localhost", "error": "Connection refused"}
        }
    ]

    for i, log in enumerate(test_logs, 1):
        response = client.post("/write_log", json=log)
        print(f"   Лог {i}: {log['level']} - {log['message']}")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")

    print()

    # 3. Проверяем health снова (должен измениться buffer_size)
    print("3. Проверяем health после отправки логов:")
    response = client.get("/health")
    data = response.json()
    print(f"   Buffer size: {data['buffer_size']}")
    print(f"   Pending files: {data['pending_files']}")
    print()

    # 4. Ждем 2 секунды для срабатывания flush (раз в секунду)
    print("4. Ждем 2 секунды для автоматической отправки буфера...")
    await asyncio.sleep(2)

    # 5. Снова проверяем health (буфер должен очиститься)
    print("5. Проверяем health после ожидания:")
    response = client.get("/health")
    data = response.json()
    print(f"   Buffer size: {data['buffer_size']}")
    print(f"   Pending files: {data['pending_files']}")
    print()

    # 6. Проверяем файлы на диске
    print("6. Проверяем файлы в buffer/pending/:")
    import glob
    pending_files = glob.glob("buffer/pending/*.json")
    sent_files = glob.glob("buffer/sent/*.json")

    print(f"   Файлов в pending/: {len(pending_files)}")
    print(f"   Файлов в sent/: {len(sent_files)}")

    if pending_files:
        print("   Пример файла в pending/:")
        with open(pending_files[0], 'r') as f:
            print(f"   {json.load(f)}")

    print()
    print("=" * 50)
    print("✅ Тестирование завершено!")

    # Чистим тестовые файлы
    for f in pending_files + sent_files:
        os.remove(f)


if __name__ == "__main__":
    asyncio.run(test_logbroker())