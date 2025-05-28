# main.py
# Điểm khởi đầu của ứng dụng bot

import os
import discord
import logging
import sys
import traceback
import asyncio
from discord.ext import commands

from config import DISCORD_TOKEN, logger
from db import init_database

# Khởi tạo bot với các intents cần thiết
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

@bot.event
async def on_ready():
    """Event được gọi khi bot đăng nhập thành công"""
    logger.info(f"Bot đã sẵn sàng với tên {bot.user}")
    print(f"Bot đã sẵn sàng với tên {bot.user}")
    
    # Hiển thị thông tin commands trước khi sync
    print("Commands in tree before sync:")
    for command in bot.tree.get_commands():
        print(f"- {command.name}")
        
    # Khởi tạo cơ sở dữ liệu nếu cần
    init_database()
    logger.info("Database initialized")
    
    # Đồng bộ commands
    await bot.tree.sync()
    logger.info("Command tree synced")
    
    # Hiển thị thông tin kết nối
    guild_count = len(bot.guilds)
    print(f"Bot đang hoạt động trên {guild_count} server")
    logger.info(f"Bot đang hoạt động trên {guild_count} server")
    
    # Thiết lập trạng thái
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing,
            name="Ma Sói | /help_masoi"
        )
    )

@bot.event
async def on_guild_join(guild):
    """Event được gọi khi bot tham gia server mới"""
    logger.info(f"Bot đã tham gia guild mới: {guild.name} (ID: {guild.id})")
    
    # Tìm kênh thích hợp để gửi thông báo
    channel = None
    for ch in guild.text_channels:
        if ch.permissions_for(guild.me).send_messages:
            channel = ch
            break
    
    if channel:
        embed = discord.Embed(
            title="🐺 Chào Mừng Đến Với Bot Ma Sói DeWolfVie!",
            description=(
                "Cảm ơn đã thêm bot Ma Sói vào server của bạn!\n\n"
                "• Sử dụng `/help_masoi` để xem hướng dẫn sử dụng\n"
                "• Sử dụng `/start_game` để bắt đầu một game mới\n"
                "• Sử dụng `/roles_list` để xem danh sách vai trò\n\n"
                "Chúc bạn và server có những trải nghiệm game vui vẻ!"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="DeWolfVie ver 5.15")
        await channel.send(embed=embed)

@bot.event
async def on_voice_state_update(member, before, after):
    """Event được gọi khi trạng thái voice của người dùng thay đổi"""
    # Nếu bot đang trong kênh voice và không còn người nào khác, bot sẽ rời kênh
    if before.channel and bot.user in before.channel.members:
        # Đếm số người trong kênh (trừ bot)
        human_count = sum(1 for m in before.channel.members if not m.bot)
        
        if human_count == 0:
            # Tìm voice client trong kênh này
            for vc in bot.voice_clients:
                if vc.channel == before.channel:
                    logger.info(f"Disconnecting from empty voice channel: {before.channel.name}")
                    await vc.disconnect()
                    break

@bot.event
async def on_command_error(ctx, error):
    """Xử lý lỗi commands cũ (prefix commands)"""
    if isinstance(error, commands.CommandNotFound):
        return
        
    logger.error(f"Command error: {str(error)}")
    await ctx.send(f"Lỗi: {str(error)}")

@bot.event
async def on_app_command_error(interaction: discord.Interaction, error):
    """Xử lý lỗi app commands (slash commands)"""
    error_message = f"Lỗi khi thực hiện lệnh: {str(error)}"
    logger.error(f"App command error: {str(error)}")
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
    
    if interaction.response.is_done():
        await interaction.followup.send(error_message, ephemeral=True)
    else:
        await interaction.response.send_message(error_message, ephemeral=True)

async def load_extensions():
    """Load tất cả các extensions/cogs cho bot"""
    extensions = [
        'cogs.game_commands',
        'cogs.info_commands',
    ]
    
    for extension in extensions:
        try:
            await bot.load_extension(extension)
            logger.info(f"Đã tải extension: {extension}")
        except Exception as e:
            logger.error(f"Lỗi khi tải extension {extension}: {str(e)}")
            traceback.print_exc()

async def start_bot():
    """Hàm khởi động bot an toàn"""
    try:
        # Tải các extensions trước
        await load_extensions()
        
        # Chạy bot
        await bot.start(DISCORD_TOKEN)
        return True
    except discord.errors.LoginFailure:
        logger.critical("Bot không thể đăng nhập. Token không hợp lệ!")
        print("Error: Invalid token. Bot couldn't login.")
        return False
    except Exception as e:
        logger.critical(f"Lỗi không xác định khi khởi động bot: {str(e)}")
        print(f"Error starting bot: {str(e)}")
        traceback.print_exc()
        return False

# Điểm khởi đầu chương trình
if __name__ == "__main__":
    print("Starting Ma Sói bot...")
    
    # Setup event loop và chạy bot
    try:
        # Cài đặt policy đặc biệt cho Windows nếu cần
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        # Chạy bot trong event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        success = loop.run_until_complete(start_bot())
        
        if not success:
            print("Bot failed to start properly. Check logs for details.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("Bot shutdown by user")
    except Exception as e:
        print(f"Unhandled error: {str(e)}")
        logger.critical(f"Unhandled error: {str(e)}")
        traceback.print_exc()
        sys.exit(1)