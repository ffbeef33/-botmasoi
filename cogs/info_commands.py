# cogs/info_commands.py
# Module chứa các lệnh slash để hiển thị thông tin

import discord
from discord import app_commands
from discord.ext import commands
import logging

from constants import ROLES, VILLAGER_ROLES, WEREWOLF_ROLES, ROLE_DESCRIPTIONS, ROLE_LINKS, BOT_VERSION
from db import get_leaderboard

logger = logging.getLogger(__name__)

class InfoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="help_masoi", description="Hiển thị hướng dẫn chơi Ma Sói")
    @app_commands.describe(topic="Chủ đề cần xem hướng dẫn")
    @app_commands.choices(topic=[
        app_commands.Choice(name="Tổng quan", value="overview"),
        app_commands.Choice(name="Lệnh bot", value="commands"),
        app_commands.Choice(name="Vai trò", value="roles"),
        app_commands.Choice(name="Luật chơi", value="rules")
    ])
    async def help_masoi(self, interaction: discord.Interaction, topic: str = "overview"):
        await interaction.response.defer()
        
        if topic == "overview":
            embed = discord.Embed(
                title="🐺 Hướng Dẫn Bot Ma Sói DeWolfVie",
                description=(
                    "Bot Ma Sói DeWolfVie giúp quản lý trò chơi Ma Sói trên Discord với giao diện đơn giản và dễ sử dụng."
                    "\n\nSử dụng `/help_masoi topic:` để xem hướng dẫn chi tiết về từng chủ đề cụ thể."
                ),
                color=discord.Color.blue()
            )
            embed.add_field(
                name="🎮 Bắt Đầu Game",
                value="Dùng `/start_game` để bắt đầu một game mới. Bạn sẽ cần chọn kênh voice, số lượng và danh sách người chơi, cũng như phân chia vai trò.",
                inline=False
            )
            embed.add_field(
                name="🏆 Các Chủ Đề Hướng Dẫn",
                value=(
                    "• **commands**: Danh sách và chi tiết các lệnh\n"
                    "• **roles**: Thông tin về các vai trò trong game\n"
                    "• **rules**: Luật chơi và cách thức hoạt động"
                ),
                inline=False
            )
        elif topic == "commands":
            embed = self._create_commands_help_embed()
        elif topic == "roles":
            embed = self._create_roles_help_embed()
        elif topic == "rules":
            embed = self._create_rules_help_embed()
        else:
            embed = discord.Embed(
                title="❌ Chủ đề không hợp lệ",
                description="Vui lòng chọn một chủ đề hợp lệ: overview, commands, roles, hoặc rules.",
                color=discord.Color.red()
            )
        
        embed.set_footer(text=BOT_VERSION)
        await interaction.followup.send(embed=embed)
    
    def _create_commands_help_embed(self):
        """Tạo embed chứa thông tin về các lệnh"""
        embed = discord.Embed(
            title="📝 Danh Sách Lệnh Bot Ma Sói",
            description="Tất cả các lệnh bắt đầu bằng `/`",
            color=discord.Color.blue()
        )
        
        commands = [
            {"name": "start_game", "desc": "Bắt đầu game mới. Cho phép chọn kênh voice, số lượng người chơi, và vai trò."},
            {"name": "pause_game", "desc": "Tạm dừng game hiện tại. Các pha sẽ dừng lại, người chơi không thể thực hiện hành động."},
            {"name": "resume_game", "desc": "Tiếp tục game đã bị tạm dừng."},
            {"name": "reset_game", "desc": "Reset lại game hiện tại và bắt đầu lại với cùng người chơi và vai trò (xáo trộn)."},
            {"name": "end_game", "desc": "Kết thúc game hiện tại và dọn dẹp tài nguyên."},
            {"name": "roles_list", "desc": "Xem danh sách tất cả vai trò trong game."},
            {"name": "roles", "desc": "Xem chi tiết về một vai trò cụ thể."},
            {"name": "status", "desc": "Kiểm tra trạng thái hiện tại của game."},
            {"name": "leaderboard", "desc": "Hiển thị bảng xếp hạng người chơi."},
            {"name": "check_mute", "desc": "Kiểm tra người chơi nào đang bị mute."},
            {"name": "help_masoi", "desc": "Hiển thị hướng dẫn chi tiết về chơi game Ma Sói."}
        ]
        
        for cmd in commands:
            embed.add_field(name=f"/{cmd['name']}", value=cmd['desc'], inline=False)
            
        return embed
    
    def _create_roles_help_embed(self):
        """Tạo embed chứa thông tin về các vai trò"""
        embed = discord.Embed(
            title="👤 Vai Trò Trong Ma Sói",
            description="Game Ma Sói có hai phe chính: Phe Dân và Phe Sói. Mỗi vai trò có khả năng đặc biệt riêng.",
            color=discord.Color.blue()
        )
        
        # Vai trò phe Dân
        villager_roles_desc = []
        for role in VILLAGER_ROLES:
            desc = ROLE_DESCRIPTIONS.get(role, "Không có mô tả")
            villager_roles_desc.append(f"**{role}**: {desc[:100]}...")
            
        embed.add_field(name="🟢 Phe Dân", value="\n\n".join(villager_roles_desc), inline=False)
        
        # Vai trò phe Sói
        werewolf_roles_desc = []
        for role in WEREWOLF_ROLES:
            desc = ROLE_DESCRIPTIONS.get(role, "Không có mô tả")
            werewolf_roles_desc.append(f"**{role}**: {desc[:100]}...")
            
        embed.add_field(name="🔴 Phe Sói", value="\n\n".join(werewolf_roles_desc), inline=False)
        
        embed.add_field(
            name="Xem Chi Tiết",
            value="Sử dụng lệnh `/roles <tên vai trò>` để xem thông tin chi tiết về một vai trò cụ thể.",
            inline=False
        )
        
        embed.set_footer(text="Tham khảo thêm tại: https://www.dewolfvie.net/vn/chucnang")
        return embed
    
    def _create_rules_help_embed(self):
        """Tạo embed chứa luật chơi"""
        embed = discord.Embed(
            title="📜 Luật Chơi Ma Sói",
            description="Game Ma Sói gồm các pha chính: Ban Ngày và Ban Đêm. Mỗi pha có các hoạt động khác nhau.",
            color=discord.Color.blue()
        )
        
        # Mục tiêu game
        embed.add_field(
            name="🎯 Mục Tiêu",
            value=(
                "• **Phe Dân**: Tiêu diệt tất cả Ma Sói\n"
                "• **Phe Sói**: Tiêu diệt đủ Dân làng để số Sói lớn hơn hoặc bằng số Dân"
            ),
            inline=False
        )
        
        # Pha Ban Ngày
        embed.add_field(
            name="☀️ Pha Ban Ngày",
            value=(
                "1. Thảo luận về những người chết đêm qua và các manh mối\n"
                "2. Bỏ phiếu treo cổ một người (hoặc không treo ai)\n"
                "3. Người bị bỏ phiếu nhiều nhất sẽ bị treo cổ và tiết lộ vai trò"
            ),
            inline=False
        )
        
        # Pha Ban Đêm
        embed.add_field(
            name="🌙 Pha Ban Đêm",
            value=(
                "1. Mỗi người chơi được chuyển vào phòng riêng\n"
                "2. Các vai trò đặc biệt thực hiện hành động\n"
                "3. Các vai không có hành động đêm phải giải toán để được bỏ phiếu\n"
                "4. Kết thúc đêm, những người bị giết sẽ được công bố"
            ),
            inline=False
        )
        
        # Các lưu ý quan trọng
        embed.add_field(
            name="⚠️ Lưu Ý Quan Trọng",
            value=(
                "• Người chết không được nói chuyện với người sống về game\n"
                "• Bot sẽ di chuyển và quản lý mic tự động\n"
                "• Phù Thủy, Thợ Săn, Sói Ám Sát chỉ có một lần sử dụng khả năng đặc biệt trong game\n"
                "• Người chết có thể nói chuyện với nhau trong kênh dead-chat\n"
                "• Sói có thể thảo luận trong kênh wolf-chat vào ban đêm"
            ),
            inline=False
        )
        
        return embed
    
    @app_commands.command(name="roles_list", description="Hiển thị danh sách vai trò trong game")
    async def roles_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        embed = discord.Embed(
            title="Danh Sách Vai Trò Ma Sói",
            description="Danh sách các vai trò trong game, phân chia theo phe. Chi tiết về các vai trò có thể xem tại [đây](https://www.dewolfvie.net/vn/chucnang).",
            color=discord.Color.blue()
        )

        # Danh sách vai trò Phe Dân
        villager_roles_list = "\n".join([f"**{role}**" for role in VILLAGER_ROLES])
        embed.add_field(name="🟢 Phe Dân", value=villager_roles_list, inline=False)

        # Danh sách vai trò Phe Sói
        werewolf_roles_list = "\n".join([f"**{role}**" for role in WEREWOLF_ROLES])
        embed.add_field(name="🔴 Phe Sói", value=werewolf_roles_list, inline=False)

        embed.set_footer(text=BOT_VERSION)
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="roles", description="Xem mô tả chi tiết của một vai trò cụ thể")
    @app_commands.describe(role="Chọn vai trò để xem chi tiết")
    @app_commands.choices(role=[app_commands.Choice(name=role, value=role) for role in ROLES])
    async def roles(self, interaction: discord.Interaction, role: str):
        await interaction.response.defer()
        
        if role not in ROLE_LINKS:
            await interaction.followup.send("Vai trò không hợp lệ!")
            return
            
        embed = discord.Embed(
            title=f"Chi Tiết Vai Trò: {role}",
            description=ROLE_DESCRIPTIONS.get(role, "Không có mô tả"),
            color=discord.Color.blue()
        )
        
        # Xác định phe
        team = "Phe Sói" if role in WEREWOLF_ROLES else "Phe Dân"
        embed.add_field(name="Phe", value=team, inline=True)
        
        # Thêm link tham khảo
        link = ROLE_LINKS[role]
        embed.add_field(name="Tham Khảo", value=f"[Chi tiết vai trò]({link})", inline=True)
        
        embed.set_footer(text=BOT_VERSION)
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="leaderboard", description="Hiển thị bảng vinh danh")
    @app_commands.describe(scope="Phạm vi hiển thị", limit="Số lượng người hiển thị")
    @app_commands.choices(scope=[
        app_commands.Choice(name="Server này", value="server"),
        app_commands.Choice(name="Tất cả server", value="global")
    ])
    async def leaderboard(self, interaction: discord.Interaction, 
                        scope: str = "server", 
                        limit: app_commands.Range[int, 5, 20] = 10):
        await interaction.response.defer()
        
        guild_id = interaction.guild.id
        
        try:
            if scope == "server":
                records = await get_leaderboard(guild_id, limit)
                title = f"🏆 Bảng xếp hạng - Top {limit} (Server: {interaction.guild.name})"
            else:
                records = await get_leaderboard(None, limit)
                title = f"🏆 Bảng xếp hạng Toàn Cầu - Top {limit}"
            
            if not records:
                await interaction.followup.send("Chưa có dữ liệu leaderboard.")
                return
            
            embed = discord.Embed(
                title=title,
                color=discord.Color.gold()
            )
            
            for i, record in enumerate(records, start=1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                embed.add_field(
                    name=f"{medal} {record['player_name']}",
                    value=f"Điểm: **{record['score']}** | Số game: {record.get('games_played', 'N/A')}",
                    inline=False
                )
            
            embed.set_footer(text=BOT_VERSION)
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error fetching leaderboard: {e}")
            await interaction.followup.send(f"Lỗi khi lấy dữ liệu leaderboard: {str(e)[:100]}...")

async def setup(bot):
    await bot.add_cog(InfoCommands(bot))