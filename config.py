# config.py
# Cấu hình cho ứng dụng bot

import os
import logging
import sys
from dotenv import load_dotenv

# Đảm bảo biến môi trường được tải
load_dotenv()

# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)

logger = logging.getLogger("masoi_bot")

# Cấu hình cơ sở dữ liệu
DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
    "pool_name": "masoi_pool",
    "pool_size": 5
}

# Cấu hình Discord bot
DISCORD_TOKEN = os.getenv("TOKEN")

# Thiết lập API retry
API_MAX_RETRIES = 5
API_RETRY_DELAY = 2

# Thời gian cho các pha game (giây)
TIMINGS = {
    "morning_discussion": 120,
    "first_day": 30,
    "voting": 45,
    "night_action": 40,
    "witch_action": 20,
    "countdown_final": 15
}

# Các biến toàn cục cho trạng thái
game_states = {}  # Lưu trữ trạng thái game cho từng guild
game_logs = {}    # Lưu trữ logs game cho từng guild