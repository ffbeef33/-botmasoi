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
                return await asyncio.wait_for(result, timeout=5)
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
        # Sửa lại cách thu thập members để phù hợp với phiên bản Discord.py mới
        members_list = []
        async for member in guild.fetch_members(limit=None):
            members_list.append(member)
        
        logger.info(f"Fetched {len(members_list)} members from guild {guild.id}")
        
        # Tạo member cache dictionary
        member_cache = {member.id: member for member in members_list}
        
        # Trả về member cache, không gán vào game_state
        return member_cache
        
    except Exception as e:
        logger.error(f"Lỗi không xác định khi cập nhật member cache: {str(e)}")
        traceback.print_exc()
        
        # Fallback: Sử dụng guild.members nếu có
        if hasattr(guild, 'members') and guild.members:
            logger.warning(f"Fallback to guild.members with {len(guild.members)} members")
            return {member.id: member for member in guild.members}
        return {}

async def play_audio(file_path, voice_connection):
    """
    Phát âm thanh trong kênh voice
    
    Args:
        file_path (str): Đường dẫn đến file âm thanh
        voice_connection (discord.VoiceClient): Kết nối voice
    """
    if voice_connection and voice_connection.is_connected():
        try:
            # Ngừng phát âm thanh nếu đang phát
            if voice_connection.is_playing():
                voice_connection.stop()
                
            audio_source = discord.FFmpegPCMAudio(file_path)
            voice_connection.play(audio_source)
            # Không chờ âm thanh phát xong để tiếp tục xử lý
            return True
        except FileNotFoundError:
            logger.error(f"Không tìm thấy file âm thanh: {file_path}")
        except Exception as e:
            logger.error(f"Lỗi khi phát âm thanh {file_path}: {str(e)}")
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