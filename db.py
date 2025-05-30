# db.py
# Xử lý kết nối và truy vấn cơ sở dữ liệu

import mysql.connector
import mysql.connector.pooling
from contextlib import contextmanager
import logging
import asyncio
from config import DB_CONFIG

logger = logging.getLogger(__name__)

# Khởi tạo pool kết nối
try:
    pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name=DB_CONFIG["pool_name"],
        pool_size=DB_CONFIG["pool_size"],
        **{k: v for k, v in DB_CONFIG.items() if k not in ["pool_name", "pool_size"]}
    )
    logger.info(f"Đã khởi tạo pool kết nối MySQL với kích thước {DB_CONFIG['pool_size']}")
except mysql.connector.Error as err:
    logger.error(f"Lỗi khi khởi tạo pool kết nối MySQL: {err}")
    pool = None

@contextmanager
def get_db_connection():
    """
    Context manager để lấy và giải phóng kết nối từ pool
    """
    if not pool:
        logger.error("Pool kết nối MySQL chưa được khởi tạo")
        raise Exception("Database connection pool not initialized")
        
    conn = None
    try:
        conn = pool.get_connection()
        yield conn
    except mysql.connector.Error as err:
        logger.error(f"Lỗi MySQL: {err}")
        raise
    finally:
        if conn:
            conn.close()

def execute_query(query, params=None, fetch=False, commit=True):
    """
    Thực thi một truy vấn SQL và trả về kết quả nếu cần
    
    Args:
        query (str): Câu truy vấn SQL
        params (tuple, list, dict): Tham số cho truy vấn
        fetch (bool): Có lấy kết quả hay không
        commit (bool): Có commit sau khi thực hiện hay không
    
    Returns:
        list: Kết quả của truy vấn nếu fetch=True, None nếu không
    """
    result = None
    
    with get_db_connection() as conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
            
            if fetch:
                result = cursor.fetchall()
            
            if commit:
                conn.commit()
                
            affected_rows = cursor.rowcount
            cursor.close()
            
            return result, affected_rows
        except mysql.connector.Error as err:
            logger.error(f"Lỗi thực thi truy vấn: {err}")
            conn.rollback()
            raise

async def execute_async_query(query, params=None, fetch=False):
    """
    Thực thi truy vấn SQL một cách bất đồng bộ
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, 
        lambda: execute_query(query, params, fetch)
    )


def init_database():
    """
    Khởi tạo các bảng cần thiết trong cơ sở dữ liệu
    """
    try:
        # Bảng leaderboard
        execute_query("""
            CREATE TABLE IF NOT EXISTS leaderboard (
                id INT AUTO_INCREMENT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                player_id BIGINT NOT NULL,
                player_name VARCHAR(255) NOT NULL,
                score INT DEFAULT 0,
                games_played INT DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY unique_guild_player (guild_id, player_id),
                INDEX idx_guild_score (guild_id, score DESC)
            )
        """)
        
        # Bảng game_logs
        execute_query("""
            CREATE TABLE IF NOT EXISTS game_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                log_message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_guild_time (guild_id, timestamp DESC)
            )
        """)
        
        # Kiểm tra và cập nhật schema nếu cần
        update_database_schema()
        
        logger.info("Đã khởi tạo các bảng trong cơ sở dữ liệu")
    except Exception as e:
        logger.error(f"Lỗi khởi tạo cơ sở dữ liệu: {e}")

def update_database_schema():
    """
    Cập nhật cấu trúc cơ sở dữ liệu khi có thay đổi
    """
    try:
        # Kiểm tra xem cột games_played đã tồn tại chưa
        check_query = """
            SELECT COUNT(*) as column_exists 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'leaderboard' AND COLUMN_NAME = 'games_played'
        """
        result, _ = execute_query(check_query, (DB_CONFIG["database"],), fetch=True)
        
        # Nếu cột chưa tồn tại, thêm vào
        if result and result[0]['column_exists'] == 0:
            add_column_query = """
                ALTER TABLE leaderboard ADD COLUMN games_played INT DEFAULT 0 AFTER score
            """
            execute_query(add_column_query)
            logger.info("Đã thêm cột games_played vào bảng leaderboard")
            
        return True
    except Exception as e:
        logger.error(f"Lỗi cập nhật schema database: {e}")
        return False

async def update_leaderboard(guild_id, player_updates):
    """
    Cập nhật leaderboard cho nhiều người chơi
    
    Args:
        guild_id (int): ID của guild (server)
        player_updates (dict): Dictionary chứa thông tin cập nhật điểm cho từng người chơi
            {player_id: {"name": "Player Name", "score": 3}}
    """
    try:
        updates = []
        
        for player_id, data in player_updates.items():
            updates.append((
                guild_id,
                player_id, 
                data["name"], 
                data["score"],
                data["score"]
            ))
        
        if updates:
            query = """
                INSERT INTO leaderboard (guild_id, player_id, player_name, score, games_played)
                VALUES (%s, %s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                player_name = VALUES(player_name),
                score = score + VALUES(score),
                games_played = games_played + 1
            """
            
            await execute_async_query(query, updates, fetch=False)
            logger.info(f"Cập nhật leaderboard thành công cho {len(updates)} người chơi trong guild {guild_id}")
            return True
    except Exception as e:
        logger.error(f"Lỗi cập nhật leaderboard: {e}")
        return False

async def get_leaderboard(guild_id, limit=10):
    """
    Lấy bảng xếp hạng cho một guild
    
    Args:
        guild_id (int): ID của guild
        limit (int): Số lượng người chơi tối đa
    
    Returns:
        list: Danh sách người chơi và điểm
    """
    try:
        query = """
            SELECT player_name, score, games_played FROM leaderboard
            WHERE guild_id = %s
            ORDER BY score DESC
            LIMIT %s
        """
        
        results, _ = await execute_async_query(query, (guild_id, limit), fetch=True)
        return results
    except Exception as e:
        logger.error(f"Lỗi lấy dữ liệu leaderboard: {e}")
        return []

async def save_game_log(guild_id, log_message):
    """
    Lưu log game vào cơ sở dữ liệu
    
    Args:
        guild_id (int): ID của guild
        log_message (str): Nội dung log
    """
    try:
        query = """
            INSERT INTO game_logs (guild_id, log_message)
            VALUES (%s, %s)
        """
        
        await execute_async_query(query, (guild_id, log_message), fetch=False)
        return True
    except Exception as e:
        logger.error(f"Lỗi lưu game log: {e}")
        return False

async def get_game_logs(guild_id, limit=10):
    """
    Lấy lịch sử game log từ database
    
    Args:
        guild_id (int): ID của server
        limit (int): Số lượng bản ghi tối đa muốn lấy
        
    Returns:
        list: Danh sách các bản ghi game, hoặc list rỗng nếu không có
    """
    try:
        conn = await get_db_connection()
        # Thay đổi: Đảm bảo sử dụng "await" thay vì "with await"
        cursor = await conn.execute(
            "SELECT * FROM game_logs WHERE guild_id = ? ORDER BY timestamp DESC LIMIT ?", 
            (guild_id, limit)
        )
        rows = await cursor.fetchall()
        await conn.close()
        
        result = []
        for row in rows:
            result.append({
                "id": row[0],
                "guild_id": row[1],
                "timestamp": row[2],
                "players_count": row[3],
                "werewolves_count": row[4],
                "villagers_count": row[5],
                "winner": row[6],
                "duration": row[7],
                "players_data": row[8]
            })
        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy game logs: {str(e)}")
        return []