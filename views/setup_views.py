# views/setup_views.py
# UI Components cho thiết lập game

import discord
import logging
from typing import List, Dict, Optional
import asyncio
import traceback

from constants import ROLES, VILLAGER_SPECIAL_ROLES, WEREWOLF_SPECIAL_ROLES
from utils.api_utils import retry_api_call

logger = logging.getLogger(__name__)

class VoiceChannelView(discord.ui.View):
    """View để chọn kênh voice cho game"""
    def __init__(self, guild, admin_id, game_states):
        super().__init__(timeout=180)
        self.add_item(VoiceChannelSelect(guild, admin_id, game_states))

class VoiceChannelSelect(discord.ui.Select):
    """Select menu để chọn kênh voice"""
    def __init__(self, guild, admin_id, game_states):
        voice_channels = [ch for ch in guild.voice_channels if ch.members]
        options = [
            discord.SelectOption(label=ch.name, value=str(ch.id))
            for ch in voice_channels[:25]  # Discord giới hạn 25 options
        ]
        super().__init__(placeholder="Chọn kênh voice", options=options, min_values=1, max_values=1)
        self.guild = guild
        self.admin_id = admin_id
        self.game_states = game_states

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
            return
        await interaction.response.defer()
        
        try:
            # self.values là list nên chỉ cần truy cập phần tử đầu tiên
            voice_channel_id = int(self.values[0])
            voice_channel = self.guild.get_channel(voice_channel_id)
            
            if not voice_channel or not voice_channel.members:
                await interaction.followup.send("Kênh voice này không có người hoặc không tồn tại!", ephemeral=True)
                return
                
            guild_id = self.guild.id
            game_state = self.game_states.get(guild_id) or {}
            
            # Sử dụng try/except để xử lý cả trường hợp game_state là dict hoặc class
            try:
                game_state.voice_channel_id = voice_channel_id
                game_state.guild_id = guild_id
            except:
                game_state["voice_channel_id"] = voice_channel_id
                game_state["guild_id"] = guild_id
            
            # Hiển thị menu chọn số lượng người chơi
            content = f"Đã chọn kênh voice {voice_channel.name}. Chọn số lượng người chơi (tối thiểu 4, tối đa {len(voice_channel.members)}):"
            
            view = PlayerCountView(len(voice_channel.members), self.admin_id, game_state)
            
            try:
                await interaction.message.edit(content=content, view=view)
            except discord.errors.NotFound:
                logger.warning("Tin nhắn không tồn tại để chỉnh sửa, gửi tin nhắn mới.")
                new_message = await interaction.channel.send(content=content, view=view)
                try:
                    game_state.setup_message = new_message
                except:
                    game_state["setup_message"] = new_message
                
        except Exception as e:
            logger.error(f"Lỗi khi xử lý chọn kênh voice: {str(e)}")
            traceback.print_exc()
            await interaction.followup.send(f"Đã xảy ra lỗi: {str(e)}", ephemeral=True)

class PlayerCountView(discord.ui.View):
    """View để chọn số lượng người chơi"""
    def __init__(self, max_players, admin_id, game_state):
        super().__init__(timeout=180)
        self.add_item(PlayerCountSelect(max_players, admin_id, game_state))

class PlayerCountSelect(discord.ui.Select):
    """Select menu để chọn số lượng người chơi"""
    def __init__(self, max_players, admin_id, game_state):
        options = [
            discord.SelectOption(label=str(i), value=str(i))
            for i in range(4, min(max_players + 1, 26))
        ]
        super().__init__(placeholder="Chọn số lượng người chơi", options=options, min_values=1, max_values=1)
        self.admin_id = admin_id
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        try:
            # self.values là list nên chỉ cần truy cập phần tử đầu tiên
            player_count = int(self.values[0])
            
            # Sử dụng try/except để xử lý cả trường hợp game_state là dict hoặc class
            try:
                self.game_state.temp_player_count = player_count
                voice_channel = interaction.guild.get_channel(self.game_state.voice_channel_id)
            except:
                self.game_state["temp_player_count"] = player_count
                voice_channel = interaction.guild.get_channel(self.game_state.get("voice_channel_id"))
            
            if voice_channel:
                human_members_count = len([m for m in voice_channel.members if not m.bot])
                if human_members_count < player_count:
                    await interaction.followup.send("Số người (không phải bot) trong kênh voice không đủ cho số lượng đã chọn!", ephemeral=True)
                    return
            else:
                await interaction.followup.send("Kênh voice không tồn tại!", ephemeral=True)
                return
            
            # Hiển thị menu chọn người chơi
            content = f"Đã chọn số lượng người chơi: {player_count}. Chọn danh sách người chơi:"
            
            view = PlayerSelectView(interaction.guild, interaction.user.id, self.game_state)
            
            try:
                await interaction.message.edit(content=content, view=view)
            except discord.errors.NotFound:
                logger.warning("Tin nhắn không tồn tại để chỉnh sửa, gửi tin nhắn mới.")
                new_message = await interaction.channel.send(content=content, view=view)
                try:
                    self.game_state.setup_message = new_message
                except:
                    self.game_state["setup_message"] = new_message
                
        except Exception as e:
            logger.error(f"Lỗi khi xử lý chọn số lượng người chơi: {str(e)}")
            traceback.print_exc()
            await interaction.followup.send(f"Đã xảy ra lỗi: {str(e)}", ephemeral=True)

class PlayerSelectView(discord.ui.View):
    """View để chọn danh sách người chơi"""
    def __init__(self, guild, admin_id, game_state):
        super().__init__(timeout=180)
        self.add_item(PlayerSelect(guild, admin_id, game_state))

class PlayerSelect(discord.ui.Select):
    """Select menu để chọn người chơi"""
    def __init__(self, guild, admin_id, game_state):
        # Sử dụng try/except để xử lý cả trường hợp game_state là dict hoặc class
        try:
            voice_channel_id = game_state.voice_channel_id
        except:
            voice_channel_id = game_state.get("voice_channel_id")
            
        voice_channel = guild.get_channel(voice_channel_id) if voice_channel_id else None
        logger.info(f"Khởi tạo PlayerSelect: voice_channel_id={voice_channel_id}, voice_channel={voice_channel}, guild_id={guild.id}")
        
        # Lọc bỏ các bot khỏi danh sách members
        members = [m for m in voice_channel.members if not m.bot][:25] if voice_channel and hasattr(voice_channel, 'members') else []
        
        if not members:
            options = [discord.SelectOption(label="Không có người chơi", value="none")]
            min_values = 1
            max_values = 1
        else:
            options = []
            for member in members:
                try:
                    display_name = member.display_name
                    if len(display_name) > 25:  # Discord giới hạn 25 ký tự cho label
                        display_name = display_name[:22] + "..."
                    options.append(discord.SelectOption(label=display_name, value=str(member.id)))
                except Exception as e:
                    logger.error(f"Lỗi tạo SelectOption cho player ID={member.id}, DisplayName={repr(member.display_name)}, error={str(e)}")
                    continue
            
            # Lấy temp_player_count an toàn
            try:
                temp_player_count = game_state.temp_player_count
            except:
                temp_player_count = game_state.get("temp_player_count", 1)
                
            actual_options = len(options)
            min_values = min(temp_player_count, actual_options)
            max_values = min(temp_player_count, actual_options)
            
        super().__init__(
            placeholder="Chọn người chơi",
            options=options,
            min_values=min_values,
            max_values=max_values
        )
        
        self.admin_id = admin_id
        self.guild = guild
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        try:
            # Lấy voice_channel_id an toàn
            try:
                voice_channel_id = self.game_state.voice_channel_id
            except:
                voice_channel_id = self.game_state.get("voice_channel_id")
                
            if not voice_channel_id:
                logger.error(f"Không có voice_channel_id trong game_state, interaction_id={interaction.id}")
                await interaction.followup.send("Lỗi: Không tìm thấy ID kênh voice. Vui lòng chạy lại /start_game!", ephemeral=True)
                return
                
            voice_channel = self.guild.get_channel(voice_channel_id)
            if not voice_channel:
                logger.error(f"Không tìm thấy kênh voice: ID={voice_channel_id}, interaction_id={interaction.id}")
                await interaction.followup.send("Lỗi: Kênh voice không tồn tại. Vui lòng chạy lại /start_game!", ephemeral=True)
                return
                
            current_members = await retry_api_call(lambda: {m.id: m for m in voice_channel.members if m}, max_attempts=5, initial_delay=2)
            if not current_members:
                logger.error(f"Không có người chơi nào trong kênh voice: ID={voice_channel_id}, interaction_id={interaction.id}")
                await interaction.followup.send("Lỗi: Kênh voice không có người chơi nào! Vui lòng kiểm tra và thử lại.", ephemeral=True)
                return
                
            # self.values là list, xử lý trực tiếp không qua .values()
            if "none" in self.values:
                logger.error(f"Không có người chơi trong kênh voice, interaction_id={interaction.id}")
                await interaction.followup.send("Không có người chơi trong kênh voice!", ephemeral=True)
                return
            
            # Tạo member_cache
            members_list = await retry_api_call(lambda: self.guild.members, max_attempts=5, initial_delay=2)
            member_cache = {m.id: m for m in members_list}
            
            # Gán vào game_state
            try:
                self.game_state.member_cache = member_cache
            except:
                self.game_state["member_cache"] = member_cache
            
            selected_ids = []
            selected_names = []
            
            # Đây là điểm quan trọng: self.values là list, KHÔNG gọi .values() trên nó
            values_list = self.values  # Đây là list chứa các ID đã chọn
            for id_str in values_list:
                try:
                    user_id = int(id_str)
                    if user_id not in current_members:
                        logger.warning(f"Player ID={user_id} không còn trong kênh voice, interaction_id={interaction.id}")
                        await interaction.followup.send(f"Một người chơi (ID: {id_str}) đã rời kênh voice! Vui lòng chọn lại.", ephemeral=True)
                        return
                    
                    member = member_cache.get(user_id)
                    if not member or not isinstance(member, discord.Member):
                        logger.error(f"Không tìm thấy member: ID={user_id}, member={member}, interaction_id={interaction.id}")
                        await interaction.followup.send(f"Không tìm thấy người chơi với ID {id_str}! Có thể họ đã rời server.", ephemeral=True)
                        return
                        
                    voice_state = member.voice
                    if not voice_state or not voice_state.channel or voice_state.channel.id != voice_channel_id:
                        logger.error(f"Player ID={user_id} có voice state không hợp lệ: voice={voice_state}, channel={voice_state.channel if voice_state else None}, interaction_id={interaction.id}")
                        await interaction.followup.send(f"Người chơi {member.display_name} không còn trong kênh voice hợp lệ!", ephemeral=True)
                        return
                        
                    selected_ids.append(user_id)
                    selected_names.append(member.display_name)
                    
                except ValueError as ve:
                    logger.error(f"ID không hợp lệ trong PlayerSelect: {id_str}, error={str(ve)}, interaction_id={interaction.id}")
                    await interaction.followup.send("Lỗi: ID người chơi không hợp lệ!", ephemeral=True)
                    return
                except Exception as e:
                    logger.error(f"Lỗi khi xử lý player ID={id_str}, error={str(e)}, interaction_id={interaction.id}")
                    await interaction.followup.send(f"Lỗi khi xử lý người chơi ID {id_str}. Vui lòng thử lại!", ephemeral=True)
                    return
            
            # Lấy temp_player_count an toàn
            try:
                temp_player_count = self.game_state.temp_player_count
            except:
                temp_player_count = self.game_state.get("temp_player_count")
                
            if len(selected_ids) != temp_player_count:
                await interaction.followup.send(
                    f"Vui lòng chọn đúng {temp_player_count} người chơi! Đã chọn: {len(selected_ids)}",
                    ephemeral=True
                )
                return
            
            # Gán giá trị vào game_state
            try:
                self.game_state.temp_players = selected_ids
            except:
                self.game_state["temp_players"] = selected_ids
                
            selected_players_str = ", ".join(selected_names)
            
            # QUAN TRỌNG: Khởi tạo temp_roles là dictionary trước khi tạo RoleSelectView
            # Đảm bảo temp_roles là dictionary
            try:
                if not hasattr(self.game_state, 'temp_roles') or not isinstance(self.game_state.temp_roles, dict):
                    self.game_state.temp_roles = {role: 0 for role in ROLES}
                    logger.info("Đã khởi tạo temp_roles mới (thuộc tính)")
            except:
                if 'temp_roles' not in self.game_state or not isinstance(self.game_state.get('temp_roles'), dict):
                    self.game_state['temp_roles'] = {role: 0 for role in ROLES}
                    logger.info("Đã khởi tạo temp_roles mới (dictionary)")
            
            # Hiển thị menu chọn vai trò
            content = f"Đã chọn người chơi: {selected_players_str}. Chọn số lượng Sói, Dân Làng và vai đặc biệt (tổng phải bằng {temp_player_count}):"
            
            view = RoleSelectView(interaction.user.id, self.game_state)
            
            try:
                await interaction.message.edit(content=content, view=view)
            except discord.errors.NotFound:
                logger.warning("Tin nhắn không tồn tại để chỉnh sửa, gửi tin nhắn mới.")
                new_message = await interaction.channel.send(content=content, view=view)
                try:
                    self.game_state.setup_message = new_message
                except:
                    self.game_state["setup_message"] = new_message
                
        except Exception as e:
            logger.error(f"Lỗi không xác định trong PlayerSelect.callback: error='{str(e)}', interaction_id={interaction.id}")
            traceback.print_exc()
            await interaction.followup.send("Lỗi không xác định khi xử lý lựa chọn người chơi. Vui lòng thử lại!", ephemeral=True)

class RoleSelectView(discord.ui.View):
    """View cho lựa chọn vai trò"""
    def __init__(self, admin_id, game_state):
        super().__init__(timeout=180)
        self.admin_id = admin_id
        self.game_state = game_state
        
        # Đảm bảo temp_roles là dictionary
        try:
            temp_player_count = game_state.temp_player_count
            temp_roles = game_state.temp_roles
            if not isinstance(temp_roles, dict):
                logger.warning(f"temp_roles không phải dictionary trong RoleSelectView: {type(temp_roles)}")
                temp_roles = {role: 0 for role in ROLES}
                game_state.temp_roles = temp_roles
        except Exception as e:
            logger.warning(f"Lỗi khi truy cập temp_roles trong RoleSelectView: {str(e)}")
            temp_player_count = game_state.get("temp_player_count", 1)
            temp_roles = game_state.get("temp_roles")
            if not isinstance(temp_roles, dict):
                logger.warning(f"temp_roles không phải dictionary trong RoleSelectView (dict): {type(temp_roles)}")
                temp_roles = {role: 0 for role in ROLES}
                game_state["temp_roles"] = temp_roles
            
        logger.info(f"Khởi tạo RoleSelectView: admin_id={admin_id}, temp_player_count={temp_player_count}, temp_roles={temp_roles}")
        
        # Thêm các item cho view
        self.add_item(WerewolfCountSelect(game_state))
        self.add_item(VillagerCountSelect(game_state))
        self.add_item(VillagerSpecialRoleSelect(game_state))
        self.add_item(WerewolfSpecialRoleSelect(game_state))
        self.add_item(ConfirmButton(game_state))
        self.add_item(ResetRolesButton(game_state))

class WerewolfCountSelect(discord.ui.Select):
    """Select menu để chọn số lượng Sói thường"""
    def __init__(self, game_state):
        # Lấy giá trị an toàn với kiểm tra TYPE
        try:
            temp_player_count = game_state.temp_player_count
            temp_roles = game_state.temp_roles
        except:
            temp_player_count = game_state.get("temp_player_count", 1)
            temp_roles = game_state.get("temp_roles", {})
            
        # THÊM KIỂM TRA VÀ KHỞI TẠO TEMP_ROLES
        if not isinstance(temp_roles, dict):
            logger.warning(f"temp_roles không phải dictionary, khởi tạo mới: {temp_roles}")
            temp_roles = {role: 0 for role in ROLES}
            # Lưu lại temp_roles đã sửa
            try:
                game_state.temp_roles = temp_roles
            except:
                game_state["temp_roles"] = temp_roles
        
        # Đảm bảo Werewolf có trong temp_roles
        if "Werewolf" not in temp_roles:
            temp_roles["Werewolf"] = 0
            
        # Giờ an toàn để gọi .values()
        total_roles = sum(temp_roles.values())
        remaining = temp_player_count - total_roles
        
        options = [
            discord.SelectOption(label=str(i), value=str(i))
            for i in range(0, min(remaining + temp_roles["Werewolf"] + 1, temp_player_count + 1))
        ]
        super().__init__(
            placeholder=f"Chọn số lượng Sói (hiện tại: {temp_roles['Werewolf']})",
            options=options,
            min_values=1,
            max_values=1
        )
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
            return
        
        # self.values là list, lấy phần tử đầu tiên
        count = int(self.values[0])
        
        # Đảm bảo temp_roles là dict trước khi gán giá trị
        try:
            if not isinstance(self.game_state.temp_roles, dict):
                self.game_state.temp_roles = {role: 0 for role in ROLES}
            self.game_state.temp_roles["Werewolf"] = count
            temp_roles = self.game_state.temp_roles
            temp_player_count = self.game_state.temp_player_count
        except:
            if not isinstance(self.game_state.get("temp_roles", {}), dict):
                self.game_state["temp_roles"] = {role: 0 for role in ROLES}
            self.game_state["temp_roles"]["Werewolf"] = count
            temp_roles = self.game_state.get("temp_roles", {})
            temp_player_count = self.game_state.get("temp_player_count", 1)
            
        total_roles = sum(temp_roles.values())
        remaining = temp_player_count - total_roles
        
        logger.info(f"Đã chọn số lượng Sói: count={count}, total_roles={total_roles}, remaining={remaining}, interaction_id={interaction.id}")
        
        # Tạo chuỗi tổng kết vai trò
        role_summary = "\n".join([f"{role}: {count}" for role, count in temp_roles.items() if count > 0])
        if not role_summary:
            role_summary = "Chưa có vai trò nào được chọn"
            
        new_content = (f"Chọn số lượng Sói, Dân Làng và vai đặc biệt (tổng phải bằng {temp_player_count}):\n"
                       f"Trạng thái vai trò:\n{role_summary}\n"
                       f"Tổng vai: {total_roles}/{temp_player_count} (còn {remaining})")
                       
        new_view = RoleSelectView(self.view.admin_id, self.game_state)
        await interaction.response.edit_message(content=new_content, view=new_view)

class VillagerCountSelect(discord.ui.Select):
    """Select menu để chọn số lượng Dân Làng thường"""
    def __init__(self, game_state):
        # Lấy giá trị an toàn với kiểm tra TYPE
        try:
            temp_player_count = game_state.temp_player_count
            temp_roles = game_state.temp_roles
        except:
            temp_player_count = game_state.get("temp_player_count", 1)
            temp_roles = game_state.get("temp_roles", {})
            
        # THÊM KIỂM TRA VÀ KHỞI TẠO TEMP_ROLES
        if not isinstance(temp_roles, dict):
            logger.warning(f"temp_roles không phải dictionary, khởi tạo mới trong VillagerCountSelect: {temp_roles}")
            temp_roles = {role: 0 for role in ROLES}
            # Lưu lại temp_roles đã sửa
            try:
                game_state.temp_roles = temp_roles
            except:
                game_state["temp_roles"] = temp_roles
        
        # Đảm bảo Villager có trong temp_roles
        if "Villager" not in temp_roles:
            temp_roles["Villager"] = 0
            
        # Giờ an toàn để gọi .values()
        total_roles = sum(temp_roles.values())
        remaining = temp_player_count - total_roles
        
        options = [
            discord.SelectOption(label=str(i), value=str(i))
            for i in range(0, min(remaining + temp_roles["Villager"] + 1, temp_player_count + 1))
        ]
        super().__init__(
            placeholder=f"Chọn số lượng Dân Làng (hiện tại: {temp_roles['Villager']})",
            options=options,
            min_values=1,
            max_values=1
        )
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
            return
        
        # self.values là list, lấy phần tử đầu tiên
        count = int(self.values[0])
        
        # Đảm bảo temp_roles là dict trước khi gán giá trị
        try:
            if not isinstance(self.game_state.temp_roles, dict):
                self.game_state.temp_roles = {role: 0 for role in ROLES}
            self.game_state.temp_roles["Villager"] = count
            temp_roles = self.game_state.temp_roles
            temp_player_count = self.game_state.temp_player_count
        except:
            if not isinstance(self.game_state.get("temp_roles", {}), dict):
                self.game_state["temp_roles"] = {role: 0 for role in ROLES}
            self.game_state["temp_roles"]["Villager"] = count
            temp_roles = self.game_state.get("temp_roles", {})
            temp_player_count = self.game_state.get("temp_player_count", 1)
            
        total_roles = sum(temp_roles.values())
        remaining = temp_player_count - total_roles
        
        logger.info(f"Đã chọn số lượng Dân Làng: count={count}, total_roles={total_roles}, remaining={remaining}, interaction_id={interaction.id}")
        
        # Tạo chuỗi tổng kết vai trò
        role_summary = "\n".join([f"{role}: {count}" for role, count in temp_roles.items() if count > 0])
        if not role_summary:
            role_summary = "Chưa có vai trò nào được chọn"
            
        new_content = (f"Chọn số lượng Sói, Dân Làng và vai đặc biệt (tổng phải bằng {temp_player_count}):\n"
                       f"Trạng thái vai trò:\n{role_summary}\n"
                       f"Tổng vai: {total_roles}/{temp_player_count} (còn {remaining})")
                       
        new_view = RoleSelectView(self.view.admin_id, self.game_state)
        await interaction.response.edit_message(content=new_content, view=new_view)

class VillagerSpecialRoleSelect(discord.ui.Select):
    """Select menu để chọn vai đặc biệt Phe Dân"""
    def __init__(self, game_state):
        # Lấy giá trị an toàn với kiểm tra TYPE
        try:
            temp_player_count = game_state.temp_player_count
            temp_roles = game_state.temp_roles
        except:
            temp_player_count = game_state.get("temp_player_count", 1)
            temp_roles = game_state.get("temp_roles", {})
            
        # THÊM KIỂM TRA VÀ KHỞI TẠO TEMP_ROLES
        if not isinstance(temp_roles, dict):
            logger.warning(f"temp_roles không phải dictionary, khởi tạo mới trong VillagerSpecialRoleSelect: {temp_roles}")
            temp_roles = {role: 0 for role in ROLES}
            # Lưu lại temp_roles đã sửa
            try:
                game_state.temp_roles = temp_roles
            except:
                game_state["temp_roles"] = temp_roles
                
        # Giờ an toàn để gọi .values()
        total_roles = sum(temp_roles.values())
        remaining = temp_player_count - total_roles
        options = []
        
        for role in VILLAGER_SPECIAL_ROLES:
            if temp_roles.get(role, 0) == 0 and remaining > 0:
                options.append(discord.SelectOption(label=role, value=role))
                
        if not options:
            options.append(discord.SelectOption(label="Không còn vai đặc biệt Phe Dân", value="none"))
            
        super().__init__(
            placeholder=f"Chọn vai đặc biệt Phe Dân (còn {remaining} vai)",
            options=options,
            min_values=1,
            max_values=1
        )
        
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
            return
        
        # self.values là list, lấy phần tử đầu tiên
        role_value = self.values[0]
            
        if role_value == "none":
            await interaction.response.send_message("Không còn vai đặc biệt Phe Dân để chọn!", ephemeral=True)
            return
        
        # Đảm bảo temp_roles là dict trước khi gán giá trị
        try:
            if not isinstance(self.game_state.temp_roles, dict):
                self.game_state.temp_roles = {role: 0 for role in ROLES}
            self.game_state.temp_roles[role_value] = 1
            temp_roles = self.game_state.temp_roles
            temp_player_count = self.game_state.temp_player_count
        except:
            if not isinstance(self.game_state.get("temp_roles", {}), dict):
                self.game_state["temp_roles"] = {role: 0 for role in ROLES}
            self.game_state["temp_roles"][role_value] = 1
            temp_roles = self.game_state.get("temp_roles", {})
            temp_player_count = self.game_state.get("temp_player_count", 1)
            
        total_roles = sum(temp_roles.values())
        remaining = temp_player_count - total_roles
        
        logger.info(f"Đã chọn vai đặc biệt Phe Dân: role={role_value}, count=1, total_roles={total_roles}, remaining={remaining}, interaction_id={interaction.id}")
        
        # Tạo chuỗi tổng kết vai trò
        role_summary = "\n".join([f"{r}: {count}" for r, count in temp_roles.items() if count > 0])
        if not role_summary:
            role_summary = "Chưa có vai trò nào được chọn"
            
        new_content = (f"Chọn số lượng Sói, Dân Làng và vai đặc biệt (tổng phải bằng {temp_player_count}):\n"
                       f"Trạng thái vai trò:\n{role_summary}\n"
                       f"Tổng vai: {total_roles}/{temp_player_count} (còn {remaining})")
                       
        new_view = RoleSelectView(self.view.admin_id, self.game_state)
        await interaction.response.edit_message(content=new_content, view=new_view)

class WerewolfSpecialRoleSelect(discord.ui.Select):
    """Select menu để chọn vai đặc biệt Phe Sói"""
    def __init__(self, game_state):
        # Lấy giá trị an toàn với kiểm tra TYPE
        try:
            temp_player_count = game_state.temp_player_count
            temp_roles = game_state.temp_roles
        except:
            temp_player_count = game_state.get("temp_player_count", 1)
            temp_roles = game_state.get("temp_roles", {})
            
        # THÊM KIỂM TRA VÀ KHỞI TẠO TEMP_ROLES
        if not isinstance(temp_roles, dict):
            logger.warning(f"temp_roles không phải dictionary, khởi tạo mới trong WerewolfSpecialRoleSelect: {temp_roles}")
            temp_roles = {role: 0 for role in ROLES}
            # Lưu lại temp_roles đã sửa
            try:
                game_state.temp_roles = temp_roles
            except:
                game_state["temp_roles"] = temp_roles
                
        # Giờ an toàn để gọi .values()
        total_roles = sum(temp_roles.values())
        remaining = temp_player_count - total_roles
        options = []
        
        for role in WEREWOLF_SPECIAL_ROLES:
            if temp_roles.get(role, 0) == 0 and remaining > 0:
                options.append(discord.SelectOption(label=role, value=role))
                
        if not options:
            options.append(discord.SelectOption(label="Không còn vai đặc biệt Phe Sói", value="none"))
            
        super().__init__(
            placeholder=f"Chọn vai đặc biệt Phe Sói (còn {remaining} vai)",
            options=options,
            min_values=1,
            max_values=1
        )
        
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
            return
        
        # self.values là list, lấy phần tử đầu tiên
        role_value = self.values[0]
            
        if role_value == "none":
            await interaction.response.send_message("Không còn vai đặc biệt Phe Sói để chọn!", ephemeral=True)
            return
            
        # Đảm bảo temp_roles là dict trước khi gán giá trị
        try:
            if not isinstance(self.game_state.temp_roles, dict):
                self.game_state.temp_roles = {role: 0 for role in ROLES}
            self.game_state.temp_roles[role_value] = 1
            temp_roles = self.game_state.temp_roles
            temp_player_count = self.game_state.temp_player_count
        except:
            if not isinstance(self.game_state.get("temp_roles", {}), dict):
                self.game_state["temp_roles"] = {role: 0 for role in ROLES}
            self.game_state["temp_roles"][role_value] = 1
            temp_roles = self.game_state.get("temp_roles", {})
            temp_player_count = self.game_state.get("temp_player_count", 1)
            
        total_roles = sum(temp_roles.values())
        remaining = temp_player_count - total_roles
        
        logger.info(f"Đã chọn vai đặc biệt Phe Sói: role={role_value}, count=1, total_roles={total_roles}, remaining={remaining}, interaction_id={interaction.id}")
        
        # Tạo chuỗi tổng kết vai trò
        role_summary = "\n".join([f"{r}: {count}" for r, count in temp_roles.items() if count > 0])
        if not role_summary:
            role_summary = "Chưa có vai trò nào được chọn"
            
        new_content = (f"Chọn số lượng Sói, Dân Làng và vai đặc biệt (tổng phải bằng {temp_player_count}):\n"
                       f"Trạng thái vai trò:\n{role_summary}\n"
                       f"Tổng vai: {total_roles}/{temp_player_count} (còn {remaining})")
                       
        new_view = RoleSelectView(self.view.admin_id, self.game_state)
        await interaction.response.edit_message(content=new_content, view=new_view)

class ConfirmButton(discord.ui.Button):
    """Button để xác nhận thiết lập game"""
    def __init__(self, game_state):
        super().__init__(label="Xác nhận", style=discord.ButtonStyle.green)
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
            return
            
        # Lấy thông tin an toàn
        try:
            temp_roles = self.game_state.temp_roles
            temp_player_count = self.game_state.temp_player_count
            if not isinstance(temp_roles, dict):
                logger.warning(f"temp_roles không phải dictionary trong ConfirmButton: {temp_roles}")
                temp_roles = {role: 0 for role in ROLES}
                self.game_state.temp_roles = temp_roles
        except:
            temp_roles = self.game_state.get("temp_roles", {})
            temp_player_count = self.game_state.get("temp_player_count", 1)
            if not isinstance(temp_roles, dict):
                logger.warning(f"temp_roles không phải dictionary trong ConfirmButton (dict): {temp_roles}")
                temp_roles = {role: 0 for role in ROLES}
                self.game_state["temp_roles"] = temp_roles
            
        total_roles = sum(temp_roles.values())
        logger.info(f"ConfirmButton clicked: total_roles={total_roles}, expected={temp_player_count}, temp_roles={temp_roles}, interaction_id={interaction.id}")
        
        # Kiểm tra điều kiện hợp lệ
        if total_roles != temp_player_count:
            await interaction.response.send_message(
                f"Tổng số vai ({total_roles}) không khớp với số người chơi ({temp_player_count})!",
                ephemeral=True
            )
            return
            
        werewolf_count = (temp_roles.get("Werewolf", 0) + 
                         temp_roles.get("Wolfman", 0) + 
                         temp_roles.get("Assassin Werewolf", 0))
        
        if werewolf_count < 1:
            await interaction.response.send_message("Phải có ít nhất 1 Sói, Người Sói hoặc Sói Ám Sát!", ephemeral=True)
            return
            
        if temp_roles.get("Villager", 0) < 0:
            await interaction.response.send_message("Số Dân Làng không thể âm!", ephemeral=True)
            return
            
        # Xác nhận và khởi động game
        await interaction.response.edit_message(content="Khởi tạo game!", view=None)
        
        # Import hàm khởi động game ở đây để tránh circular import
        from phases.game_setup import start_game_logic
        await start_game_logic(interaction, self.game_state)

class ResetRolesButton(discord.ui.Button):
    """Button để reset lựa chọn vai trò"""
    def __init__(self, game_state):
        super().__init__(label="Reset Roles", style=discord.ButtonStyle.red)
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
            return
        
        # Reset vai trò an toàn
        empty_roles = {role: 0 for role in ROLES}
        try:
            self.game_state.temp_roles = empty_roles
            temp_player_count = self.game_state.temp_player_count
        except:
            self.game_state["temp_roles"] = empty_roles
            temp_player_count = self.game_state.get("temp_player_count", 1)
            
        total_roles = sum(empty_roles.values())
        remaining = temp_player_count - total_roles
        
        logger.info(f"Vai trò đã reset: temp_roles={empty_roles}, interaction_id={interaction.id}")
        
        role_summary = "\n".join([f"{role}: {count}" for role, count in empty_roles.items() if count > 0])
        if not role_summary:
            role_summary = "Chưa có vai trò nào được chọn"
            
        new_content = (f"Đã reset vai trò. Chọn số lượng Sói, Dân Làng và vai đặc biệt (tổng phải bằng {temp_player_count}):\n"
                       f"Trạng thái vai trò:\n{role_summary}\n"
                       f"Tổng vai: {total_roles}/{temp_player_count} (còn {remaining})")
                       
        new_view = RoleSelectView(self.view.admin_id, self.game_state)
        await interaction.response.edit_message(content=new_content, view=new_view)