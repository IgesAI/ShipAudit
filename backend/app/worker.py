import os

from redis import Redis
from rq import Worker

from app.core.config import settings


def main() -> None:
    redis = Redis.from_url(settings.redis_url)
    queues = os.getenv("QUEUES", "default,audit,ingestion").split(",")
    worker = Worker(queues, connection=redis)
    worker.work()


if __name__ == "__main__":
    main()
