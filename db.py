# db.py
# Xử lý kết nối và truy vấn cơ sở dữ liệu

import mysql.connector
import mysql.connector.pooling
from contextlib import contextmanager, asynccontextmanager
import logging
import asyncio
import json
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

# Thêm async context manager cho việc sử dụng với async/await
@asynccontextmanager
async def get_db_connection_async():
    """
    Async context manager để lấy và giải phóng kết nối từ pool
    """
    loop = asyncio.get_event_loop()
    if not pool:
        logger.error("Pool kết nối MySQL chưa được khởi tạo")
        raise Exception("Database connection pool not initialized")
        
    conn = None
    try:
        conn = await loop.run_in_executor(None, pool.get_connection)
        yield conn
    except mysql.connector.Error as err:
        logger.error(f"Lỗi MySQL: {err}")
        raise
    finally:
        if conn:
            await loop.run_in_executor(None, conn.close)

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
        # Bảng leaderboard với schema mở rộng
        execute_query("""
            CREATE TABLE IF NOT EXISTS leaderboard (
                id INT AUTO_INCREMENT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                player_id BIGINT NOT NULL,
                player_name VARCHAR(255) NOT NULL,
                score INT DEFAULT 0,
                games_played INT DEFAULT 0,
                wins INT DEFAULT 0,
                role_counts TEXT DEFAULT '{}',
                role_wins TEXT DEFAULT '{}',
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
                winner VARCHAR(20) DEFAULT NULL,
                players_count INT DEFAULT 0,
                werewolves_count INT DEFAULT 0,
                villagers_count INT DEFAULT 0,
                duration INT DEFAULT 0,
                players_data TEXT DEFAULT NULL,
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
        # Kiểm tra và thêm các cột mới vào bảng leaderboard
        columns_to_check = [
            ('wins', 'INT DEFAULT 0 AFTER games_played'),
            ('role_counts', 'TEXT DEFAULT \'{}\' AFTER wins'),
            ('role_wins', 'TEXT DEFAULT \'{}\' AFTER role_counts')
        ]
        
        for column_name, column_def in columns_to_check:
            check_query = """
                SELECT COUNT(*) as column_exists 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'leaderboard' AND COLUMN_NAME = %s
            """
            result, _ = execute_query(check_query, (DB_CONFIG["database"], column_name), fetch=True)
            
            # Nếu cột chưa tồn tại, thêm vào
            if result and result[0]['column_exists'] == 0:
                add_column_query = f"""
                    ALTER TABLE leaderboard ADD COLUMN {column_name} {column_def}
                """
                execute_query(add_column_query)
                logger.info(f"Đã thêm cột {column_name} vào bảng leaderboard")
        
        # Kiểm tra và thêm các cột mới vào bảng game_logs
        log_columns_to_check = [
            ('winner', 'VARCHAR(20) DEFAULT NULL AFTER log_message'),
            ('players_count', 'INT DEFAULT 0 AFTER timestamp'),
            ('werewolves_count', 'INT DEFAULT 0 AFTER players_count'),
            ('villagers_count', 'INT DEFAULT 0 AFTER werewolves_count'),
            ('duration', 'INT DEFAULT 0 AFTER villagers_count'),
            ('players_data', 'TEXT DEFAULT NULL AFTER duration')
        ]
        
        for column_name, column_def in log_columns_to_check:
            check_query = """
                SELECT COUNT(*) as column_exists 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'game_logs' AND COLUMN_NAME = %s
            """
            result, _ = execute_query(check_query, (DB_CONFIG["database"], column_name), fetch=True)
            
            # Nếu cột chưa tồn tại, thêm vào
            if result and result[0]['column_exists'] == 0:
                add_column_query = f"""
                    ALTER TABLE game_logs ADD COLUMN {column_name} {column_def}
                """
                execute_query(add_column_query)
                logger.info(f"Đã thêm cột {column_name} vào bảng game_logs")
            
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

async def update_player_stats(guild_id, user_id, player_name, win=False, role=""):
    """
    Cập nhật thống kê cho một người chơi
    
    Args:
        guild_id (int): ID của guild (server)
        user_id (int): ID của người chơi
        player_name (str): Tên hiển thị của người chơi
        win (bool): True nếu người chơi thắng
        role (str): Vai trò của người chơi trong game
    """
    try:
        # Điểm cộng thêm dựa trên kết quả
        score_change = 3 if win else 1
        
        # Kiểm tra người chơi đã tồn tại chưa
        query_check = """
            SELECT role_counts, role_wins FROM leaderboard
            WHERE guild_id = %s AND player_id = %s
        """
        results, _ = await execute_async_query(query_check, (guild_id, user_id), fetch=True)
        
        if results:
            # Người chơi đã tồn tại, cập nhật dữ liệu
            try:
                role_counts = json.loads(results[0]['role_counts']) if results[0]['role_counts'] else {}
                role_wins = json.loads(results[0]['role_wins']) if results[0]['role_wins'] else {}
            except (json.JSONDecodeError, TypeError):
                role_counts = {}
                role_wins = {}
                
            # Cập nhật số lần chơi và thắng theo vai trò
            role_counts[role] = role_counts.get(role, 0) + 1
            if win:
                role_wins[role] = role_wins.get(role, 0) + 1
                
            # Cập nhật record
            query_update = """
                UPDATE leaderboard SET
                score = score + %s,
                games_played = games_played + 1,
                wins = wins + %s,
                player_name = %s,
                role_counts = %s,
                role_wins = %s
                WHERE guild_id = %s AND player_id = %s
            """
            await execute_async_query(
                query_update,
                (score_change, 1 if win else 0, player_name, json.dumps(role_counts), json.dumps(role_wins), guild_id, user_id),
                fetch=False
            )
        else:
            # Người chơi chưa tồn tại, thêm mới
            role_counts = {role: 1}
            role_wins = {role: 1} if win else {role: 0}
            
            query_insert = """
                INSERT INTO leaderboard (guild_id, player_id, player_name, score, games_played, wins, role_counts, role_wins)
                VALUES (%s, %s, %s, %s, 1, %s, %s, %s)
            """
            await execute_async_query(
                query_insert,
                (guild_id, user_id, player_name, score_change, 1 if win else 0, json.dumps(role_counts), json.dumps(role_wins)),
                fetch=False
            )
            
        logger.info(f"Đã cập nhật thống kê cho người chơi {player_name} (ID: {user_id}) trong guild {guild_id}")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật thống kê người chơi: {str(e)}")
        return False

async def update_all_player_stats(game_state, winner="no_one"):
    """
    Cập nhật thống kê cho tất cả người chơi sau khi game kết thúc
    
    Args:
        game_state (dict): Trạng thái game hiện tại
        winner (str): Phe thắng cuộc ("werewolves", "villagers", "no_one")
    """
    try:
        guild_id = game_state.get("guild_id")
        if not guild_id:
            logger.error("Cannot update leaderboard: guild_id not found in game_state")
            return False
            
        update_tasks = []
        
        for user_id, data in game_state["players"].items():
            role = data.get("role", "Unknown")
            player_name = "Unknown"
            
            # Lấy tên người chơi từ member_cache nếu có
            if user_id in game_state.get("member_cache", {}):
                player_name = game_state["member_cache"][user_id].display_name
                
            # Xác định người chơi có thắng hay không
            is_winner = False
            
            if winner == "werewolves" and role in ["Werewolf", "Wolfman", "Demon Werewolf", "Assassin Werewolf"]:
                is_winner = True
            elif winner == "villagers" and role not in ["Werewolf", "Wolfman", "Demon Werewolf", "Assassin Werewolf"]:
                is_winner = True
                
            # Thêm task cập nhật cho người chơi này
            update_tasks.append(update_player_stats(guild_id, user_id, player_name, is_winner, role))
        
        # Thực hiện tất cả các cập nhật cùng lúc
        if update_tasks:
            await asyncio.gather(*update_tasks)
            logger.info(f"Updated leaderboard for {len(update_tasks)} players in guild {guild_id}")
            
            # Lưu log kết quả game
            werewolf_count = sum(1 for _, d in game_state["players"].items() 
                               if d.get("role") in ["Werewolf", "Wolfman", "Demon Werewolf", "Assassin Werewolf"])
            villager_count = len(game_state["players"]) - werewolf_count
            
            # Chuẩn bị dữ liệu người chơi để lưu vào logs
            players_data = {}
            for user_id, data in game_state["players"].items():
                player_name = "Unknown"
                if user_id in game_state.get("member_cache", {}):
                    player_name = game_state["member_cache"][user_id].display_name
                    
                players_data[user_id] = {
                    "name": player_name,
                    "role": data.get("role", "Unknown"),
                    "status": data.get("status", "unknown")
                }
                
            log_message = f"Game kết thúc. Kết quả: {winner.capitalize()} thắng!"
            
            await save_game_log(
                guild_id, 
                log_message, 
                winner, 
                len(game_state["players"]), 
                werewolf_count, 
                villager_count, 
                game_state.get("night_count", 0), 
                json.dumps(players_data)
            )
            
            return True
        
        return False
    except Exception as e:
        logger.error(f"Error updating all player stats: {str(e)}")
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
            SELECT player_name, score, games_played, wins, role_counts, role_wins 
            FROM leaderboard
            WHERE guild_id = %s
            ORDER BY score DESC
            LIMIT %s
        """
        
        results, _ = await execute_async_query(query, (guild_id, limit), fetch=True)
        return results
    except Exception as e:
        logger.error(f"Lỗi lấy dữ liệu leaderboard: {e}")
        return []

async def save_game_log(guild_id, log_message, winner=None, players_count=0, werewolves_count=0, villagers_count=0, duration=0, players_data=None):
    """
    Lưu log game vào cơ sở dữ liệu
    
    Args:
        guild_id (int): ID của guild
        log_message (str): Nội dung log
        winner (str, optional): Phe thắng cuộc
        players_count (int, optional): Số lượng người chơi
        werewolves_count (int, optional): Số lượng sói
        villagers_count (int, optional): Số lượng dân
        duration (int, optional): Số đêm đã qua
        players_data (str, optional): Dữ liệu JSON về người chơi
    """
    try:
        query = """
            INSERT INTO game_logs (
                guild_id, log_message, winner, players_count, 
                werewolves_count, villagers_count, duration, players_data
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        await execute_async_query(
            query, 
            (guild_id, log_message, winner, players_count, werewolves_count, villagers_count, duration, players_data), 
            fetch=False
        )
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
        query = """
            SELECT id, guild_id, timestamp, log_message, winner, 
            players_count, werewolves_count, villagers_count, duration, players_data
            FROM game_logs 
            WHERE guild_id = %s 
            ORDER BY timestamp DESC 
            LIMIT %s
        """
        
        results, _ = await execute_async_query(query, (guild_id, limit), fetch=True)
        return results
    except Exception as e:
        logger.error(f"Lỗi khi lấy game logs: {str(e)}")
        return []