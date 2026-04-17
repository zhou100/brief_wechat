import subprocess
import time
import socket
import sys

def wait_for_db():
    print("Waiting for database to be ready...")
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect(('db', 5432))
                print("Database is ready!")
                return
        except socket.error:
            print("Database not ready yet, waiting...")
            time.sleep(1)

def run_migrations():
    print("Running database migrations...")
    result = subprocess.run(['alembic', 'upgrade', 'head'], capture_output=True, text=True)
    if result.returncode != 0:
        print("Error running migrations:", result.stderr)
        sys.exit(1)
    print("Migrations completed successfully!")

def start_app():
    print("Starting FastAPI application...")
    subprocess.run(['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '10000', '--reload'])

if __name__ == '__main__':
    wait_for_db()
    run_migrations()
    start_app()
