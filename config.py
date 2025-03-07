import os


# Настройки Redis
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Команды бота
BOT_COMMANDS = [
    # ("start", "cmd-start"),
    # ("help", "cmd-help"),
    # ("subscription", "cmd-subscription"),
    # ("subscription_terms", "cmd-subscription-terms"), 
    # ("support", "cmd-support")
]

# Настройки NATS
NATS_URL = os.getenv("NATS_URL", "nats://nats:4222")


