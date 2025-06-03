# phases/game_setup.py
# Module quản lý việc khởi tạo game

import discord
import logging
import asyncio
import random
import traceback
from typing import Dict, List, Optional

from constants import ROLE_ICONS, BOT_VERSION
from utils.api_utils import retry_api_call, play_audio
from utils.role_utils import assign_random_roles
from phases.morning import morning_phase

logger = logging.getLogger(__name__)

async def setup_wolf_channel(guild: discord.Guild, game_state):
    """
    Tạo kênh wolf-chat cho phe sói
    
    Args:
        guild (discord.Guild): Guild để tạo kênh
        game_state: Trạng thái game
    
    Returns:
        discord.TextChannel: Kênh wolf-chat đã tạo
    """
    try:
        # Tạo Overwrites để chỉ bot và sói có thể thấy kênh
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        if guild.system_channel and guild.system_channel.category:
            wolf_channel = await guild.create_text_channel(
                "wolf-chat",
                overwrites=overwrites,
                category=guild.system_channel.category
            )
        else:
            wolf_channel = await guild.create_text_channel(
                "wolf-chat",
                overwrites=overwrites
            )
            
        logger.info(f"Created wolf-chat channel: ID={wolf_channel.id}")
        
        # Kiểm tra quyền gửi tin nhắn của bot
        perm_check = wolf_channel.permissions_for(guild.me)
        if not perm_check.send_messages:
            logger.warning(f"Bot doesn't have send_messages permission in wolf-chat: ID={wolf_channel.id}")
            await wolf_channel.set_permissions(guild.me, send_messages=True)
            
        embed = discord.Embed(
            title="🐺 Kênh Chat Của Phe Sói",
            description=(
                "Đây là kênh riêng của phe Sói để thảo luận trong pha đêm.\n"
                "• Chỉ các thành viên phe Sói và Nhà Ảo Thuật (Illusionist) mới biết kênh này.\n"
                "• Sói thường chọn một mục tiêu chung để giết mỗi đêm.\n"
                "• Hãy thảo luận và đồng nhất đối tượng để tăng hiệu quả cho phe Sói!"
            ),
            color=discord.Color.dark_red()
        )
        await wolf_channel.send(embed=embed)
        return wolf_channel
        
    except discord.errors.Forbidden:
        logger.error(f"Bot doesn't have permission to create wolf-chat in guild ID={guild.id}")
        raise
    except Exception as e:
        logger.error(f"Error creating wolf-chat: {str(e)}")
        raise

async def setup_dead_channel(guild: discord.Guild, game_state):
    """
    Tạo kênh dead-chat cho người chết
    
    Args:
        guild (discord.Guild): Guild để tạo kênh
        game_state: Trạng thái game
    
    Returns:
        discord.TextChannel: Kênh dead-chat đã tạo
    """
    try:
        # Tạo Overwrites để chỉ bot và người chết có thể thấy kênh
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        if game_state["dead_role_id"]:
            dead_role = guild.get_role(game_state["dead_role_id"])
            if dead_role:
                overwrites[dead_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        if guild.system_channel and guild.system_channel.category:
            dead_channel = await guild.create_text_channel(
                "dead-chat",
                overwrites=overwrites,
                category=guild.system_channel.category
            )
        else:
            dead_channel = await guild.create_text_channel(
                "dead-chat",
                overwrites=overwrites
            )
            
        logger.info(f"Created dead-chat channel: ID={dead_channel.id}")
        
        # Kiểm tra quyền gửi tin nhắn của bot
        perm_check = dead_channel.permissions_for(guild.me)
        if not perm_check.send_messages:
            logger.warning(f"Bot doesn't have send_messages permission in dead-chat: ID={dead_channel.id}")
            await dead_channel.set_permissions(guild.me, send_messages=True)
            
        embed = discord.Embed(
            title="💀 Kênh Chat Của Người Chết",
            description=(
                "Đây là kênh riêng của người chơi đã chết.\n"
                "• Người chết không được tiết lộ thông tin về game cho người chơi khác.\n"
                "• Người chết không thể tham gia thảo luận và bỏ phiếu trong kênh chính.\n"
                "• Bạn vẫn có thể theo dõi cuộc chơi và trò chuyện với người chơi khác đã chết ở đây."
            ),
            color=discord.Color.dark_grey()
        )
        await dead_channel.send(embed=embed)
        return dead_channel
        
    except discord.errors.Forbidden:
        logger.error(f"Bot doesn't have permission to create dead-chat in guild ID={guild.id}")
        raise
    except Exception as e:
        logger.error(f"Error creating dead-chat: {str(e)}")
        raise

async def start_game_logic(interaction: discord.Interaction, game_state):
    """
    Xử lý logic khởi động game mới
    
    Args:
        interaction (discord.Interaction): Interaction để phản hồi
        game_state: Trạng thái game hiện tại
    """
    try:
        # Kiểm tra interaction có còn hợp lệ không
        text_channel = interaction.channel
        if not text_channel:
            # Nếu không có channel trong interaction, lấy từ game_state
            text_channel = game_state.get("text_channel")
            if not text_channel:
                logger.error("Không thể tìm thấy text channel để gửi thông báo")
                return
        
        # Gửi thông báo đang khởi tạo game
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
                await asyncio.sleep(0.5)  # Đợi để đảm bảo defer được xử lý
                await interaction.followup.send("Game đang được khởi tạo...", ephemeral=True)
            else:
                # Nếu interaction đã được phản hồi, gửi tin nhắn vào channel
                await text_channel.send("Game đang được khởi tạo...")
        except Exception as e:
            logger.warning(f"Không thể phản hồi interaction: {str(e)}")
            await text_channel.send("Game đang được khởi tạo...")

        # Lấy các kênh và guild
        guild = interaction.guild
        if not guild:
            logger.error(f"Guild không tìm thấy trong interaction, ID={interaction.guild_id}")
            await text_channel.send("Lỗi: Không tìm thấy guild.")
            return
            
        voice_channel = await retry_api_call(lambda: interaction.client.get_channel(game_state["voice_channel_id"]))
        if not voice_channel:
            await text_channel.send("Lỗi: Không tìm thấy kênh voice.")
            return
    
        try:
            # Kiểm tra và ngắt kết nối nếu bot đã ở trong kênh voice
            if game_state.get("voice_connection") and game_state["voice_connection"].is_connected():
                await game_state["voice_connection"].disconnect()
                logger.info(f"Bot đã ngắt kết nối khỏi kênh voice cũ: ID={game_state.get('voice_channel_id')}")
    
            # Tham gia kênh voice mới
            try:
                game_state["voice_connection"] = await voice_channel.connect()
                logger.info(f"Bot đã tham gia kênh voice: ID={voice_channel.id}, Name={voice_channel.name}")
            except Exception as e:
                logger.error(f"Không thể tham gia kênh voice ID={voice_channel.id}: {str(e)}")
                await text_channel.send(f"Lỗi: Không thể tham gia kênh voice {voice_channel.name}.")
                return
    
            # Tạo vai trò Discord
            villager_role = await guild.create_role(
                name="Villager", 
                color=discord.Color.green(), 
                hoist=True, 
                mentionable=False,
                reason="DeWolfVie game role"
            )
            game_state["villager_role_id"] = villager_role.id
            
            dead_role = await guild.create_role(
                name="Dead", 
                color=discord.Color.greyple(), 
                hoist=True, 
                mentionable=False,
                reason="DeWolfVie game role"
            )
            game_state["dead_role_id"] = dead_role.id
            
            werewolf_role = await guild.create_role(
                name="Werewolf", 
                color=discord.Color.red(), 
                hoist=False, 
                mentionable=False,
                reason="DeWolfVie game role"
            )
            game_state["werewolf_role_id"] = werewolf_role.id
    
            # Đảm bảo người chết không nói được trong kênh voice
            await voice_channel.set_permissions(dead_role, speak=False)
    
            # Thiết lập channel permissions
            await text_channel.set_permissions(guild.default_role, send_messages=False)
            await text_channel.set_permissions(villager_role, send_messages=True)
            await text_channel.set_permissions(dead_role, send_messages=False)
            
            # Tạo kênh wolf-chat và dead-chat
            wolf_channel = await setup_wolf_channel(guild, game_state)
            dead_channel = await setup_dead_channel(guild, game_state)
            
            # Tạo các kênh voice riêng biệt cho từng người chơi
            game_state["player_channels"] = {}
            player_channel_tasks = []
            
            for user_id in game_state["temp_players"]:
                member = game_state["member_cache"].get(user_id)
                if not member:
                    member = game_state["member_cache"].get(str(user_id))  # Thử với dạng string
                    if not member:
                        logger.warning(f"Member not found in cache: ID={user_id}")
                        continue
                    
                max_name_length = 100 - len("House of ") - 1  # Đảm bảo tên không vượt quá 100 ký tự
                channel_name = f"House of {member.display_name[:max_name_length]}"
                
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False),
                    member: discord.PermissionOverwrite(read_messages=True, connect=True),
                    guild.me: discord.PermissionOverwrite(read_messages=True, connect=True)
                }
                
                # Create Task để tạo channel bất đồng bộ
                player_channel_tasks.append(create_player_channel(guild, channel_name, overwrites, user_id, game_state))
                
            # Thực hiện tất cả các tasks tạo channel cùng lúc
            await asyncio.gather(*player_channel_tasks)
            
            # Khởi tạo game state
            game_state["wolf_channel"] = wolf_channel
            game_state["dead_channel"] = dead_channel
            game_state["voice_channel_id"] = voice_channel.id
            game_state["guild_id"] = guild.id
            game_state["text_channel"] = text_channel
            game_state["is_game_running"] = True
            game_state["is_game_paused"] = False
            game_state["witch_has_power"] = game_state["temp_roles"]["Witch"] > 0
            game_state["hunter_has_power"] = game_state["temp_roles"]["Hunter"] > 0
            game_state["is_first_day"] = True
            game_state["phase"] = "none"
            game_state["night_count"] = 0
            game_state["demon_werewolf_activated"] = False
            game_state["demon_werewolf_cursed_player"] = None
            game_state["demon_werewolf_has_cursed"] = False
            game_state["demon_werewolf_cursed_this_night"] = False
            
            # Phân vai cho người chơi và gửi tin nhắn
            await assign_random_roles(game_state, guild)
            
            # Thông báo game bắt đầu
            role_list_str = ", ".join([f"{role}: {count}" for role, count in game_state["temp_roles"].items() if count > 0])
            
            start_embed = discord.Embed(
                title="🎮 **Game Ma Sói DeWolfVie Bắt Đầu!**",
                description=(
                    f"**🔹 Số lượng người chơi: {len(game_state['players'])}**\n"
                    f"**🔹 Các vai trò trong game: {role_list_str}**\n"
                    "**🔹 Tất cả người chơi đã được gán vai trò.**\n"
                    "**🔹 Kênh wolf-chat và dead-chat đã được thiết lập.**\n"
                    "**🔹 Hãy kiểm tra tin nhắn DM để biết vai trò của bạn.**\n"
                    "**🔹 Hãy kiểm tra tin nhắn DM để biết vai trò của bạn.**\n"
                    "**🔹 Chuẩn bị cho pha ngày đầu tiên!**"
                ),
                color=discord.Color.blue()
            )
            start_embed.set_image(url="https://cdn.discordapp.com/attachments/1365707789321633813/1377490486498951241/Banner_early_acccess_Recovered.png?ex=6839277c&is=6837d5fc&hm=f3451388485840264aa9207a07f9a1579a1cc9038baa46e0b3aaeecb1998279f&")  # Thêm URL của ảnh banner
            start_embed.set_footer(text=BOT_VERSION)
            await game_state["text_channel"].send(embed=start_embed)
            
            # Bắt đầu pha sáng đầu tiên
            await morning_phase(interaction, game_state)
            
        except Exception as e:
            logger.error(f"Error in start_game_logic: {str(e)}")
            traceback.print_exc()
            await text_channel.send(f"Có lỗi xảy ra khi khởi tạo game: {str(e)[:1000]}")
    except Exception as e:
        logger.error(f"Fatal error in start_game_logic: {str(e)}")
        traceback.print_exc()
        
        # Cố gắng gửi thông báo lỗi bằng mọi cách
        try:
            if hasattr(interaction, 'channel') and interaction.channel:
                await interaction.channel.send(f"Lỗi nghiêm trọng khi khởi tạo game: {str(e)[:1000]}")
            elif game_state.get("text_channel"):
                await game_state["text_channel"].send(f"Lỗi nghiêm trọng khi khởi tạo game: {str(e)[:1000]}")
        except:
            logger.critical("Không thể gửi thông báo lỗi qua bất kỳ kênh nào")

async def create_player_channel(guild, channel_name, overwrites, user_id, game_state):
    """
    Tạo kênh voice riêng cho người chơi
    
    Args:
        guild (discord.Guild): Guild để tạo kênh
        channel_name (str): Tên kênh
        overwrites (dict): Permissions overwrites
        user_id (int): ID của người chơi
        game_state (dict): Trạng thái game
    """
    try:
        channel = await guild.create_voice_channel(channel_name, overwrites=overwrites)
        game_state["player_channels"][user_id] = channel
        logger.info(f"Created private voice channel for player: {channel_name}, ID={channel.id}")
        return channel
    except Exception as e:
        logger.error(f"Failed to create player channel {channel_name}: {str(e)}")
        return None

async def start_new_game_with_same_setup(interaction: discord.Interaction, game_state):
    """
    Bắt đầu game mới với cùng người chơi và vai trò
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game
    """
    try:
        # Lấy thông tin từ game_state
        temp_players = game_state.get("temp_players", []) 
        temp_roles = game_state.get("temp_roles", {})
        temp_admin_id = game_state.get("temp_admin_id", interaction.user.id)
        
        # Xác định text_channel
        text_channel = interaction.channel
        if not text_channel and "text_channel" in game_state:
            text_channel = game_state["text_channel"]
            
        if not text_channel:
            logger.error("Không tìm thấy text_channel trong interaction hoặc game_state")
            return
        
        if not temp_players or not temp_roles:
            await text_channel.send("Lỗi: Không có thông tin người chơi hoặc vai trò để khởi động lại game!")
            logger.error("Missing temp_players or temp_roles in game_state")
            return
            
        # Lấy thông tin voice_channel
        guild = interaction.guild
        voice_channel_id = game_state.get("voice_channel_id")
        
        if not guild:
            await text_channel.send("Lỗi: Không tìm thấy guild!")
            logger.error("Guild not found in interaction")
            return
            
        if not voice_channel_id:
            await text_channel.send("Lỗi: Không tìm thấy ID kênh voice trong game_state!")
            logger.error("voice_channel_id not found in game_state")
            return
            
        voice_channel = interaction.client.get_channel(voice_channel_id)
        if not voice_channel:
            await text_channel.send(f"Lỗi: Không tìm thấy kênh voice với ID {voice_channel_id}!")
            logger.error(f"Voice channel with ID {voice_channel_id} not found")
            return
        
        # Reset game state và lưu lại những thông tin cần thiết
        game_state.reset()
        
        # Gán lại các thông tin quan trọng
        game_state["temp_players"] = temp_players
        game_state["temp_roles"] = temp_roles
        game_state["temp_admin_id"] = temp_admin_id
        game_state["text_channel"] = text_channel
        game_state["voice_channel_id"] = voice_channel_id
        
        # Làm mới member_cache
        try:
            # Sử dụng hàm update_member_cache đã sửa
            from utils.api_utils import update_member_cache
            game_state["member_cache"] = await update_member_cache(guild, game_state)
        except Exception as e:
            logger.error(f"Failed to refresh member_cache: {str(e)}")
            # Tạo cache mới nếu cần
            game_state["member_cache"] = {}
            # Thử lấy member từ guild cho mỗi player
            for player_id in temp_players:
                try:
                    member = await guild.fetch_member(player_id)
                    if member:
                        game_state["member_cache"][player_id] = member
                except:
                    logger.warning(f"Could not fetch member for ID {player_id}")
    
        # Kiểm tra trạng thái voice của người chơi
        current_members = {m.id for m in voice_channel.members if not m.bot}
        missing_players = [uid for uid in game_state["temp_players"] if uid not in current_members]
        if missing_players:
            missing_names = []
            for uid in missing_players:
                if uid in game_state["member_cache"]:
                    missing_names.append(game_state["member_cache"][uid].display_name)
                elif str(uid) in game_state["member_cache"]:
                    missing_names.append(game_state["member_cache"][str(uid)].display_name)
                else:
                    missing_names.append(f"ID:{uid}")
                
            await text_channel.send(f"Các người chơi sau không còn trong kênh voice: {', '.join(missing_names)}")
            
            # Tùy chọn tiếp tục hoặc hủy
            view = ContinueWithMissingPlayersView(interaction, game_state, missing_players)
            await text_channel.send("Bạn muốn tiếp tục game mà không có những người chơi này?", view=view)
            return
        
        # Nếu tất cả người chơi có mặt, tiếp tục khởi động game mới
        try:
            # Bot tham gia lại kênh voice
            if game_state.get("voice_connection") and game_state["voice_connection"].is_connected():
                await game_state["voice_connection"].disconnect()
            
            game_state["voice_connection"] = await voice_channel.connect()
            logger.info(f"Bot joined voice channel: ID={voice_channel.id}, Name={voice_channel.name}")
        except Exception as e:
            logger.error(f"Failed to join voice channel ID={voice_channel.id}: {str(e)}")
            await text_channel.send(f"Lỗi: Không thể tham gia kênh voice {voice_channel.name}.")
            return
        
        # Khởi động game mới
        await start_game_logic(interaction, game_state)
    except Exception as e:
        logger.error(f"Error in start_new_game_with_same_setup: {str(e)}")
        traceback.print_exc()
        
        try:
            # Thử gửi thông báo lỗi qua kênh nếu có thể
            if hasattr(interaction, 'channel') and interaction.channel:
                await interaction.channel.send(f"Lỗi khi khởi tạo game mới: {str(e)[:1000]}")
            elif game_state.get("text_channel"):
                await game_state["text_channel"].send(f"Lỗi khi khởi tạo game mới: {str(e)[:1000]}")
        except:
            logger.critical("Không thể gửi thông báo lỗi")

class ContinueWithMissingPlayersView(discord.ui.View):
    """View để quyết định có tiếp tục game không khi thiếu người chơi"""
    def __init__(self, interaction, game_state, missing_players):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.game_state = game_state
        self.missing_players = missing_players

    @discord.ui.button(label="Tiếp tục không có họ", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id != self.game_state["temp_admin_id"]:
                await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
                return
                
            # Xóa người chơi vắng mặt khỏi danh sách
            self.game_state["temp_players"] = [p for p in self.game_state["temp_players"] if p not in self.missing_players]
            
            # Đếm số vai trò cần thiết cho game mới
            roles_needed = len(self.game_state["temp_players"])
            total_roles = sum(self.game_state["temp_roles"].values())
            
            if total_roles > roles_needed:
                # Cần giảm số lượng vai trò nếu có ít người chơi hơn
                await interaction.response.edit_message(content="Số người chơi ít hơn số vai trò. Vui lòng thiết lập lại vai trò!", view=None)
                
                # Xử lý loại bỏ vai trò dư thừa theo mức độ ưu tiên
                from views.setup_views import RoleSelectView
                new_view = RoleSelectView(self.game_state["temp_admin_id"], self.game_state)
                await interaction.channel.send(f"Thiết lập lại vai trò cho {roles_needed} người chơi:", view=new_view)
            else:
                await interaction.response.edit_message(content="Tiếp tục game với số người chơi có mặt...", view=None)
                # Sử dụng interaction hiện tại, không phải interaction cũ
                await start_game_logic(interaction, self.game_state)
        except Exception as e:
            logger.error(f"Error in continue_button: {str(e)}")
            await interaction.channel.send(f"Lỗi khi tiếp tục game: {str(e)}")

    @discord.ui.button(label="Hủy game", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id != self.game_state["temp_admin_id"]:
                await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
                return
                
            await interaction.response.edit_message(content="Game đã bị hủy. Sử dụng /start_game để bắt đầu game mới.", view=None)
            
            # Reset game state triệt để hơn
            self.game_state.reset()
            self.game_state["temp_players"] = []
            self.game_state["temp_roles"] = {}
        except Exception as e:
            logger.error(f"Error in cancel_button: {str(e)}")
            await interaction.channel.send(f"Lỗi khi hủy game: {str(e)}")