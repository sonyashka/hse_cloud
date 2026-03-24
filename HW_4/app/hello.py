from flask import Flask
import os
import psycopg2
import socket

app = Flask(__name__)
version = os.environ.get('APP_VERSION', '1.0.0')
db_host = os.environ.get('DB_HOST', 'localhost')
db_name = os.environ.get('DB_NAME', 'testdb')
db_user = os.environ.get('DB_USER', 'postgres')
db_password = os.environ.get('DB_PASSWORD', '')

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password
        )
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

@app.route('/')
def hello_world():
    hostname = socket.gethostname()
    return f'Hello from Pod: {hostname}'

@app.route('/version')
def show_version():
    return f'Version: {version}'

@app.route('/health')
def health_check():
    return 'OK', 200

@app.route('/db-check')
def db_check():
    conn = get_db_connection()
    if conn:
        conn.close()
        return 'Database connection successful'
    return 'Database connection failed', 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)