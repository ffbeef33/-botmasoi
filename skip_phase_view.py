# views/skip_phase_view.py
# View hiển thị cho tính năng bỏ qua pha thảo luận

import discord
import logging
import asyncio
from typing import Dict, Set, Optional

from phases.voting import start_voting_phase

logger = logging.getLogger(__name__)

class SkipPhaseView(discord.ui.View):
    """View cho phép người chơi bỏ phiếu bỏ qua pha thảo luận"""
    
    def __init__(self, interaction, game_state):
        super().__init__(timeout=300)  # 5 phút timeout
        self.game_state = game_state
        self.original_interaction = interaction
        self.message = None
        self.voted_users: Set[int] = set()  # Danh sách người đã vote
        self.required_votes = 0  # Số vote cần thiết, sẽ được tính sau
        self.is_completed = False  # Cờ đánh dấu đã xử lý xong
        self.update_timer = None  # Timer để cập nhật message
    
    def get_alive_players_count(self) -> int:
        """Lấy số lượng người chơi còn sống"""
        return sum(1 for player_data in self.game_state["players"].values() 
                   if player_data["status"] == "alive")
    
    def calculate_required_votes(self) -> int:
        """Tính số lượng vote cần thiết (50% số người chơi còn sống)"""
        alive_count = self.get_alive_players_count()
        return (alive_count + 1) // 2  # Làm tròn lên nếu số lẻ
    
    def get_vote_status_text(self) -> str:
        """Tạo text hiển thị trạng thái vote hiện tại"""
        voted_players = []
        for user_id in self.voted_users:
            member = self.game_state["member_cache"].get(user_id)
            if member:
                voted_players.append(member.display_name)
        
        vote_text = "Chưa có ai bỏ phiếu" if not voted_players else "\n".join([f"• {name}" for name in voted_players])
        return f"**Đã Vote ({len(self.voted_users)}/{self.required_votes}):**\n{vote_text}"
    
    async def update_vote_message(self):
        """Cập nhật message hiển thị vote"""
        if not self.message or self.is_completed:
            return
            
        try:
            embed = discord.Embed(
                title="Bỏ phiếu bỏ qua pha thảo luận",
                description=(
                    f"Bỏ phiếu để chuyển thẳng sang pha voting.\n\n"
                    f"{self.get_vote_status_text()}\n\n"
                    f"Cần ít nhất {self.required_votes} phiếu (50% người chơi còn sống)."
                ),
                color=discord.Color.gold()
            )
            await self.message.edit(embed=embed, view=self)
        except Exception as e:
            logger.error(f"Lỗi cập nhật message vote: {str(e)}")
    
    async def start_vote(self):
        """Bắt đầu bỏ phiếu"""
        self.required_votes = self.calculate_required_votes()
        
        embed = discord.Embed(
            title="Bỏ phiếu bỏ qua pha thảo luận",
            description=(
                f"Bỏ phiếu để chuyển thẳng sang pha voting.\n\n"
                f"{self.get_vote_status_text()}\n\n"
                f"Cần ít nhất {self.required_votes} phiếu (50% người chơi còn sống)."
            ),
            color=discord.Color.gold()
        )
        
        try:
            await self.original_interaction.response.send_message(embed=embed, view=self)
            self.message = await self.original_interaction.original_response()
            
            # Bắt đầu timer cập nhật message mỗi 5 giây
            self.update_timer = asyncio.create_task(self._update_timer())
        except Exception as e:
            logger.error(f"Lỗi khởi tạo vote: {str(e)}")
            try:
                await self.original_interaction.followup.send("Có lỗi xảy ra khi bắt đầu bỏ phiếu.", ephemeral=True)
            except:
                pass
    
    async def _update_timer(self):
        """Timer để cập nhật message vote định kỳ"""
        try:
            while not self.is_completed:
                await asyncio.sleep(5)  # Cập nhật mỗi 5 giây
                await self.update_vote_message()
        except asyncio.CancelledError:
            logger.debug("Update timer đã bị hủy")
        except Exception as e:
            logger.error(f"Lỗi trong update timer: {str(e)}")
    
    async def check_votes(self, interaction: discord.Interaction):
        """Kiểm tra số vote và quyết định có skip phase không"""
        if len(self.voted_users) >= self.required_votes:
            # Đủ vote, dừng pha thảo luận
            self.is_completed = True
            if self.update_timer:
                self.update_timer.cancel()
            
            # Thông báo đã đủ vote để skip
            embed = discord.Embed(
                title="Đã bỏ qua pha thảo luận!",
                description=f"Đã nhận đủ {len(self.voted_users)}/{self.required_votes} phiếu đồng thuận. Chuyển sang pha voting!",
                color=discord.Color.green()
            )
            await self.message.edit(embed=embed, view=None)
            
            # Chuyển sang pha voting
            await asyncio.sleep(2)  # Đợi 2 giây để người chơi đọc thông báo
            self.disable_all_items()  # Vô hiệu hóa các nút
            await start_voting_phase(interaction, self.game_state)
            return True
        return False
    
    @discord.ui.button(label="Đồng ý bỏ qua", style=discord.ButtonStyle.primary, emoji="⏩")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Nút đồng ý bỏ qua pha thảo luận"""
        # Kiểm tra người vote có phải người chơi còn sống không
        user_id = interaction.user.id
        if user_id not in self.game_state["players"]:
            await interaction.response.send_message("Bạn không phải người chơi trong game!", ephemeral=True)
            return
        
        if self.game_state["players"][user_id]["status"] != "alive":
            await interaction.response.send_message("Chỉ người chơi còn sống mới có thể bỏ phiếu!", ephemeral=True)
            return
            
        if user_id in self.voted_users:
            # Rút lại vote nếu đã vote trước đó
            self.voted_users.remove(user_id)
            await interaction.response.send_message("Bạn đã rút lại vote của mình.", ephemeral=True)
        else:
            # Thêm vote mới
            self.voted_users.add(user_id)
            await interaction.response.send_message("Bạn đã vote để bỏ qua pha thảo luận.", ephemeral=True)
        
        await self.update_vote_message()
        await self.check_votes(interaction)
    
    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Nút hủy bỏ vote (chỉ dành cho người tạo vote)"""
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("Chỉ người bắt đầu vote mới có thể hủy!", ephemeral=True)
            return
            
        self.is_completed = True
        if self.update_timer:
            self.update_timer.cancel()
            
        embed = discord.Embed(
            title="Vote đã bị hủy",
            description="Người tạo vote đã hủy bỏ phiếu. Pha thảo luận vẫn tiếp tục.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def on_timeout(self):
        """Xử lý khi view timeout"""
        if self.is_completed:
            return
            
        self.is_completed = True
        if self.update_timer:
            self.update_timer.cancel()
            
        try:
            embed = discord.Embed(
                title="Vote đã hết hạn",
                description="Thời gian bỏ phiếu đã kết thúc. Không đủ vote để bỏ qua pha thảo luận.",
                color=discord.Color.grey()
            )
            await self.message.edit(embed=embed, view=None)
        except:
            pass