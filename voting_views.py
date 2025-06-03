# views/voting_views.py
# UI Components cho việc bỏ phiếu

import discord
import logging
from typing import List, Dict, Optional

from constants import NO_NIGHT_ACTION_ROLES

logger = logging.getLogger(__name__)

class VoteView(discord.ui.View):
    """View cho việc bỏ phiếu ban ngày"""
    def __init__(self, alive_players, game_state, timeout=45):
        super().__init__(timeout=timeout)
        self.alive_players = alive_players
        self.game_state = game_state
        self.add_item(VoteSelect(alive_players, game_state))
        self.add_item(SkipButton(game_state))

class VoteSelect(discord.ui.Select):
    """Select menu cho việc bỏ phiếu"""
    def __init__(self, alive_players, game_state):
        options = [
            discord.SelectOption(
                label=member.display_name[:25], 
                value=str(member.id),
                description=f"ID: {member.id % 10000}"
            )
            for member in alive_players
        ]
        super().__init__(placeholder="Chọn người để loại", options=options, min_values=1, max_values=1)
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        # Kiểm tra điều kiện cơ bản
        if interaction.user.id not in self.game_state["players"] or self.game_state["players"][interaction.user.id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Bạn không thể bỏ phiếu!", ephemeral=True)
            return
            
        if self.game_state["phase"] != "voting":
            await interaction.response.send_message("Chưa phải pha bỏ phiếu!", ephemeral=True)
            return
            
        if self.game_state["is_game_paused"]:
            await interaction.response.send_message("Game đang tạm dừng, không thể bỏ phiếu!", ephemeral=True)
            return

        # Ghi nhận phiếu bầu
        target_id = int(self.values[0])
        self.game_state["votes"][interaction.user.id] = target_id
        
        target_member = next((m for m in self.options if m.value == self.values[0]), None)
        target_name = target_member.label if target_member else "Unknown"

        # Kiểm tra điều kiện để hiển thị thông báo phù hợp
        player_data = self.game_state["players"][interaction.user.id]
        
        # Người chơi đủ điều kiện nếu: vai trò không yêu cầu toán HOẶC đã giải toán đúng
        if player_data["role"] not in NO_NIGHT_ACTION_ROLES or (interaction.user.id in self.game_state["math_results"] and self.game_state["math_results"][interaction.user.id]):
            embed = discord.Embed(
                title="🗳️ Phiếu Bầu Đã Ghi Nhận",
                description=f"Bạn đã bỏ phiếu cho **{target_name}**!",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="🗳️ Phiếu Bầu Không Hợp Lệ",
                description=f"Bạn đã bỏ phiếu cho **{target_name}**, nhưng phiếu của bạn không được tính do không giải đúng bài toán!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        logger.info(f"Player {interaction.user.id} voted for {target_id} ({target_name})")

class SkipButton(discord.ui.Button):
    """Button để bỏ qua vote"""
    def __init__(self, game_state):
        super().__init__(label="Bỏ qua", style=discord.ButtonStyle.grey)
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.game_state["players"] or self.game_state["players"][interaction.user.id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Bạn không thể bỏ phiếu!", ephemeral=True)
            return
            
        if self.game_state["phase"] != "voting":
            await interaction.response.send_message("Chưa phải pha bỏ phiếu!", ephemeral=True)
            return
            
        if self.game_state["is_game_paused"]:
            await interaction.response.send_message("Game đang tạm dừng, không thể bỏ phiếu!", ephemeral=True)
            return
            
        if interaction.user.id in self.game_state["math_results"] and not self.game_state["math_results"][interaction.user.id]:
            embed = discord.Embed(
                title="🗳️ Không Thể Bỏ Phiếu",
                description="Bạn không có quyền bỏ phiếu do trả lời sai bài toán đêm qua!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        self.game_state["votes"][interaction.user.id] = "skip"
        
        embed = discord.Embed(
            title="🗳️ Bỏ Qua Bỏ Phiếu",
            description="Bạn đã chọn bỏ qua việc bỏ phiếu trong lượt này.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"Player {interaction.user.id} skipped voting")

class GameEndView(discord.ui.View):
    """View cho tùy chọn khi game kết thúc"""
    def __init__(self, admin_id, interaction, game_state):
        super().__init__(timeout=60)
        self.admin_id = admin_id
        self.interaction = interaction
        self.game_state = game_state

    @discord.ui.button(label="Start New Game", style=discord.ButtonStyle.green)
    async def start_new_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id != self.admin_id:
                await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
                return
                
            embed = discord.Embed(
                title="🎮 Bắt Đầu Game Mới",
                description="Đang khởi tạo game mới với cùng người chơi và vai trò...",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Disable button để ngăn nhấn nhiều lần
            button.disabled = True
            try:
                await interaction.message.edit(view=self)
            except:
                logger.warning("Không thể cập nhật nút sau khi nhấn")
            
            # Import hàm khởi động game mới ở đây để tránh circular import
            from phases.game_setup import start_new_game_with_same_setup
            # Sửa: Sử dụng interaction mới thay vì self.interaction
            await start_new_game_with_same_setup(interaction, self.game_state)
            
        except Exception as e:
            logger.error(f"Lỗi khi bắt đầu game mới: {str(e)}")
            try:
                # Nếu có thể vẫn trả lời được interaction
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Lỗi khi bắt đầu game mới: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Lỗi khi bắt đầu game mới: {str(e)}", ephemeral=True)
            except:
                # Nếu không thể phản hồi interaction, gửi tin nhắn qua channel
                try:
                    await interaction.channel.send(f"Lỗi khi bắt đầu game mới: {str(e)}")
                except:
                    logger.error("Không thể gửi thông báo lỗi")

    @discord.ui.button(label="End Game", style=discord.ButtonStyle.red)
    async def end_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id != self.admin_id:
                await interaction.response.send_message("Chỉ người chạy lệnh /start_game được thao tác!", ephemeral=True)
                return
                
            embed = discord.Embed(
                title="🛑 Kết Thúc Game",
                description="Game đã kết thúc hoàn toàn.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Disable button để ngăn nhấn nhiều lần
            button.disabled = True
            self.children[0].disabled = True  # Disable nút Start New Game cũng
            try:
                await interaction.message.edit(view=self)
            except:
                logger.warning("Không thể cập nhật nút sau khi nhấn")
            
            # Reset game state
            self.game_state["temp_players"] = []
            self.game_state["temp_roles"] = {role: 0 for role in self.game_state["temp_roles"].keys()} if isinstance(self.game_state["temp_roles"], dict) else {}
            self.game_state["temp_admin_id"] = None
            self.game_state["voice_channel_id"] = None
            self.game_state["guild_id"] = None 
            self.game_state["text_channel"] = None
            self.game_state["member_cache"].clear()
            
            logger.info(f"Game ended by admin {interaction.user.id}")
            
        except Exception as e:
            logger.error(f"Lỗi khi kết thúc game: {str(e)}")
            try:
                await interaction.followup.send(f"Lỗi: {str(e)}", ephemeral=True)
            except:
                try:
                    await interaction.channel.send(f"Lỗi khi kết thúc game: {str(e)}")
                except:
                    logger.error("Không thể gửi thông báo lỗi")