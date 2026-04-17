"""
Worker entrypoint — run alongside the API server.
Processes audio jobs from the SQL queue.

Usage: python scripts/worker.py
Docker: set command to this script in docker-compose worker service.
"""
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

from app.services.worker import run_worker

if __name__ == "__main__":
    asyncio.run(run_worker())
