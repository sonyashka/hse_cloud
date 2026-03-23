FROM python:3.12-slim

WORKDIR /app

# Устанавливаем системные зависимости для psycopg2 и других библиотек
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости и устанавливаем их
COPY src/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY src/ .

# Создаем пользователя для безопасности
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Создаем директории для буфера логов
RUN mkdir -p /app/buffer/pending /app/buffer/sent

# Открываем порт для FastAPI
EXPOSE 8080

# Запускаем приложение
CMD ["sh", "/entrypoint.sh"]
