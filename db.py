# db.py
# Xử lý kết nối và truy vấn cơ sở dữ liệu

import mysql.connector
import mysql.connector.pooling
from contextlib import contextmanager, asynccontextmanager
import logging
import asyncio
import json
import traceback
import time
from config import DB_CONFIG

logger = logging.getLogger(__name__)

# Khởi tạo pool kết nối
pool = None
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
except Exception as e:
    logger.error(f"Lỗi không xác định khi khởi tạo pool kết nối: {str(e)}")
    pool = None

def test_database_connection():
    """Kiểm tra kết nối cơ sở dữ liệu và trả về trạng thái"""
    global pool
    try:
        if not pool:
            logger.error("Pool kết nối MySQL chưa được khởi tạo")
            return False
            
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

def reconnect_pool():
    """Thử kết nối lại pool nếu bị ngắt kết nối"""
    global pool
    try:
        if pool:
            logger.info("Đang đóng pool cũ và tạo lại pool mới...")
            pool = None
            
        pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name=DB_CONFIG["pool_name"],
            pool_size=DB_CONFIG["pool_size"],
            **{k: v for k, v in DB_CONFIG.items() if k not in ["pool_name", "pool_size"]}
        )
        logger.info(f"Đã tái tạo pool kết nối MySQL với kích thước {DB_CONFIG['pool_size']}")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi tái tạo pool kết nối: {str(e)}")
        return False

@contextmanager
def get_db_connection(max_retries=3):
    """
    Context manager để lấy và giải phóng kết nối từ pool
    
    Args:
        max_retries (int): Số lần thử lại tối đa nếu lỗi kết nối
    """
    global pool
    conn = None
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            if not pool:
                logger.error("Pool kết nối MySQL chưa được khởi tạo")
                reconnect_pool()
                if not pool:
                    raise Exception("Database connection pool not initialized")
            
            conn = pool.get_connection()
            yield conn
            break
        except mysql.connector.errors.PoolError as err:
            logger.error(f"Lỗi pool kết nối ({retry_count+1}/{max_retries}): {err}")
            retry_count += 1
            if retry_count >= max_retries:
                raise
            time.sleep(1)
            reconnect_pool()
        except mysql.connector.errors.InterfaceError as err:
            logger.error(f"Lỗi interface ({retry_count+1}/{max_retries}): {err}")
            retry_count += 1
            if retry_count >= max_retries:
                raise
            time.sleep(1)
            reconnect_pool()
        except mysql.connector.Error as err:
            logger.error(f"Lỗi MySQL khi lấy kết nối: {err}")
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    logger.error(f"Lỗi khi đóng kết nối: {str(e)}")

@asynccontextmanager
async def get_db_connection_async(max_retries=3):
    """
    Async context manager để lấy và giải phóng kết nối từ pool
    
    Args:
        max_retries (int): Số lần thử lại tối đa nếu lỗi kết nối
    """
    global pool
    loop = asyncio.get_event_loop()
    conn = None
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            if not pool:
                logger.error("Pool kết nối MySQL chưa được khởi tạo")
                await loop.run_in_executor(None, reconnect_pool)
                if not pool:
                    raise Exception("Database connection pool not initialized")
            
            conn = await loop.run_in_executor(None, pool.get_connection)
            yield conn
            break
        except mysql.connector.errors.PoolError as err:
            logger.error(f"Lỗi pool kết nối async ({retry_count+1}/{max_retries}): {err}")
            retry_count += 1
            if retry_count >= max_retries:
                raise
            await asyncio.sleep(1)
            await loop.run_in_executor(None, reconnect_pool)
        except mysql.connector.errors.InterfaceError as err:
            logger.error(f"Lỗi interface async ({retry_count+1}/{max_retries}): {err}")
            retry_count += 1
            if retry_count >= max_retries:
                raise
            await asyncio.sleep(1)
            await loop.run_in_executor(None, reconnect_pool)
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
    conn = None
    cursor = None
    
    try:
        if not test_database_connection():
            logger.error("Kiểm tra kết nối cơ sở dữ liệu thất bại, đang thử kết nối lại...")
            reconnect_pool()
            if not test_database_connection():
                raise Exception("Không thể kết nối đến cơ sở dữ liệu")
            
        with get_db_connection() as conn:
            try:
                cursor = conn.cursor(dictionary=True)
                
                # Ghi log truy vấn và tham số để gỡ lỗi
                logger.debug(f"Thực thi truy vấn: {query}")
                
                # In tham số dưới dạng không gây lỗi
                try:
                    if params:
                        if isinstance(params, list) and len(params) > 10:
                            logger.debug(f"Với {len(params)} tham số (showing first 2): {params[:2]}")
                        else:
                            logger.debug(f"Với tham số: {params}")
                except:
                    logger.debug("Không thể in tham số truy vấn")
                
                # Xử lý các loại tham số khác nhau
                if many and isinstance(params, (list, tuple)) and params:
                    try:
                        cursor.executemany(query, params)
                        logger.debug(f"Đã thực thi executemany với {len(params)} dòng dữ liệu")
                    except Exception as e:
                        logger.error(f"Lỗi executemany: {str(e)}")
                        # Thử phương án thay thế: thực hiện từng truy vấn một
                        cursor.close()
                        cursor = conn.cursor(dictionary=True)
                        success_count = 0
                        for p in params:
                            try:
                                cursor.execute(query, p)
                                if commit:
                                    conn.commit()
                                success_count += 1
                            except Exception as inner_e:
                                logger.error(f"Lỗi thực thi truy vấn đơn: {str(inner_e)} với tham số {p}")
                        logger.info(f"Đã thực thi {success_count}/{len(params)} truy vấn")
                else:
                    cursor.execute(query, params or ())
                
                if fetch:
                    result = cursor.fetchall()
                
                if commit:
                    conn.commit()
                    logger.debug(f"Truy vấn đã commit với {cursor.rowcount} dòng bị ảnh hưởng")
                
                affected_rows = cursor.rowcount
                return result, affected_rows
            except mysql.connector.Error as err:
                conn.rollback()
                error_message = f"Lỗi MySQL: {err}, Mã: {err.errno}"
                if hasattr(err, 'sqlstate'):
                    error_message += f", SQLState: {err.sqlstate}"
                logger.error(error_message)
                logger.error(f"Truy vấn thất bại: {query}")
                try:
                    logger.error(f"Tham số: {params}")
                except:
                    logger.error("Không thể in tham số truy vấn")
                raise
            finally:
                if cursor:
                    cursor.close()
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
            reconnect_pool()
            if not test_database_connection():
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

async def direct_update_leaderboard(guild_id, user_id, player_name, points=1, wins=0, role="Unknown"):
    """
    Cập nhật trực tiếp leaderboard cho một người chơi duy nhất - phương pháp đơn giản nhất
    
    Args:
        guild_id (int): ID của guild (server)
        user_id (int): ID của người chơi
        player_name (str): Tên hiển thị của người chơi
        points (int): Điểm thưởng
        wins (int): Số trận thắng (0 hoặc 1)
        role (str): Vai trò của người chơi
    """
    try:
        # Đảm bảo các giá trị là số nguyên
        guild_id = int(guild_id)
        user_id = int(user_id)
        
        # Kiểm tra player_name
        if not player_name or player_name == "":
            player_name = "Unknown Player"
        
        # Kiểm tra xem người chơi đã tồn tại chưa
        check_query = "SELECT id, role_counts, role_wins FROM leaderboard WHERE guild_id = %s AND player_id = %s"
        result, _ = await execute_async_query(check_query, (guild_id, user_id), fetch=True)
        
        if result:
            # Người chơi đã tồn tại, cập nhật
            try:
                role_counts = json.loads(result[0].get('role_counts', '{}')) if result[0].get('role_counts') else {}
                role_wins = json.loads(result[0].get('role_wins', '{}')) if result[0].get('role_wins') else {}
            except:
                role_counts = {}
                role_wins = {}
            
            # Cập nhật số lần chơi và thắng theo vai trò
            role_counts[role] = role_counts.get(role, 0) + 1
            if wins > 0:
                role_wins[role] = role_wins.get(role, 0) + 1
            
            # Cập nhật bảng
            update_query = """
                UPDATE leaderboard SET
                score = score + %s,
                games_played = games_played + 1,
                wins = wins + %s,
                player_name = %s,
                role_counts = %s,
                role_wins = %s
                WHERE guild_id = %s AND player_id = %s
            """
            
            params = (points, wins, player_name, json.dumps(role_counts), json.dumps(role_wins), guild_id, user_id)
            await execute_async_query(update_query, params)
            logger.info(f"Đã cập nhật leaderboard cho {player_name} ({user_id}): +{points} điểm, +{wins} thắng")
            
        else:
            # Thêm người chơi mới
            role_counts = {role: 1}
            role_wins = {role: 1} if wins > 0 else {role: 0}
            
            insert_query = """
                INSERT INTO leaderboard (guild_id, player_id, player_name, score, games_played, wins, role_counts, role_wins)
                VALUES (%s, %s, %s, %s, 1, %s, %s, %s)
            """
            
            params = (guild_id, user_id, player_name, points, wins, json.dumps(role_counts), json.dumps(role_wins))
            await execute_async_query(insert_query, params)
            logger.info(f"Đã thêm người chơi mới vào leaderboard: {player_name} ({user_id}): {points} điểm")
            
        return True
    except Exception as e:
        logger.error(f"Lỗi cập nhật leaderboard cho {player_name} ({user_id}): {str(e)}")
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
        if not test_database_connection():
            logger.error("Không thể cập nhật leaderboard: Kiểm tra kết nối cơ sở dữ liệu thất bại")
            reconnect_pool()
            if not test_database_connection():
                return False
            
        # Chuyển đổi guild_id sang số nguyên để đảm bảo đúng kiểu
        guild_id = int(guild_id)
        
        if not player_updates:
            logger.warning("update_leaderboard: Không có dữ liệu cập nhật")
            return False
            
        # Log chi tiết thông tin cập nhật
        logger.info(f"update_leaderboard: Đang cập nhật cho {len(player_updates)} người chơi trong guild {guild_id}")
        for player_id, data in player_updates.items():
            logger.info(f"  - Player {player_id}: name={data.get('name', 'Unknown')}, score={data.get('score', 0)}")
            
        # Thực hiện cập nhật từng người một để tránh lỗi batch
        success_count = 0
        for player_id, data in player_updates.items():
            try:
                # Đảm bảo player_id là số nguyên
                player_id_int = int(player_id)
                player_name = data.get("name", "Unknown Player")
                score = data.get("score", 0)
                
                # Sử dụng truy vấn INSERT ... ON DUPLICATE KEY UPDATE
                query = """
                    INSERT INTO leaderboard (guild_id, player_id, player_name, score, games_played)
                    VALUES (%s, %s, %s, %s, 1)
                    ON DUPLICATE KEY UPDATE
                    player_name = VALUES(player_name),
                    score = score + VALUES(score),
                    games_played = games_played + 1
                """
                
                params = (guild_id, player_id_int, player_name, score)
                _, affected = await execute_async_query(query, params)
                
                if affected > 0:
                    success_count += 1
                    logger.debug(f"Cập nhật thành công cho {player_name} ({player_id_int})")
                else:
                    logger.warning(f"Không có dòng nào được cập nhật cho {player_name} ({player_id_int})")
                    
            except Exception as e:
                logger.error(f"Lỗi cập nhật cho người chơi {player_id}: {str(e)}")
                
        logger.info(f"Đã cập nhật leaderboard cho {success_count}/{len(player_updates)} người chơi trong guild {guild_id}")
        return success_count > 0
    except Exception as e:
        logger.error(f"Lỗi tổng thể trong update_leaderboard: {e}")
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
        # Kiểm tra kết nối database
        if not test_database_connection():
            logger.error(f"Không thể cập nhật thống kê cho {player_name}: Kết nối database không khả dụng")
            reconnect_pool()
            if not test_database_connection():
                return False
        
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
        
        logger.info(f"update_player_stats: Guild {guild_id}, Player {user_id} ({player_name}), Role {role}, Win {win}, Points {score_change}")
        
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
        if not test_database_connection():
            logger.error("Không thể cập nhật player stats: Kết nối cơ sở dữ liệu không khả dụng")
            reconnect_pool()
            if not test_database_connection():
                return False
            
        # Kiểm tra dữ liệu đầu vào
        guild_id = game_state.get("guild_id")
        if not guild_id:
            logger.error("Cannot update leaderboard: guild_id not found in game_state")
            return False
        
        # Đảm bảo guild_id là số nguyên
        guild_id = int(guild_id)
        
        # Kiểm tra dữ liệu players
        if not game_state.get("players"):
            logger.error("Game state không chứa thông tin người chơi")
            return False
            
        # Hiển thị chi tiết thông tin game_state để debug
        logger.info(f"update_all_player_stats: winner={winner}, guild_id={guild_id}, player_count={len(game_state.get('players', {}))}")
        
        # Phương pháp đơn giản hóa: lập danh sách người chơi và điểm để cập nhật trực tiếp
        direct_updates = []
        
        # Chuẩn bị dữ liệu cập nhật cho mỗi người chơi 
        for user_id_raw, data in game_state["players"].items():
            # Đảm bảo user_id luôn là int
            user_id = int(user_id_raw)
            role = data.get("role", "Unknown")
            player_name = "Unknown Player"
            
            # Tìm tên người chơi từ member_cache
            if game_state.get("member_cache"):
                if user_id in game_state["member_cache"]:
                    member = game_state["member_cache"][user_id]
                    player_name = getattr(member, "display_name", "Unknown Player")
                elif str(user_id) in game_state["member_cache"]:
                    member = game_state["member_cache"][str(user_id)]
                    player_name = getattr(member, "display_name", "Unknown Player")
                    
            # Xác định người chơi thuộc phe nào và có thắng hay không  
            is_winner = False
            
            if winner == "werewolves":
                # Nếu Illusionist thuộc phía sói hay dân là tùy thuộc vào cách code của bạn
                if role in ["Werewolf", "Wolfman", "Demon Werewolf", "Assassin Werewolf", "Illusionist"]:
                    is_winner = True
            elif winner == "villagers":
                if role not in ["Werewolf", "Wolfman", "Demon Werewolf", "Assassin Werewolf"]:
                    is_winner = True
                    
            # Ghi log và thêm vào danh sách cập nhật
            logger.debug(f"Người chơi: {player_name} ({user_id}), vai trò: {role}, thắng: {is_winner}")
            
            # Thêm vào danh sách cập nhật trực tiếp
            direct_updates.append({
                "user_id": user_id,
                "player_name": player_name, 
                "points": 3 if is_winner else 1,
                "win": 1 if is_winner else 0,
                "role": role
            })
                
        # Thực hiện cập nhật database - dùng phương pháp trực tiếp
        if direct_updates:
            # Dùng mô hình worker pool để làm việc với nhiều người chơi cùng lúc
            update_tasks = []
            for player_data in direct_updates:
                update_tasks.append(direct_update_leaderboard(
                    guild_id,
                    player_data["user_id"],
                    player_data["player_name"],
                    player_data["points"],
                    player_data["win"],
                    player_data["role"]
                ))
            
            if update_tasks:
                results = await asyncio.gather(*update_tasks, return_exceptions=True)
                success_count = sum(1 for r in results if r is True)
                error_count = sum(1 for r in results if isinstance(r, Exception))
                
                logger.info(f"Kết quả cập nhật leaderboard: {success_count} thành công, {error_count} lỗi")
        
        # Lưu log kết quả game
        try:
            # Tính số lượng sói và dân
            werewolf_count = sum(1 for _, d in game_state["players"].items() 
                              if d.get("role") in ["Werewolf", "Wolfman", "Demon Werewolf", "Assassin Werewolf", "Illusionist"])
            villager_count = len(game_state["players"]) - werewolf_count
            
            # Chuẩn bị dữ liệu người chơi để lưu vào logs
            players_data = {}
            for user_id_raw, data in game_state["players"].items():
                user_id = int(user_id_raw)
                user_id_str = str(user_id)
                player_name = "Unknown Player"
                
                # Tìm tên người chơi
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
                
            # Tạo nội dung log
            log_message = f"Game kết thúc. Kết quả: {winner.capitalize()} thắng!"
            
            # Lưu log game
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
    
    except Exception as e:
        logger.error(f"Lỗi tổng thể khi cập nhật thống kê người chơi: {str(e)}")
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
