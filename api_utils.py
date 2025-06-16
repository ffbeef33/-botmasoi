# utils/api_utils.py
# Các utility cho API và Discord

import discord
import asyncio
import inspect
import logging
import traceback
import random
from typing import Callable, Any, Dict, List, Optional, Union

from config import API_MAX_RETRIES, API_RETRY_DELAY

logger = logging.getLogger(__name__)

async def retry_api_call(func, max_attempts=API_MAX_RETRIES, initial_delay=API_RETRY_DELAY):
    """
    Thực hiện một API call với cơ chế retry
    
    Args:
        func (callable): Hàm cần thực hiện
        max_attempts (int): Số lần thử tối đa
        initial_delay (int): Thời gian chờ giữa các lần thử
    
    Returns:
        Any: Kết quả của hàm
    """
    attempt = 1
    delay = initial_delay
    func_name = getattr(func, "__name__", str(func))
    
    while attempt <= max_attempts:
        try:
            result = func()
            if inspect.iscoroutine(result):
                return await asyncio.wait_for(result, timeout=10)  # Tăng timeout lên 10s cho các thao tác fetch
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"API call timed out, attempt={attempt}/{max_attempts}, func={func_name}")
            if attempt == max_attempts:
                raise discord.errors.HTTPException(response=None, message="API call timed out")
                
            await asyncio.sleep(delay)
            attempt += 1
            delay *= 2
            
        except discord.errors.HTTPException as e:
            if e.status == 429:  # Rate limit
                logger.warning(f"Discord rate limit hit, attempt={attempt}/{max_attempts}, retrying in {delay}s")
                await asyncio.sleep(delay)
                attempt += 1
                delay *= 2
            else:
                logger.error(f"Discord HTTP error in API call: {str(e)}, attempt={attempt}, func={func_name}")
                raise e
                
        except Exception as e:
            logger.error(f"API call failed: {str(e)}, attempt={attempt}, func={func_name}")
            traceback.print_exc()
            
            if attempt == max_attempts:
                raise e
                
            await asyncio.sleep(delay)
            attempt += 1
            delay *= 2
            
    raise discord.errors.HTTPException(response=None, message="Max retries exceeded for API call")

async def safe_send_message(channel, content=None, *, embed=None, view=None, ephemeral=False, **kwargs):
    """
    Gửi tin nhắn an toàn với xử lý lỗi
    
    Args:
        channel (discord.abc.Messageable): Kênh để gửi tin nhắn
        content (str, optional): Nội dung tin nhắn
        embed (discord.Embed, optional): Embed để gửi
        view (discord.ui.View, optional): View để đính kèm
        ephemeral (bool): Chỉ người gọi lệnh nhìn thấy (chỉ hoạt động với interaction.response)
        **kwargs: Các thông số khác cho send
    
    Returns:
        discord.Message: Tin nhắn đã gửi hoặc None nếu có lỗi
    """
    try:
        if isinstance(channel, discord.Interaction):
            if channel.response.is_done():
                return await channel.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral, **kwargs)
            else:
                await channel.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral, **kwargs)
                return await channel.original_response()
        else:
            return await channel.send(content=content, embed=embed, view=view, **kwargs)
    except discord.errors.Forbidden:
        logger.error(f"Không có quyền gửi tin nhắn đến {channel}")
    except discord.errors.HTTPException as e:
        logger.error(f"Lỗi HTTP khi gửi tin nhắn: {str(e)}")
    except Exception as e:
        logger.error(f"Lỗi không xác định khi gửi tin nhắn: {str(e)}")
        traceback.print_exc()
    
    return None

async def safe_edit_message(message, content=None, *, embed=None, view=None, **kwargs):
    """
    Chỉnh sửa tin nhắn an toàn với xử lý lỗi
    
    Args:
        message (discord.Message): Tin nhắn để chỉnh sửa
        content (str, optional): Nội dung mới
        embed (discord.Embed, optional): Embed mới
        view (discord.ui.View, optional): View mới
        **kwargs: Các thông số khác cho edit
    
    Returns:
        discord.Message: Tin nhắn đã chỉnh sửa hoặc None nếu có lỗi
    """
    try:
        return await message.edit(content=content, embed=embed, view=view, **kwargs)
    except discord.errors.NotFound:
        logger.warning(f"Không tìm thấy tin nhắn để chỉnh sửa ID={message.id}")
    except discord.errors.Forbidden:
        logger.error(f"Không có quyền chỉnh sửa tin nhắn ID={message.id}")
    except discord.errors.HTTPException as e:
        logger.error(f"Lỗi HTTP khi chỉnh sửa tin nhắn: {str(e)}")
    except Exception as e:
        logger.error(f"Lỗi không xác định khi chỉnh sửa tin nhắn: {str(e)}")
        traceback.print_exc()
    
    return None

async def update_member_cache(guild, game_state):
    """
    Cập nhật cache các thành viên trong guild
    
    Args:
        guild (discord.Guild): Guild cần cập nhật cache
        game_state (dict/GameState): Trạng thái game hiện tại
        
    Returns:
        dict: Dictionary chứa các thành viên dưới dạng {member_id: member}
    """
    try:
        # Phương pháp 1: Sử dụng guild.members nếu đã được chunk
        if guild.chunked:
            logger.info(f"Sử dụng guild.members đã được cache ({len(guild.members)} thành viên)")
            return {member.id: member for member in guild.members}
        
        # Phương pháp 2: Chunk guild để lấy tất cả members
        try:
            logger.info(f"Chunk guild {guild.id} để lấy tất cả thành viên")
            await guild.chunk(cache=True)
            logger.info(f"Chunk thành công, thu được {len(guild.members)} thành viên")
            return {member.id: member for member in guild.members}
        except Exception as chunk_error:
            logger.warning(f"Lỗi khi chunk guild: {str(chunk_error)}")
        
        # Phương pháp 3: Sử dụng fetch_members theo chặng
        logger.info(f"Fetch members từ guild {guild.id}")
        members_dict = {}
        
        # Fetch members với timeout riêng và xử lý theo chặng
        async with asyncio.timeout(30):  # Timeout dài hơn cho toàn bộ quá trình
            async for member in guild.fetch_members(limit=None):
                members_dict[member.id] = member
                # Log tiến trình theo từng 100 members
                if len(members_dict) % 100 == 0:
                    logger.debug(f"Đã fetch được {len(members_dict)} thành viên...")
        
        logger.info(f"Đã fetch thành công {len(members_dict)} thành viên từ guild {guild.id}")
        return members_dict
        
    except asyncio.TimeoutError:
        logger.error(f"Timeout khi fetch members từ guild {guild.id}")
    except Exception as e:
        logger.error(f"Lỗi không xác định khi cập nhật member cache: {str(e)}")
        traceback.print_exc()
    
    # Fallback: Sử dụng guild.members nếu có hoặc trả về cache hiện có
    logger.warning(f"Sử dụng guild.members làm fallback")
    if hasattr(guild, 'members') and guild.members:
        return {member.id: member for member in guild.members}
    elif hasattr(game_state, "member_cache") and game_state.member_cache:
        return game_state.member_cache
    elif isinstance(game_state, dict) and game_state.get("member_cache"):
        return game_state["member_cache"]
    
    logger.error("Không thể lấy dữ liệu members, trả về dict rỗng")
    return {}

async def get_all_members(guild):
    """
    Lấy tất cả thành viên từ guild một cách an toàn
    
    Args:
        guild (discord.Guild): Guild cần lấy thành viên
        
    Returns:
        list: Danh sách các thành viên
    """
    try:
        # Nếu members đã được cache bởi Discord.py
        if guild.chunked:
            return list(guild.members)
        
        # Thử chunk guild
        try:
            await guild.chunk(cache=True)
            return list(guild.members)
        except:
            pass
            
        # Nếu không thành công, fetch thủ công
        members = []
        async with asyncio.timeout(30):
            async for member in guild.fetch_members(limit=None):
                members.append(member)
        
        return members
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thành viên: {str(e)}")
        # Trả về danh sách hiện có (có thể không đầy đủ)
        return list(guild.members)

async def play_audio(file_path, voice_connection):
    """
    Phát âm thanh trong kênh voice với xử lý lỗi tốt hơn
    
    Args:
        file_path (str): Đường dẫn đến file âm thanh
        voice_connection (discord.VoiceClient): Kết nối voice
        
    Returns:
        bool: True nếu thành công, False nếu thất bại
    """
    if not voice_connection:
        logger.error("Voice connection is None, cannot play audio")
        return False
        
    try:
        # Kiểm tra kết nối còn nguyên vẹn không
        if not voice_connection.is_connected():
            logger.warning("Voice connection is not connected, cannot play audio")
            # Thử lấy tham chiếu đến VoiceManager để kết nối lại
            try:
                from main import voice_manager
                if voice_manager and voice_connection.channel:
                    guild_id = voice_connection.channel.guild.id
                    await voice_manager._attempt_reconnect(guild_id)
                    # Cập nhật lại voice_connection với phiên bản mới
                    if guild_id in voice_manager.voice_connections:
                        voice_connection = voice_manager.voice_connections[guild_id]
                    else:
                        return False
            except ImportError:
                logger.warning("Cannot import voice_manager, reconnection not attempted")
                return False
                
        # Ngừng phát âm thanh nếu đang phát
        if voice_connection.is_playing():
            voice_connection.stop()
            
        # Thêm xử lý lỗi cụ thể hơn
        audio_source = discord.FFmpegPCMAudio(file_path)
        voice_connection.play(
            audio_source,
            after=lambda error: logger.error(f"Audio playback error: {error}") if error else None
        )
        return True
        
    except FileNotFoundError:
        logger.error(f"Audio file not found: {file_path}")
    except discord.errors.ClientException as e:
        logger.error(f"Discord client error when playing audio: {e}")
    except Exception as e:
        logger.error(f"General error playing audio {file_path}: {e}")
        traceback.print_exc()
    
    return False

async def generate_math_problem(used_problems):
    """
    Tạo bài toán cộng/trừ cho người chơi phải giải quyết
    
    Args:
        used_problems (set): Tập hợp các bài toán đã được sử dụng
    
    Returns:
        dict: Bài toán với dạng {"problem": "123 + 456", "answer": 579, "options": [579, 589, 569]}
    """
    for _ in range(20):  # Giảm số lần thử từ 100 xuống 20 để tối ưu
        num1 = random.randint(100, 999)
        num2 = random.randint(100, 999)
        operation = random.choice(['+', '-'])
        problem = f"{num1} {operation} {num2}"
        
        if problem in used_problems:
            continue
            
        answer = num1 + num2 if operation == '+' else num1 - num2
        if answer < 100:
            continue
            
        # Tạo các phương án sai gần với đáp án đúng
        wrong_options = [answer + offset for offset in [-100, -50, -10, 10, 50, 100] 
                         if answer + offset != answer and answer + offset >= 0]
        
        if len(wrong_options) < 2:
            continue
            
        wrong1, wrong2 = random.sample(wrong_options, 2)
        options = [answer, wrong1, wrong2]
        random.shuffle(options)
        
        return {"problem": problem, "answer": answer, "options": options}
    
    # Nếu không thể tạo bài toán duy nhất sau nhiều lần thử
    # Trả về một bài toán mặc định
    default_answer = 150
    return {
        "problem": "100 + 50", 
        "answer": default_answer, 
        "options": [default_answer, default_answer + 10, default_answer - 10]
    }

async def countdown(channel, seconds, phase, game_state):
    """
    Hiển thị đếm ngược cho một pha game
    
    Args:
        channel (discord.TextChannel): Kênh để hiển thị đếm ngược
        seconds (int): Số giây cần đếm ngược
        phase (str): Tên của pha đang đếm ngược
        game_state (GameState): Trạng thái game hiện tại
    """
    if not game_state.is_game_running or game_state.is_game_paused:
        logger.info(f"Game không hoạt động hoặc tạm dừng, bỏ qua đếm ngược cho {phase}")
        return

    if channel is None:
        logger.error(f"Không thể gửi tin nhắn đếm ngược cho {phase}: channel is None")
        return

    try:
        # Gửi tin nhắn ban đầu
        current_message = await channel.send(f"⏳ *Đang đếm ngược cho {phase}... ({seconds}s)*")
        
        # Cập nhật mỗi 5 giây để giảm số lượng API calls
        update_interval = 5
        for remaining in range(seconds - 1, 0, -update_interval):
            if not game_state.is_game_running or game_state.is_game_paused:
                await current_message.edit(content="⏳ *Đếm ngược bị hủy do game dừng hoặc tạm dừng.*")
                return
                
            await asyncio.sleep(min(update_interval, remaining))
            
            # Chỉ cập nhật tin nhắn nếu còn trên 10 giây
            if remaining > 10:
                await current_message.edit(content=f"⏳ *Đang đếm ngược cho {phase}... ({remaining}s)*")
        
        # Đếm ngược 5 giây cuối
        for i in range(5, 0, -1):
            if not game_state.is_game_running or game_state.is_game_paused:
                await current_message.edit(content="⏳ *Đếm ngược bị hủy do game dừng hoặc tạm dừng.*")
                return
                
            await current_message.edit(content=f"⏳ *Còn {i}s để {phase}*")
            await asyncio.sleep(1)
            
        await current_message.edit(content=f"⏳ *Pha {phase} kết thúc!*")
        
    except Exception as e:
        logger.error(f"Lỗi trong quá trình đếm ngược cho {phase}: {str(e)}")
        traceback.print_exc()
