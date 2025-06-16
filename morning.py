# phases/morning.py
# Module quản lý các pha sáng trong game

import discord
import logging
import asyncio
from typing import Dict, List, Optional

from constants import GIF_URLS, AUDIO_FILES
from utils.api_utils import play_audio, countdown, safe_send_message
from phases.voting import voting_phase

logger = logging.getLogger(__name__)

async def morning_phase(interaction: discord.Interaction, game_state):
    """
    Xử lý pha sáng trong game
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    if not game_state["is_game_running"] or game_state["is_game_paused"]:
        logger.info("morning_phase: Game stopped or paused, skipping")
        return
        
    # Đặt phase sớm để có thể kiểm tra ở các hàm khác
    game_state["phase"] = "morning"
    game_state["votes"].clear()  # Xóa phiếu bầu từ ngày trước
    
    # Reset trạng thái vote skip nếu có
    game_state["skip_vote_active"] = False
    
    # Lưu lại các thông tin quan trọng cho pha hiện tại
    game_state["current_phase_start_time"] = asyncio.get_event_loop().time()
    
    # Lấy và kiểm tra các kênh cần thiết
    main_channel = interaction.client.get_channel(game_state["voice_channel_id"])
    text_channel = game_state.get("text_channel")
    
    if not text_channel:
        logger.error("morning_phase: text_channel is None, cannot proceed")
        return
    
    # Xử lý người bị nguyền từ đêm trước
    if game_state["demon_werewolf_cursed_player"] is not None:
        await handle_cursed_player(interaction, game_state)
    
    try:
        # Thiết lập quyền chat cho người còn sống
        guild = interaction.guild
        villager_role = guild.get_role(game_state["villager_role_id"])
        if text_channel and villager_role:
            # Thiết lập quyền chat một lần cho toàn bộ channel thay vì từng người một
            await text_channel.set_permissions(guild.default_role, send_messages=True)
            await text_channel.set_permissions(villager_role, send_messages=True)
            
        # Di chuyển tất cả người chơi về main channel trong một coroutine
        move_tasks = []
        for user_id in game_state["players"]:
            member = game_state["member_cache"].get(user_id)
            if member and member.voice and member.voice.channel:
                move_tasks.append(member.move_to(main_channel))
                
        if move_tasks:
            await asyncio.gather(*move_tasks)
            
        # Hiệu ứng và thông báo
        embed = discord.Embed(
            title="☀️ Bình Minh",
            description=("Mọi người thức dậy! Thảo luận trong " + 
                        ("30" if game_state["is_first_day"] else "120") + 
                        " giây trước khi bỏ phiếu."),
            color=discord.Color.gold()
        )
        embed.set_image(url=GIF_URLS["morning"])
        await text_channel.send(embed=embed)
        
        # Phát âm thanh không đồng bộ để không chặn tiến trình
        asyncio.create_task(play_audio(AUDIO_FILES["morning"], game_state["voice_connection"]))
        
        # Đếm ngược thời gian thảo luận
        from config import TIMINGS
        discussion_time = TIMINGS["first_day"] if game_state["is_first_day"] else TIMINGS["morning_discussion"]
        await countdown(text_channel, discussion_time, "thảo luận", game_state)
        
        if not game_state["is_game_running"] or game_state["is_game_paused"]:
            return
            
        # Xử lý ngày đầu tiên
        if game_state["is_first_day"]:
            game_state["is_first_day"] = False
            from phases.night import night_phase
            await night_phase(interaction, game_state)
            return
            
        # Tiếp tục với pha bỏ phiếu
        await voting_phase(interaction, game_state)
        
    except Exception as e:
        logger.error(f"Error in morning_phase: {str(e)}")
        import traceback
        traceback.print_exc()
        if text_channel:
            await text_channel.send(f"Đã xảy ra lỗi trong pha sáng: {str(e)[:100]}...")

async def handle_cursed_player(interaction: discord.Interaction, game_state):
    """
    Xử lý người chơi đã bị nguyền bởi Sói Quỷ
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    cursed_id = game_state["demon_werewolf_cursed_player"]
    if cursed_id in game_state["players"] and game_state["players"][cursed_id]["status"] in ["alive", "wounded"]:
        # Lưu vai trò cũ để thông báo
        old_role = game_state["players"][cursed_id]["role"]
        
        # Chuyển đổi vai trò thành Werewolf
        game_state["players"][cursed_id]["role"] = "Werewolf"
        
        member = game_state["member_cache"].get(cursed_id)
        if member:
            # Thêm Discord Werewolf role
            werewolf_role = interaction.guild.get_role(game_state["werewolf_role_id"])
            if werewolf_role and werewolf_role not in member.roles:
                await member.add_roles(werewolf_role)
            
            # Thông báo cho người bị nguyền
            embed = discord.Embed(
                title="🌙 Lời Nguyền Của Sói Quỷ",
                description=(
                    "Bạn đã bị nguyền và trở thành **Sói**!\n\n"
                    f"Vai trò cũ: **{old_role}**\n"
                    "Vai trò mới: **Werewolf**\n\n"
                    "Bạn sẽ thức dậy cùng bầy Sói trong pha đêm và mất chức năng cũ."
                ),
                color=discord.Color.dark_red()
            )
            await member.send(embed=embed)
            
            # Cấp quyền truy cập wolf-chat
            if game_state["wolf_channel"]:
                await game_state["wolf_channel"].set_permissions(member, read_messages=True, send_messages=True)
                
                # Thông báo trong wolf-chat
                wolf_embed = discord.Embed(
                    title="🐺 Thành Viên Mới!",
                    description=f"**{member.display_name}** đã bị nguyền và trở thành Sói!\nVai trò cũ: **{old_role}**",
                    color=discord.Color.dark_red()
                )
                await game_state["wolf_channel"].send(embed=wolf_embed)
        
        # Reset biến nguyền sau khi xử lý
        logger.info(f"Player {cursed_id} transformed from {old_role} into Werewolf due to curse")
        game_state["demon_werewolf_cursed_player"] = None
