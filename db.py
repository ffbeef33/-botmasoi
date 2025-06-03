# db.py
# Xử lý kết nối và truy vấn cơ sở dữ liệu

import mysql.connector
import mysql.connector.pooling
from contextlib import contextmanager, asynccontextmanager
import logging
import asyncio
import json
import traceback
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

def test_database_connection():
    """Kiểm tra kết nối cơ sở dữ liệu và trả về trạng thái"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            if result and result[0] == 1:
                logger.info("Kiểm tra kết nối cơ sở dữ liệu thành công")
                return True
            else:
                logger.error("Kiểm tra kết nối cơ sở dữ liệu thất bại")
                return False
    except mysql.connector.Error as err:
        logger.error(f"Lỗi kiểm tra kết nối cơ sở dữ liệu: {err}")
        return False
    except Exception as e:
        logger.error(f"Lỗi không xác định khi kiểm tra kết nối: {str(e)}")
        return False

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
        logger.error(f"Lỗi MySQL khi lấy kết nối: {err}")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.error(f"Lỗi khi đóng kết nối: {str(e)}")

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
        logger.error(f"Lỗi MySQL khi lấy kết nối async: {err}")
        raise
    finally:
        if conn:
            try:
                await loop.run_in_executor(None, conn.close)
            except Exception as e:
                logger.error(f"Lỗi khi đóng kết nối async: {str(e)}")

def execute_query(query, params=None, fetch=False, commit=True, many=False):
    """
    Thực thi một truy vấn SQL và trả về kết quả nếu cần
    
    Args:
        query (str): Câu truy vấn SQL
        params (tuple, list, dict): Tham số cho truy vấn
        fetch (bool): Có lấy kết quả hay không
        commit (bool): Có commit sau khi thực hiện hay không
        many (bool): Có phải thực hiện executemany không
    
    Returns:
        list: Kết quả của truy vấn nếu fetch=True, None nếu không
        int: Số dòng bị ảnh hưởng
    """
    result = None
    
    try:
        if not pool:
            logger.error("Không thể thực thi truy vấn: Pool kết nối MySQL chưa được khởi tạo")
            return None, 0
            
        with get_db_connection() as conn:
            try:
                cursor = conn.cursor(dictionary=True)
                
                # Ghi log truy vấn và tham số để gỡ lỗi
                logger.debug(f"Thực thi truy vấn: {query}")
                logger.debug(f"Với tham số: {params}")
                
                # Xử lý các loại tham số khác nhau
                if many and isinstance(params, (list, tuple)):
                    cursor.executemany(query, params)
                    logger.debug(f"Đã thực thi executemany với {len(params)} dòng dữ liệu")
                else:
                    cursor.execute(query, params or ())
                
                if fetch:
                    result = cursor.fetchall()
                
                if commit:
                    conn.commit()
                    logger.debug(f"Truy vấn đã commit với {cursor.rowcount} dòng bị ảnh hưởng")
                
                affected_rows = cursor.rowcount
                cursor.close()
                
                return result, affected_rows
            except mysql.connector.Error as err:
                conn.rollback()
                error_message = f"Lỗi MySQL: {err}, Mã: {err.errno}"
                if hasattr(err, 'sqlstate'):
                    error_message += f", SQLState: {err.sqlstate}"
                logger.error(error_message)
                logger.error(f"Truy vấn thất bại: {query}")
                logger.error(f"Tham số: {params}")
                raise
    except Exception as e:
        logger.error(f"Lỗi kết nối cơ sở dữ liệu: {str(e)}")
        logger.error(traceback.format_exc())
        raise

async def execute_async_query(query, params=None, fetch=False, many=False):
    """
    Thực thi truy vấn SQL một cách bất đồng bộ
    
    Args:
        query (str): Câu truy vấn SQL
        params (tuple, list, dict): Tham số cho truy vấn
        fetch (bool): Có lấy kết quả hay không
        many (bool): Có phải thực hiện executemany không
    
    Returns:
        list: Kết quả của truy vấn nếu fetch=True, None nếu không
        int: Số dòng bị ảnh hưởng
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, 
        lambda: execute_query(query, params, fetch, True, many)
    )

def init_database():
    """
    Khởi tạo các bảng cần thiết trong cơ sở dữ liệu
    """
    try:
        # Kiểm tra kết nối trước
        if not test_database_connection():
            logger.error("Kiểm tra kết nối cơ sở dữ liệu thất bại trong quá trình khởi tạo")
            return False
            
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
        return True
    except Exception as e:
        logger.error(f"Lỗi khởi tạo cơ sở dữ liệu: {e}")
        logger.error(traceback.format_exc())
        return False

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
        logger.error(traceback.format_exc())
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
        # Kiểm tra kết nối
        if not pool:
            logger.error("Không thể cập nhật leaderboard: Pool kết nối MySQL chưa được khởi tạo")
            return False
            
        # Chuyển đổi guild_id sang số nguyên để đảm bảo đúng kiểu
        guild_id = int(guild_id)
        updates = []
        
        # Chuẩn bị dữ liệu cập nhật
        for player_id, data in player_updates.items():
            # Đảm bảo player_id là số nguyên
            player_id_int = int(player_id)
            player_name = data.get("name", "Unknown Player")
            score = data.get("score", 0)
            
            if not player_name or player_name == "Unknown Player":
                logger.warning(f"Người chơi {player_id_int} không có tên hợp lệ")
            
            updates.append((
                guild_id,
                player_id_int, 
                player_name, 
                score,
                1  # games_played
            ))
        
        if updates:
            # Sử dụng Insert ... ON DUPLICATE KEY UPDATE để cập nhật hàng loạt
            query = """
                INSERT INTO leaderboard (guild_id, player_id, player_name, score, games_played)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                player_name = VALUES(player_name),
                score = score + VALUES(score),
                games_played = games_played + 1
            """
            
            # Sử dụng executemany để cập nhật tất cả trong một lần
            try:
                _, affected_rows = await execute_async_query(query, updates, fetch=False, many=True)
                if affected_rows > 0:
                    logger.info(f"Cập nhật leaderboard thành công cho {len(updates)} người chơi trong guild {guild_id}")
                else:
                    logger.warning(f"Cập nhật leaderboard không ảnh hưởng đến dòng nào")
                return True
            except Exception as e:
                # Nếu executemany thất bại, thử lại từng cập nhật một
                logger.warning(f"Cập nhật hàng loạt thất bại, đang thử cập nhật từng người: {str(e)}")
                success_count = 0
                for update in updates:
                    try:
                        _, affected = await execute_async_query(query, update, fetch=False)
                        if affected > 0:
                            success_count += 1
                    except Exception as inner_e:
                        logger.error(f"Cập nhật thất bại cho người chơi {update[1]}: {str(inner_e)}")
                
                logger.info(f"Cập nhật leaderboard thành công cho {success_count}/{len(updates)} người chơi trong guild {guild_id}")
                return success_count > 0
        else:
            logger.warning("Không có dữ liệu cập nhật cho leaderboard")
            return False
    except Exception as e:
        logger.error(f"Lỗi cập nhật leaderboard: {e}")
        logger.error(traceback.format_exc())
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
        # Chuyển đổi ID sang số nguyên để đảm bảo đúng kiểu
        guild_id = int(guild_id)
        user_id = int(user_id)
        
        # Sanitize player_name
        if not player_name or player_name == "":
            player_name = "Unknown Player"
            
        # Sanitize role
        if not role or role == "":
            role = "Unknown"
            
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
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Lỗi phân tích JSON cho người chơi {user_id}: {e}")
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
            
            params = (
                score_change, 
                1 if win else 0, 
                player_name, 
                json.dumps(role_counts), 
                json.dumps(role_wins), 
                guild_id, 
                user_id
            )
            
            _, affected_rows = await execute_async_query(query_update, params)
            
            if affected_rows == 0:
                logger.warning(f"Cập nhật cho người chơi {player_name} ({user_id}) không có tác dụng")
                return False
            else:
                logger.info(f"Đã cập nhật thống kê cho người chơi {player_name} ({user_id}): +{score_change} điểm, thắng={win}")
                return True
                
        else:
            # Người chơi chưa tồn tại, thêm mới
            role_counts = {role: 1}
            role_wins = {role: 1} if win else {role: 0}
            
            query_insert = """
                INSERT INTO leaderboard (guild_id, player_id, player_name, score, games_played, wins, role_counts, role_wins)
                VALUES (%s, %s, %s, %s, 1, %s, %s, %s)
            """
            
            params = (
                guild_id, 
                user_id, 
                player_name, 
                score_change, 
                1 if win else 0, 
                json.dumps(role_counts), 
                json.dumps(role_wins)
            )
            
            _, affected_rows = await execute_async_query(query_insert, params)
            
            if affected_rows == 0:
                logger.warning(f"Thêm mới người chơi {player_name} ({user_id}) không có tác dụng")
                return False
            else:
                logger.info(f"Đã thêm người chơi mới {player_name} ({user_id}) với {score_change} điểm, thắng={win}")
                return True
            
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật thống kê người chơi {player_name} ({user_id}): {str(e)}")
        logger.error(traceback.format_exc())
        return False

async def update_all_player_stats(game_state, winner="no_one"):
    """
    Cập nhật thống kê cho tất cả người chơi sau khi game kết thúc
    
    Args:
        game_state (dict): Trạng thái game hiện tại
        winner (str): Phe thắng cuộc ("werewolves", "villagers", "no_one")
    """
    try:
        # Kiểm tra kết nối
        if not pool:
            logger.error("Không thể cập nhật player stats: Pool kết nối MySQL chưa được khởi tạo")
            return False
            
        guild_id = game_state.get("guild_id")
        if not guild_id:
            logger.error("Cannot update leaderboard: guild_id not found in game_state")
            return False
            
        # Đảm bảo guild_id là số nguyên
        guild_id = int(guild_id)
            
        update_tasks = []
        player_updates = {}
        
        # In thông tin game_state để debug
        logger.debug(f"Game state type: {type(game_state)}")
        logger.debug(f"Game state keys: {list(game_state.keys() if hasattr(game_state, 'keys') else [])}")
        
        # Kiểm tra cấu trúc của players
        if not game_state.get("players"):
            logger.error("Game state không chứa thông tin người chơi")
            return False
            
        # Đảm bảo member_cache tồn tại
        if not game_state.get("member_cache"):
            logger.warning("Game state không có member_cache, sử dụng tên mặc định")
            game_state["member_cache"] = {}
            
        for user_id_raw, data in game_state["players"].items():
            # Đảm bảo user_id luôn là int
            user_id = int(user_id_raw)
            user_id_str = str(user_id)
            
            # Lấy vai trò người chơi
            role = data.get("role", "Unknown")
            player_name = "Unknown Player"
            
            # Thử lấy tên người chơi từ member_cache - kiểm tra cả dạng string và int key
            if user_id_str in game_state.get("member_cache", {}):
                member = game_state["member_cache"][user_id_str]
                player_name = getattr(member, "display_name", "Unknown Player")
            elif user_id in game_state.get("member_cache", {}):
                member = game_state["member_cache"][user_id]
                player_name = getattr(member, "display_name", "Unknown Player")
                
            # Xác định người chơi có thắng hay không
            is_winner = False
            
            if winner == "werewolves":
                if role in ["Werewolf", "Wolfman", "Demon Werewolf", "Assassin Werewolf", "Illusionist"]:
                    is_winner = True
            elif winner == "villagers":
                if role not in ["Werewolf", "Wolfman", "Demon Werewolf", "Assassin Werewolf"]:
                    is_winner = True
            
            # Ghi log thông tin cập nhật
            logger.info(f"Chuẩn bị cập nhật: Player={player_name}, ID={user_id}, Role={role}, Winner={is_winner}")
            
            # Thêm task cập nhật cho người chơi này
            update_tasks.append(update_player_stats(guild_id, user_id, player_name, is_winner, role))
            
            # Cập nhật dictionary cho update_leaderboard (phương pháp backup)
            player_updates[user_id] = {
                "name": player_name,
                "score": 3 if is_winner else 1
            }
        
        # Thực hiện tất cả các cập nhật cùng lúc
        if update_tasks:
            # Đầu tiên thử phương pháp update_leaderboard
            try:
                logger.info("Bắt đầu cập nhật leaderboard bằng phương pháp hàng loạt")
                batch_update_successful = await update_leaderboard(guild_id, player_updates)
                if batch_update_successful:
                    logger.info(f"Cập nhật hàng loạt thành công cho {len(player_updates)} người chơi")
                else:
                    logger.warning("Cập nhật hàng loạt thất bại, đang thử phương pháp cập nhật riêng lẻ")
                    raise Exception("Batch update failed")
            except Exception:
                # Nếu thất bại, thử phương pháp cập nhật riêng lẻ
                logger.info("Đang thực hiện cập nhật riêng lẻ")
                results = await asyncio.gather(*update_tasks, return_exceptions=True)
                
                # Kiểm tra kết quả
                success_count = sum(1 for r in results if r is True)
                error_count = sum(1 for r in results if isinstance(r, Exception))
                failed_count = len(results) - success_count - error_count
                
                logger.info(f"Kết quả cập nhật riêng lẻ: {success_count} thành công, {failed_count} thất bại, {error_count} lỗi")
                
                # Log lỗi chi tiết
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Lỗi cập nhật người chơi thứ {i}: {str(result)}")
            
            # Lưu log kết quả game
            try:
                werewolf_count = sum(1 for _, d in game_state["players"].items() 
                                if d.get("role") in ["Werewolf", "Wolfman", "Demon Werewolf", "Assassin Werewolf", "Illusionist"])
                villager_count = len(game_state["players"]) - werewolf_count
                
                # Chuẩn bị dữ liệu người chơi để lưu vào logs
                players_data = {}
                for user_id_raw, data in game_state["players"].items():
                    user_id = int(user_id_raw)
                    user_id_str = str(user_id)
                    player_name = "Unknown Player"
                    
                    if user_id_str in game_state.get("member_cache", {}):
                        member = game_state["member_cache"][user_id_str]
                        player_name = getattr(member, "display_name", "Unknown Player")
                    elif user_id in game_state.get("member_cache", {}):
                        member = game_state["member_cache"][user_id]
                        player_name = getattr(member, "display_name", "Unknown Player")
                        
                    players_data[user_id_str] = {
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
            except Exception as e:
                logger.error(f"Lỗi khi lưu log game: {str(e)}")
                logger.error(traceback.format_exc())
            
            return True
        
        logger.warning("Không có người chơi nào để cập nhật")
        return False
    except Exception as e:
        logger.error(f"Error updating all player stats: {str(e)}")
        logger.error(traceback.format_exc())
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
        guild_id = int(guild_id)
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
        logger.error(traceback.format_exc())
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
        guild_id = int(guild_id)
        query = """
            INSERT INTO game_logs (
                guild_id, log_message, winner, players_count, 
                werewolves_count, villagers_count, duration, players_data
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        params = (guild_id, log_message, winner, players_count, werewolves_count, villagers_count, duration, players_data)
        _, affected_rows = await execute_async_query(query, params)
        
        if affected_rows > 0:
            logger.info(f"Đã lưu log game cho guild {guild_id}: {winner} thắng")
            return True
        else:
            logger.warning(f"Không thể lưu log game cho guild {guild_id}")
            return False
    except Exception as e:
        logger.error(f"Lỗi lưu game log: {e}")
        logger.error(traceback.format_exc())
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
        guild_id = int(guild_id)
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
        logger.error(traceback.format_exc())
        return []
