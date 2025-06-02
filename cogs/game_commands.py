# cogs/game_commands.py
# Module chứa các lệnh slash để quản lý game

import discord
from discord import app_commands
from discord.ext import commands
import logging
import traceback
import functools
import asyncio

from game_state import GameState
from views.setup_views import VoiceChannelView
from phases.end_game import reset_game_state, handle_game_end
from phases.voting import check_win_condition
from phases.morning import morning_phase
from phases.night import night_phase
from phases.voting import voting_phase
from utils.api_utils import update_member_cache

logger = logging.getLogger(__name__)

# Decorator để xử lý tương tác và lỗi một cách nhất quán
def handle_interaction(func):
    @functools.wraps(func)
    async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
        try:
            # Defer ngay lập tức để tránh timeout
            try:
                # Mặc định hiển thị dưới dạng công khai, trừ khi có yêu cầu khác
                ephemeral = getattr(func, 'ephemeral', False)
                await interaction.response.defer(ephemeral=ephemeral)
            except Exception as defer_error:
                logger.warning(f"Không thể defer tương tác: {str(defer_error)}")
                # Có thể do tương tác đã được xử lý, tiếp tục thực hiện hàm
            
            # Gọi hàm gốc
            return await func(self, interaction, *args, **kwargs)
        except Exception as e:
            # Log lỗi
            logger.error(f"Lỗi trong {func.__name__}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Gửi thông báo lỗi cho người dùng
            try:
                error_embed = discord.Embed(
                    title="❌ Lỗi", 
                    description=f"Lỗi khi thực hiện lệnh: {str(e)[:1500]}", 
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            except:
                if interaction.channel:
                    try:
                        await interaction.channel.send(
                            embed=discord.Embed(
                                title="❌ Lỗi",
                                description=f"Lỗi khi xử lý lệnh: {str(e)[:1500]}",
                                color=discord.Color.red()
                            )
                        )
                    except:
                        pass
            return None
    
    return wrapper

class GameCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.game_states = {}  # Lưu trữ trạng thái game theo guild_id
    
    def get_game_state(self, guild_id):
        """Lấy hoặc tạo mới game state cho guild"""
        if guild_id not in self.game_states:
            self.game_states[guild_id] = GameState(guild_id)
        return self.game_states[guild_id]
    
    @app_commands.command(name="start_game", description="Bắt đầu một game Ma Sói mới")
    @handle_interaction
    async def start_game(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.followup.send("Lỗi: Lệnh này phải được sử dụng trong server.", ephemeral=True)
            return
        
        guild_id = interaction.guild.id
        game_state = self.get_game_state(guild_id)
        
        if game_state.is_game_running:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Game đang chạy trên server này! Dùng `/reset_game` hoặc `/end_game` để kết thúc game hiện tại.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        game_state.temp_admin_id = interaction.user.id
        guild = interaction.guild
        
        # Tìm các kênh voice có người
        voice_channels = [ch for ch in guild.voice_channels if ch.members]
        
        if not voice_channels:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Không có kênh voice nào có người chơi! Mọi người cần tham gia một kênh voice trước.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Cập nhật member cache
        try:
            member_cache = await update_member_cache(guild, game_state)
            game_state.member_cache = member_cache
        except Exception as e:
            logger.error(f"Lỗi cập nhật member cache: {str(e)}")
            await interaction.followup.send(f"Lỗi cập nhật thông tin người chơi: {str(e)}", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎮 Bắt Đầu Game Ma Sói",
            description="Chọn kênh voice để bắt đầu game:",
            color=discord.Color.blue()
        )
        
        try:
            await interaction.followup.send(
                embed=embed,
                view=VoiceChannelView(guild, interaction.user.id, self.game_states)
            )
            logger.info(f"Start game command initiated by {interaction.user.id} in guild {guild_id}")
        except Exception as e:
            logger.error(f"Lỗi hiển thị VoiceChannelView: {str(e)}")
            await interaction.followup.send(f"Lỗi hiển thị màn hình chọn kênh voice: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="pause_game", description="Tạm dừng game")
    @handle_interaction
    async def pause_game(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.followup.send("Lỗi: Lệnh này phải được sử dụng trong server.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        # Kiểm tra xem game đã được khởi tạo chưa
        if guild_id not in self.game_states:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Chưa có game nào để tạm dừng trên server này!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
            
        game_state = self.game_states[guild_id]
        
        # Kiểm tra quyền hạn
        if not interaction.user.guild_permissions.administrator and interaction.user.id != game_state.temp_admin_id:
            embed = discord.Embed(
                title="❌ Quyền hạn không đủ",
                description="Chỉ admin server hoặc người tạo game có thể tạm dừng game.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        if not game_state.is_game_running:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Chưa có game nào để tạm dừng!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
            
        if game_state.is_game_paused:
            embed = discord.Embed(
                title="❓ Thông báo",
                description="Game đã đang tạm dừng rồi! Dùng `/resume_game` để tiếp tục.",
                color=discord.Color.yellow()
            )
            await interaction.followup.send(embed=embed)
            return
            
        game_state.is_game_paused = True
        logger.info(f"Game paused by {interaction.user.id} on guild {guild_id}")
        
        embed = discord.Embed(
            title="⏸️ Game Tạm Dừng",
            description="Game đã được tạm dừng! Dùng `/resume_game` để tiếp tục.\n\nPhase hiện tại: " + game_state.phase,
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="resume_game", description="Tiếp tục game")
    @handle_interaction
    async def resume_game(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.followup.send("Lỗi: Lệnh này phải được sử dụng trong server.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        # Kiểm tra xem game đã được khởi tạo chưa
        if guild_id not in self.game_states:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Chưa có game nào để tiếp tục trên server này!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
            
        game_state = self.game_states[guild_id]
        
        # Kiểm tra quyền hạn
        if not interaction.user.guild_permissions.administrator and interaction.user.id != game_state.temp_admin_id:
            embed = discord.Embed(
                title="❌ Quyền hạn không đủ",
                description="Chỉ admin server hoặc người tạo game có thể tiếp tục game.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
            
        if not game_state.is_game_running:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Chưa có game nào để tiếp tục!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
            
        if not game_state.is_game_paused:
            embed = discord.Embed(
                title="❓ Thông báo",
                description="Game không đang tạm dừng! Dùng `/pause_game` để tạm dừng.",
                color=discord.Color.yellow()
            )
            await interaction.followup.send(embed=embed)
            return
            
        game_state.is_game_paused = False
        logger.info(f"Game resumed by {interaction.user.id} on guild {guild_id}")
        
        embed = discord.Embed(
            title="▶️ Game Tiếp Tục",
            description="Game đã được tiếp tục! Trò chơi sẽ tiếp tục từ pha hiện tại.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)
        
        # Tiếp tục từ phase hiện tại
        try:
            if game_state.phase == "morning":
                await morning_phase(interaction, game_state)
            elif game_state.phase == "night":
                await night_phase(interaction, game_state)
            elif game_state.phase == "voting":
                await voting_phase(interaction, game_state)
        except Exception as e:
            logger.error(f"Error resuming game: {str(e)}")
            traceback.print_exc()
            await interaction.channel.send(f"Có lỗi khi tiếp tục game: {str(e)[:100]}...")
    
    @app_commands.command(name="reset_game", description="Khởi động lại game")
    @handle_interaction
    async def reset_game(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.followup.send("Lỗi: Lệnh này phải được sử dụng trong server.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        # Kiểm tra xem game đã được khởi tạo chưa
        if guild_id not in self.game_states:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Chưa có game nào để reset trên server này!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
            
        game_state = self.game_states[guild_id]
        
        # Kiểm tra quyền hạn
        if not interaction.user.guild_permissions.administrator and interaction.user.id != game_state.temp_admin_id:
            embed = discord.Embed(
                title="❌ Quyền hạn không đủ",
                description="Chỉ admin server hoặc người tạo game có thể reset game.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
            
        if not game_state.is_game_running:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Chưa có game nào để reset!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
            
        embed = discord.Embed(
            title="🔄 Reset Game",
            description="Đang reset game...",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)
        
        try:
            await reset_game_state(interaction, game_state)
        except Exception as e:
            logger.error(f"Lỗi khi reset game: {str(e)}")
            traceback.print_exc()
            await interaction.channel.send(f"Lỗi khi reset game: {str(e)[:100]}...")
    
    @app_commands.command(name="end_game", description="Kết thúc game")
    @handle_interaction
    async def end_game(self, interaction: discord.Interaction):
        if not interaction.guild:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Không thể xác định server! Lệnh này phải được sử dụng trong server.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        guild_id = interaction.guild.id
        # Kiểm tra đúng cấu trúc của self.game_states
        if not hasattr(self, 'game_states') or guild_id not in self.game_states:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Chưa có game nào để kết thúc trên server này!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
            
        game_state = self.game_states[guild_id]
        
        # Kiểm tra quyền hạn
        if not interaction.user.guild_permissions.administrator and interaction.user.id != game_state.temp_admin_id:
            embed = discord.Embed(
                title="❌ Quyền hạn không đủ",
                description="Chỉ admin server hoặc người tạo game có thể kết thúc game.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
            
        # Kiểm tra cả hai dạng truy cập trạng thái game
        is_running = False
        try:
            is_running = game_state.is_game_running
        except AttributeError:
            is_running = game_state.get("is_game_running", False)
            
        if not is_running:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Chưa có game nào để kết thúc!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
            
        embed = discord.Embed(
            title="🛑 Kết Thúc Game",
            description="Đang kết thúc game...",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)
        
        try:
            await handle_game_end(interaction, game_state)
        except Exception as e:
            logger.error(f"Lỗi khi kết thúc game: {str(e)}")
            traceback.print_exc()
            
            # Đảm bảo người dùng luôn nhận được phản hồi
            try:
                await interaction.followup.send(f"Lỗi khi kết thúc game: {str(e)[:100]}...", ephemeral=True)
            except:
                if interaction.channel:
                    await interaction.channel.send(f"Lỗi khi kết thúc game: {str(e)[:100]}...")
    
    @app_commands.command(name="status", description="Xem trạng thái game hiện tại")
    @handle_interaction
    async def status(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.followup.send("Lỗi: Lệnh này phải được sử dụng trong server.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        if guild_id not in self.game_states:
            embed = discord.Embed(
                title="Trạng thái Bot Ma Sói",
                description="Chưa có game nào đang chạy trên server này.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
            
        game_state = self.game_states[guild_id]
        embed = discord.Embed(title="Trạng thái Bot Ma Sói", color=discord.Color.green())
        
        # Thông tin cơ bản
        embed.add_field(name="Game đang chạy", value=str(game_state.is_game_running), inline=False)
        embed.add_field(name="Game đang tạm dừng", value=str(game_state.is_game_paused), inline=False)
        embed.add_field(name="Pha hiện tại", value=game_state.phase, inline=False)
        
        # Thông tin người chơi
        try:
            alive_count = sum(1 for data in game_state.players.values() if data["status"] in ["alive", "wounded"])
            dead_count = sum(1 for data in game_state.players.values() if data["status"] == "dead")
            embed.add_field(name="Người chơi", value=f"Còn sống: {alive_count}\nĐã chết: {dead_count}", inline=False)
        except Exception as e:
            embed.add_field(name="Người chơi", value=f"Lỗi khi lấy thông tin người chơi: {str(e)[:100]}", inline=False)
        
        # Thống kê game
        embed.add_field(name="Số đêm đã qua", value=str(game_state.night_count), inline=True)
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="check_mute", description="Kiểm tra tình trạng mic")
    @handle_interaction
    async def check_mute(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.followup.send("Lỗi: Lệnh này phải được sử dụng trong server.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        if guild_id not in self.game_states:
            embed = discord.Embed(
                title="❌ Lỗi",
                description="Chưa có game nào đang chạy trên server này!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
            
        game_state = self.game_states[guild_id]
        muted_players = []
        
        for user_id in game_state.players:
            member = game_state.member_cache.get(user_id)
            if member and member.voice and member.voice.mute:
                muted_players.append(f"{member.display_name} (ID: {user_id})")
        
        embed = discord.Embed(
            title="🎙️ Kiểm Tra Mic",
            color=discord.Color.blue()
        )
        
        if muted_players:
            embed.description = "Những người chơi đang bị mute:"
            embed.add_field(name="Người bị mute", value="\n".join(muted_players), inline=False)
        else:
            embed.description = "Không có người chơi nào đang bị mute."
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    try:
        await bot.add_cog(GameCommands(bot))
        logger.info("Đã thêm cog GameCommands")
        
        # Không đồng bộ lệnh ở đây - sẽ được thực hiện trong on_ready
        # Bỏ dòng: await bot.tree.sync()
    except Exception as e:
        logger.error(f"Lỗi khi thêm cog GameCommands: {str(e)}")
        traceback.print_exc()