# utils/voice_manager.py
# Quản lý kết nối voice và tự động kết nối lại

import discord
import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class VoiceManager:
    """Lớp quản lý các kết nối voice của bot"""
    
    def __init__(self, bot):
        self.bot = bot
        self.voice_connections: Dict[int, discord.VoiceClient] = {}
        self.keepalive_tasks: Dict[int, asyncio.Task] = {}
        self.channel_ids: Dict[int, int] = {}  # Lưu channel id để kết nối lại
        self.game_states = {}  # Tham chiếu đến game_states
        
    def set_game_states_reference(self, game_states):
        """Thiết lập tham chiếu đến game_states"""
        self.game_states = game_states
        
    async def connect_to_voice(self, voice_channel, guild_id):
        """
        Kết nối đến kênh voice và thiết lập giữ kết nối
        
        Args:
            voice_channel (discord.VoiceChannel): Kênh voice cần kết nối
            guild_id (int): ID của guild
        
        Returns:
            discord.VoiceClient: Kết nối voice đã được thiết lập
        """
        try:
            # Ngắt kết nối cũ nếu có
            if guild_id in self.voice_connections and self.voice_connections[guild_id].is_connected():
                await self.voice_connections[guild_id].disconnect(force=True)
                logger.info(f"Đã ngắt kết nối voice cũ trong guild {guild_id}")
            
            # Thử kết nối
            voice_client = await voice_channel.connect(timeout=10.0, reconnect=True)
            
            # Lưu thông tin
            self.voice_connections[guild_id] = voice_client
            self.channel_ids[guild_id] = voice_channel.id
            
            # Bắt đầu task giữ kết nối
            self._start_keepalive(guild_id)
            
            logger.info(f"Kết nối thành công đến kênh voice {voice_channel.name} (ID: {voice_channel.id}) trong guild {guild_id}")
            return voice_client
            
        except Exception as e:
            logger.error(f"Lỗi khi kết nối đến kênh voice: {e}")
            return None
    
    async def disconnect(self, guild_id):
        """Ngắt kết nối voice từ guild"""
        if guild_id in self.voice_connections and self.voice_connections[guild_id].is_connected():
            # Dừng task giữ kết nối
            self._stop_keepalive(guild_id)
            
            # Ngắt kết nối
            await self.voice_connections[guild_id].disconnect()
            
            # Xóa thông tin
            del self.voice_connections[guild_id]
            if guild_id in self.channel_ids:
                del self.channel_ids[guild_id]
                
            logger.info(f"Đã ngắt kết nối voice từ guild {guild_id}")
            return True
        return False
    
    def _start_keepalive(self, guild_id):
        """Bắt đầu task giữ kết nối cho guild"""
        if guild_id in self.keepalive_tasks and not self.keepalive_tasks[guild_id].done():
            self.keepalive_tasks[guild_id].cancel()
        
        self.keepalive_tasks[guild_id] = asyncio.create_task(self._keepalive_loop(guild_id))
        logger.debug(f"Đã bắt đầu task giữ kết nối cho guild {guild_id}")
    
    def _stop_keepalive(self, guild_id):
        """Dừng task giữ kết nối cho guild"""
        if guild_id in self.keepalive_tasks and not self.keepalive_tasks[guild_id].done():
            self.keepalive_tasks[guild_id].cancel()
            logger.debug(f"Đã dừng task giữ kết nối cho guild {guild_id}")
    
    async def _keepalive_loop(self, guild_id):
        """Loop giữ kết nối voice"""
        try:
            while True:
                await asyncio.sleep(20)  # Kiểm tra mỗi 20 giây
                
                if guild_id not in self.voice_connections:
                    logger.debug(f"Guild {guild_id} không còn trong danh sách kết nối voice, dừng keepalive")
                    break
                    
                voice_client = self.voice_connections[guild_id]
                
                # Kiểm tra nếu kết nối đã bị ngắt
                if not voice_client or not voice_client.is_connected():
                    logger.warning(f"Phát hiện mất kết nối voice trong guild {guild_id}, đang thử kết nối lại")
                    await self._attempt_reconnect(guild_id)
                    
        except asyncio.CancelledError:
            logger.debug(f"Task giữ kết nối cho guild {guild_id} đã bị hủy")
        except Exception as e:
            logger.error(f"Lỗi trong task giữ kết nối cho guild {guild_id}: {e}")
    
    async def _attempt_reconnect(self, guild_id):
        """Thử kết nối lại khi mất kết nối"""
        # Kiểm tra xem có thông tin kênh không
        if guild_id not in self.channel_ids:
            logger.error(f"Không có thông tin kênh voice để kết nối lại cho guild {guild_id}")
            return False
            
        try:
            # Lấy thông tin kênh
            channel_id = self.channel_ids[guild_id]
            channel = self.bot.get_channel(channel_id)
            
            if not channel:
                logger.error(f"Không tìm thấy kênh voice {channel_id} trong guild {guild_id}")
                return False
                
            # Kết nối lại
            voice_client = await channel.connect(timeout=10.0, reconnect=True)
            self.voice_connections[guild_id] = voice_client
            
            # Cập nhật game_state nếu đang có game chạy
            if guild_id in self.game_states and self.game_states[guild_id].get("is_game_running"):
                game_state = self.game_states[guild_id]
                game_state["voice_connection"] = voice_client
                
                # Thông báo trong kênh text nếu có
                if game_state.get("text_channel"):
                    await game_state["text_channel"].send("🔄 Bot đã kết nối lại kênh voice sau khi bị ngắt kết nối!")
            
            logger.info(f"Đã kết nối lại thành công đến kênh voice {channel.name} trong guild {guild_id}")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi thử kết nối lại kênh voice trong guild {guild_id}: {e}")
            return False
            
    async def handle_voice_state_update(self, member, before, after):
        """Xử lý sự kiện thay đổi trạng thái voice"""
        # Xử lý khi bot bị ngắt kết nối
        if member.id == self.bot.user.id and before.channel and not after.channel:
            guild_id = before.channel.guild.id
            logger.warning(f"Bot bị ngắt kết nối khỏi kênh voice trong guild {guild_id}")
            
            # Kiểm tra nếu đang có game chạy
            if guild_id in self.game_states and self.game_states[guild_id].get("is_game_running"):
                logger.info(f"Đang có game chạy trong guild {guild_id}, thử kết nối lại")
                await self._attempt_reconnect(guild_id)
                
        # Xử lý khi không còn người trong kênh (ngoài bot)
        elif before.channel and member.id != self.bot.user.id:
            if before.channel.members and len([m for m in before.channel.members if not m.bot]) == 0:
                guild_id = before.channel.guild.id
                
                # Không tự động ngắt kết nối nếu đang có game chạy
                if guild_id in self.game_states and self.game_states[guild_id].get("is_game_running"):
                    logger.debug(f"Không ngắt kết nối khỏi kênh trống vì game đang chạy trong guild {guild_id}")
                    return
                    
                # Ngắt kết nối nếu không còn người trong kênh và không có game chạy
                voice_client = discord.utils.get(self.bot.voice_clients, guild=before.channel.guild)
                if voice_client and voice_client.channel == before.channel:
                    logger.info(f"Ngắt kết nối khỏi kênh trống {before.channel.name} trong guild {guild_id}")
                    await voice_client.disconnect()