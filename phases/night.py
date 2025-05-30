# phases/night.py
# Module quản lý pha đêm trong game

import discord
import logging
import asyncio
from typing import Dict, List, Optional

from constants import GIF_URLS, AUDIO_FILES, VILLAGER_ROLES, WEREWOLF_ROLES, NO_NIGHT_ACTION_ROLES
from utils.api_utils import play_audio, countdown, safe_send_message, generate_math_problem
from utils.role_utils import handle_player_death, get_player_team

logger = logging.getLogger(__name__)

async def night_phase(interaction: discord.Interaction, game_state):
    """
    Xử lý pha đêm trong game
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    if not game_state["is_game_running"] or game_state["is_game_paused"]:
        logger.info("night_phase: Game stopped or paused, skipping night phase")
        return
        
    # Tăng số đêm và đặt phase
    game_state["phase"] = "night"
    game_state["night_count"] += 1
    
    # Gọi các hàm riêng biệt cho từng chức năng
    await setup_night_permissions(interaction, game_state)  # Thiết lập quyền hạn đêm
    await move_players_to_private_rooms(interaction, game_state)  # Di chuyển người chơi vào phòng riêng
    await send_night_announcement(interaction, game_state)  # Gửi thông báo đêm
    
    # Reset các biến theo dõi hành động đêm
    await reset_night_actions(game_state)
    
    # Gửi hành động đêm cho từng vai trò
    await send_werewolf_actions(interaction, game_state)
    await send_special_role_actions(interaction, game_state)
    await send_math_problems(interaction, game_state)
    
    # Đếm ngược thời gian hành động đêm
    from config import TIMINGS
    await countdown(game_state["text_channel"], TIMINGS["night_action"], "hành động đêm", game_state)
    if not game_state["is_game_running"] or game_state["is_game_paused"]:
        return
        
    # Xử lý hành động Phù Thủy riêng biệt
    await process_witch_actions(interaction, game_state)
    
    # Xử lý kết quả của tất cả hành động đêm
    dead_players = await process_night_action_results(interaction, game_state)
    
    # Thông báo người chết
    await announce_night_deaths(interaction, game_state, dead_players)
    
    # Kiểm tra điều kiện thắng
    from phases.voting import check_win_condition
    if await check_win_condition(interaction, game_state):
        return
        
    # Khôi phục quyền hạn chat và chuyển sang pha sáng
    await restore_permissions(interaction, game_state)
    from phases.morning import morning_phase
    await morning_phase(interaction, game_state)

async def setup_night_permissions(interaction: discord.Interaction, game_state):
    """
    Thiết lập quyền hạn cho pha đêm
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    text_channel = game_state["text_channel"]
    guild = interaction.guild
    villager_role = guild.get_role(game_state["villager_role_id"])
    
    # Thiết lập quyền cho kênh text: cấm chat cho @everyone và vai trò Dân Làng
    if text_channel and villager_role:
        try:
            await text_channel.set_permissions(guild.default_role, send_messages=False)
            await text_channel.set_permissions(villager_role, send_messages=False)
            logger.info("Set text channel permissions for night phase")
        except Exception as e:
            logger.error(f"Failed to set text channel permissions: {str(e)}")
            await text_channel.send(f"Lỗi: Không thể chặn chat trong kênh text: {str(e)}")

async def move_players_to_private_rooms(interaction: discord.Interaction, game_state):
    """
    Di chuyển người chơi vào các phòng riêng
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    # Di chuyển người chơi vào kênh riêng
    move_tasks = []
    for user_id, data in game_state["players"].items():
        if data["status"] in ["alive", "wounded"]:
            if user_id in game_state["player_channels"]:
                member = game_state["member_cache"].get(user_id)
                if member and member.voice:
                    temp_channel = game_state["player_channels"][user_id]
                    move_tasks.append(member.move_to(temp_channel))
    
    # Thực hiện tất cả task di chuyển cùng lúc
    if move_tasks:
        await asyncio.gather(*move_tasks, return_exceptions=True)

async def send_night_announcement(interaction: discord.Interaction, game_state):
    """
    Gửi thông báo pha đêm
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    text_channel = game_state["text_channel"]
    if not text_channel:
        return
        
    night_embed = discord.Embed(
        title="🌙 Pha Đêm Bắt Đầu",
        description="Mọi người đã bị cô lập để thực hiện hành động đêm!",
        color=discord.Color.dark_blue()
    )
    night_embed.set_image(url=GIF_URLS["night"])
    await text_channel.send(embed=night_embed)
    
    # Phát âm thanh đêm
    await play_audio(AUDIO_FILES["night"], game_state["voice_connection"])

async def reset_night_actions(game_state):
    """
    Reset các biến theo dõi hành động đêm
    
    Args:
        game_state (dict): Trạng thái game hiện tại
    """
    game_state["werewolf_target_id"] = None
    game_state["witch_target_save_id"] = None
    game_state["witch_target_kill_id"] = None
    game_state["witch_action_save"] = False
    game_state["witch_action_kill"] = False
    game_state["hunter_target_id"] = None
    game_state["explorer_target_id"] = None
    game_state["math_problems"] = {}
    game_state["math_results"] = {}
    game_state["demon_werewolf_cursed_this_night"] = False    
    game_state["seer_target_id"] = None
    game_state["protected_player_id"] = None
    
    # Cập nhật hiệu ứng Illusionist
    if game_state["illusionist_scanned"] and game_state["night_count"] == game_state["illusionist_effect_night"]:
        game_state["illusionist_effect_active"] = True
    else:
        game_state["illusionist_effect_active"] = False
        
    # Kiểm tra nếu có Sói chết để kích hoạt Sói Quỷ
    werewolf_dead = any(
        data["role"] in WEREWOLF_ROLES and data["status"] == "dead" 
        for data in game_state["players"].values()
    )
    
    if werewolf_dead and not game_state["demon_werewolf_activated"]:
        game_state["demon_werewolf_activated"] = True
        for user_id, data in game_state["players"].items():
            if data["role"] == "Demon Werewolf" and data["status"] in ["alive", "wounded"]:
                member = game_state["member_cache"].get(user_id)
                if member:
                    await member.send("Một Sói đã chết! Bạn có thể nguyền một người chơi trong đêm này hoặc các đêm tiếp theo.")

async def send_werewolf_actions(interaction: discord.Interaction, game_state):
    """
    Gửi action view cho phe Sói
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    wolf_channel = game_state["wolf_channel"]
    if not wolf_channel:
        logger.error("Wolf channel not found")
        return
        
    # Lấy danh sách người chơi còn sống
    from phases.voting import get_alive_players
    alive_players = await get_alive_players(interaction, game_state)
    
    # Gửi thông báo chung cho phe Sói trong wolf-chat
    from views.action_views import NightActionView
    try:
        embed = discord.Embed(
            title="🐺 Đến Lượt Phe Sói",
            description="Cùng thảo luận và chọn một người để giết!",
            color=discord.Color.dark_red()
        )
        await wolf_channel.send(
            embed=embed,
            view=NightActionView("Werewolf", alive_players, game_state, 40)
        )
    except Exception as e:
        logger.error(f"Error sending werewolf action view: {str(e)}")

async def send_special_role_actions(interaction: discord.Interaction, game_state):
    """
    Gửi action view cho các vai trò đặc biệt
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    # Lấy danh sách người chơi còn sống
    from phases.voting import get_alive_players
    alive_players = await get_alive_players(interaction, game_state)
    
    # Import các view cần thiết
    from views.action_views import NightActionView, DetectiveSelectView, AssassinActionView
    
    # Xử lý hành động đêm cho các vai trò khác
    for user_id, data in game_state["players"].items():
        if data["status"] not in ["alive", "wounded"] or data["role"] in NO_NIGHT_ACTION_ROLES:
            continue
            
        member = game_state["member_cache"].get(user_id)
        if not member or member not in alive_players:
            continue
            
        try:
            if data["role"] == "Seer":
                embed = discord.Embed(
                    title="🔮 Hành Động Tiên Tri",
                    description="Chọn một người để soi phe:",
                    color=discord.Color.purple()
                )
                await member.send(embed=embed, view=NightActionView("Seer", alive_players, game_state, 40))
                
            elif data["role"] == "Guard":
                embed = discord.Embed(
                    title="🛡️ Hành Động Bảo Vệ",
                    description="Chọn một người để bảo vệ:",
                    color=discord.Color.blue()
                )
                await member.send(embed=embed, view=NightActionView("Guard", alive_players, game_state, 40))
                
            elif data["role"] == "Hunter" and game_state["hunter_has_power"]:
                embed = discord.Embed(
                    title="🏹 Hành Động Thợ Săn",
                    description="Chọn một người để giết (chỉ một lần duy nhất):",
                    color=discord.Color.dark_orange()
                )
                await member.send(embed=embed, view=NightActionView("Hunter", alive_players, game_state, 40))
                
            elif data["role"] == "Explorer" and game_state["night_count"] >= 2 and game_state.get("explorer_can_act", False):
                embed = discord.Embed(
                    title="🧭 Hành Động Người Khám Phá",
                    description="Chọn một người để khám phá. Chọn đúng Sói, Sói chết; chọn sai, bạn chết:",
                    color=discord.Color.gold()
                )
                await member.send(embed=embed, view=NightActionView("Explorer", alive_players, game_state, 40))
                
            elif data["role"] == "Demon Werewolf":
                if game_state["demon_werewolf_activated"] and not game_state["demon_werewolf_has_cursed"]:
                    embed = discord.Embed(
                        title="👹 Hành Động Sói Quỷ",
                        description="Chọn một người để nguyền. Họ sẽ trở thành Sói vào đêm tiếp theo:",
                        color=discord.Color.dark_red()
                    )
                    await member.send(embed=embed, view=NightActionView("Demon Werewolf", alive_players, game_state, 40))
                elif game_state["demon_werewolf_has_cursed"]:
                    await member.send("Bạn đã sử dụng chức năng nguyền! Không còn chức năng đặc biệt nữa.")
                else:
                    await member.send("Chức năng Sói Quỷ chưa được kích hoạt. Bạn cần chờ một con Sói khác chết.")
        except discord.errors.Forbidden:
            logger.error(f"Cannot send DM to user {user_id}")
        except Exception as e:
            logger.error(f"Error sending action view to role {data['role']}, user {user_id}: {str(e)}")
    
    # Xử lý hành động của Sói Ám Sát
    for user_id, data in game_state["players"].items():
        if data["role"] == "Assassin Werewolf" and data["status"] in ["alive", "wounded"] and not game_state["assassin_werewolf_has_acted"]:
            assassin_member = game_state["member_cache"].get(user_id)
            if assassin_member:
                try:
                    embed = discord.Embed(
                        title="🗡️ Hành Động Sói Ám Sát",
                        description="Chọn một người chơi và đoán vai trò của họ. Đoán đúng, họ chết; sai, bạn chết:",
                        color=discord.Color.dark_red()
                    )
                    await assassin_member.send(embed=embed, view=AssassinActionView(game_state, user_id))
                except Exception as e:
                    logger.error(f"Error sending Assassin Werewolf view to user {user_id}: {str(e)}")
    
    # Xử lý hành động của Detective
    for user_id, data in game_state["players"].items():
        if data["role"] == "Detective" and data["status"] in ["alive", "wounded"] and not game_state["detective_has_used_power"]:
            detective_member = game_state["member_cache"].get(user_id)
            if detective_member:
                try:
                    embed = discord.Embed(
                        title="🔍 Hành Động Thám Tử",
                        description="Chọn hai người chơi để kiểm tra xem họ có cùng phe hay không:",
                        color=discord.Color.blue()
                    )
                    await detective_member.send(embed=embed, view=DetectiveSelectView(user_id, alive_players, game_state))
                except Exception as e:
                    logger.error(f"Error sending Detective view to user {user_id}: {str(e)}")

async def send_math_problems(interaction: discord.Interaction, game_state):
    """
    Gửi bài toán cho các vai trò cần giải toán
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    # Lấy danh sách người chơi còn sống
    from phases.voting import get_alive_players
    alive_players = await get_alive_players(interaction, game_state)
    
    # Gửi bài toán cho các vai không có hành động đêm
    for user_id, data in game_state["players"].items():
        if data["status"] not in ["alive", "wounded"] or data["role"] not in NO_NIGHT_ACTION_ROLES:
            continue
            
        member = game_state["member_cache"].get(user_id)
        if not member or member not in alive_players:
            continue
            
        try:
            # Tạo và gửi bài toán
            from views.action_views import NightMathView
            from utils.api_utils import generate_math_problem
            
            math_problem = await generate_math_problem(game_state["math_problems"])
            game_state["math_problems"][user_id] = math_problem
            
            options_str = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(math_problem["options"])])
            
            embed = discord.Embed(
                title="🧮 Bài Toán Ban Đêm",
                description=(
                    f"Bạn phải giải bài toán sau để được quyền bỏ phiếu vào ban ngày:\n\n"
                    f"**{math_problem['problem']}**\n\n"
                    f"Chọn đáp án đúng trong 40 giây:\n{options_str}"
                ),
                color=discord.Color.blue()
            )
            
            await member.send(
                embed=embed,
                view=NightMathView(user_id, math_problem["options"], math_problem["answer"], game_state)
            )
            
        except discord.errors.Forbidden:
            logger.error(f"Cannot send math problem to user {user_id}")
            # Đặt giá trị mặc định để người chơi không bị mất quyền bỏ phiếu
            game_state["math_results"][user_id] = True
            
        except Exception as e:
            logger.error(f"Error sending math problem to user {user_id}: {str(e)}")
            game_state["math_results"][user_id] = True

async def process_witch_actions(interaction: discord.Interaction, game_state):
    """
    Xử lý hành động của Phù Thủy
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    # Xác định các mục tiêu tiềm năng cho Phù Thủy
    potential_targets = []
    target_ids = set()
    kill_counts = {}  # Đếm số lần bị giết của mỗi người chơi
    
    # Thu thập tất cả các hành động giết
    actions = []
    
    # Hành động của Sói
    if game_state["werewolf_target_id"] and not game_state["demon_werewolf_cursed_this_night"]:
        actions.append(("werewolf", game_state["werewolf_target_id"]))
    
    # Hành động của Thợ Săn
    if game_state["hunter_target_id"]:
        actions.append(("hunter", game_state["hunter_target_id"]))
    
    # Hành động của Người Khám Phá
    if game_state["night_count"] >= 2 and game_state["explorer_target_id"]:
        explorer_target_id = game_state["explorer_target_id"]
        target_role = game_state["players"][explorer_target_id]["role"]
        if target_role in ["Werewolf", "Wolfman", "Assassin Werewolf", "Demon Werewolf"]:
            actions.append(("explorer", explorer_target_id))
        else:
            explorer_id = next((uid for uid, d in game_state["players"].items() if d["role"] == "Explorer" and d["status"] in ["alive", "wounded"]), None)
            if explorer_id:
                actions.append(("explorer", explorer_id))
    
    # Đếm số lần bị giết, bỏ qua người được Bảo Vệ
    protected_id = game_state["protected_player_id"]
    for action_type, target_id in actions:
        if target_id != protected_id:
            kill_counts[target_id] = kill_counts.get(target_id, 0) + 1
    
    # Xác định ai sẽ chết và thêm vào potential targets
    for user_id, count in kill_counts.items():
        data = game_state["players"].get(user_id)
        if data and data["status"] in ["alive", "wounded"]:
            if data["role"] == "Tough Guy":
                # Touch Guy chết nếu: alive + >=2 lần giết, hoặc wounded + >=1 lần giết
                if (data["status"] == "alive" and count >= 2) or (data["status"] == "wounded" and count >= 1):
                    target = game_state["member_cache"].get(user_id)
                    if target:
                        potential_targets.append(target)
                        target_ids.add(user_id)
            else:
                # Người thường chết nếu bị giết ít nhất 1 lần
                if count >= 1:
                    target = game_state["member_cache"].get(user_id)
                    if target:
                        potential_targets.append(target)
                        target_ids.add(user_id)
    
    logger.info(f"Potential targets for Witch: {target_ids}")
    
    # Tìm Phù Thủy và gửi view
    witch_id = next((user_id for user_id, data in game_state["players"].items() 
                    if data["role"] == "Witch" and data["status"] in ["alive", "wounded"]), None)
                    
    if witch_id and game_state["witch_has_power"]:
        witch_member = game_state["member_cache"].get(witch_id)
        if witch_member:
            from views.action_views import WitchActionView
            
            # Lấy danh sách người chơi còn sống
            from phases.voting import get_alive_players
            alive_players = await get_alive_players(interaction, game_state)
            
            try:
                if potential_targets:
                    target_names = ", ".join([t.display_name for t in potential_targets])
                    embed = discord.Embed(
                        title="🧙‍♀️ Hành Động Phù Thủy",
                        description=f"Đêm nay, {target_names} sẽ bị giết. Bạn có thể cứu một người hoặc giết người khác:",
                        color=discord.Color.purple()
                    )
                    await witch_member.send(
                        embed=embed,
                        view=WitchActionView(alive_players, potential_targets, game_state, timeout=20)
                    )
                    logger.info(f"Sent Witch notification with targets: {target_names}")
                else:
                    embed = discord.Embed(
                        title="🧙‍♀️ Hành Động Phù Thủy",
                        description="Không ai bị giết đêm nay! Bạn có thể chọn giết một người hoặc bỏ qua:",
                        color=discord.Color.purple()
                    )
                    await witch_member.send(
                        embed=embed,
                        view=WitchActionView(alive_players, [], game_state, timeout=20)
                    )
                    logger.info(f"Sent Witch notification: no targets")
            except Exception as e:
                logger.error(f"Error sending Witch view: {str(e)}")
    
    # Đợi quyết định của Phù Thủy
    from config import TIMINGS
    await countdown(game_state["text_channel"], TIMINGS["witch_action"], "quyết định Phù Thủy", game_state)
    
    if not game_state["is_game_running"] or game_state["is_game_paused"]:
        return

async def process_night_action_results(interaction: discord.Interaction, game_state):
    """
    Xử lý kết quả các hành động đêm
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
        
    Returns:
        List[str]: Danh sách tên người chơi đã chết
    """
    dead_players = []
    
    # Lưu mục tiêu ban đầu của Hunter
    original_hunter_target_id = game_state["hunter_target_id"]
    
    # 1. Xử lý hành động của Phù Thủy
    if game_state["witch_has_power"]:
        # Xử lý hành động cứu
        if game_state["witch_action_save"] and game_state["witch_target_save_id"]:
            target_id = game_state["witch_target_save_id"]
            if target_id in game_state["players"] and game_state["players"][target_id]["status"] in ["alive", "wounded"]:
                target_data = game_state["players"][target_id]
                logger.info(f"Witch saving player: target_id={target_id}")
                
                # Kiểm tra nếu là Tough Guy và sẽ chết
                if target_data["role"] == "Tough Guy":
                    count = 0
                    # Đếm số hành động giết nhắm vào Tough Guy
                    if game_state["werewolf_target_id"] == target_id and not game_state["demon_werewolf_cursed_this_night"]:
                        count += 1
                    if game_state["hunter_target_id"] == target_id:
                        count += 1
                    if game_state["explorer_target_id"] == target_id:
                        count += 1
                        
                    if (target_data["status"] == "alive" and count >= 2) or (target_data["status"] == "wounded" and count >= 1):
                        target_data["status"] = "wounded"
                        logger.info(f"Witch saved Tough Guy: target_id={target_id}, status set to wounded")
                    else:
                        logger.info(f"Witch saved Tough Guy but no status change needed: target_id={target_id}")
                
                # Hủy các hành động giết
                if game_state["werewolf_target_id"] == target_id:
                    game_state["werewolf_target_id"] = None
                if game_state["hunter_target_id"] == target_id:
                    game_state["hunter_target_id"] = None
                if game_state["explorer_target_id"] == target_id:
                    game_state["explorer_target_id"] = None
                
                # Gửi thông báo cho Phù Thủy
                witch_id = next((uid for uid, d in game_state["players"].items() if d["role"] == "Witch" and d["status"] in ["alive", "wounded"]), None)
                if witch_id:
                    witch_member = game_state["member_cache"].get(witch_id)
                    target_member = game_state["member_cache"].get(target_id)
                    if witch_member and target_member:
                        await witch_member.send(f"Bạn đã cứu {target_member.display_name} thành công! Từ đêm sau, bạn sẽ không nhận thông tin về người bị giết nữa.")
                
                # Đánh dấu Phù Thủy đã sử dụng quyền năng
                game_state["witch_has_power"] = False
        
        # Xử lý hành động giết
        if game_state["witch_action_kill"] and game_state["witch_target_kill_id"]:
            target_id = game_state["witch_target_kill_id"]
            if target_id in game_state["players"] and game_state["players"][target_id]["status"] in ["alive", "wounded"]:
                target_data = game_state["players"][target_id]
                
                # Kiểm tra người được Bảo Vệ
                if target_id == game_state["protected_player_id"]:
                    logger.info(f"Witch kill failed: target_id={target_id} is protected")
                    # Gửi thông báo cho Phù Thủy
                    witch_id = next((uid for uid, d in game_state["players"].items() if d["role"] == "Witch" and d["status"] in ["alive", "wounded"]), None)
                    if witch_id:
                        witch_member = game_state["member_cache"].get(witch_id)
                        if witch_member:
                            await witch_member.send("Mục tiêu của bạn được Bảo Vệ bảo vệ! Không thể giết người đó.")
                else:
                    # Xử lý giết người
                    member = game_state["member_cache"].get(target_id)
                    if member:
                        if target_data["role"] == "Tough Guy" and target_data["status"] == "alive":
                            target_data["status"] = "wounded"
                            logger.info(f"Tough Guy wounded by Witch: target_id={target_id}")
                        else:
                            target_data["status"] = "dead"
                            dead_players.append(member.display_name)
                            await handle_player_death(interaction, member, target_id, game_state, interaction.guild)
                            logger.info(f"Witch killed player: target_id={target_id}")
                
                # Đánh dấu Phù Thủy đã sử dụng quyền năng
                game_state["witch_has_power"] = False
    
    # 2. Xử lý các cái chết từ Sói và Thợ Săn
    for source, target_id in [("Werewolf", game_state["werewolf_target_id"]), 
                             ("Hunter", game_state["hunter_target_id"])]:
        if target_id and target_id != game_state["protected_player_id"]:
            if target_id in game_state["players"] and game_state["players"][target_id]["status"] in ["alive", "wounded"]:
                target_data = game_state["players"][target_id]
                member = game_state["member_cache"].get(target_id)
                
                if member:
                    logger.info(f"Processing death by {source}: target_id={target_id}, target_name={member.display_name}")
                    
                    # Kiểm tra điều kiện đặc biệt: Sói Quỷ đã nguyền trong đêm này
                    if source == "Werewolf" and game_state["demon_werewolf_cursed_this_night"]:
                        logger.info(f"Werewolf target not killed because Demon Werewolf cursed this night: target_id={target_id}")
                        continue
                        
                    # Kiểm tra Tough Guy
                    if target_data["role"] == "Tough Guy" and target_data["status"] == "alive":
                        target_data["status"] = "wounded"
                        logger.info(f"Tough Guy wounded by {source}: target_id={target_id}")
                    else:
                        target_data["status"] = "dead"
                        dead_players.append(member.display_name)
                        await handle_player_death(interaction, member, target_id, game_state, interaction.guild)
                        logger.info(f"{source} killed player: target_id={target_id}")
    
    # 3. Cập nhật trạng thái Hunter sau khi xử lý tất cả hành động
    if original_hunter_target_id is not None:
        game_state["hunter_has_power"] = False
        for user_id, data in game_state["players"].items():
            if data["role"] == "Hunter" and data["status"] in ["alive", "wounded"]:
                hunter_member = game_state["member_cache"].get(user_id)
                if hunter_member:
                    await hunter_member.send("Bạn đã sử dụng quyền năng của mình! Bạn không còn chức năng đặc biệt nữa.")
                break
    
    # 4. Xử lý các cái chết của Người Khám Phá
    if game_state["night_count"] >= 2 and game_state.get("explorer_id") in game_state["players"] and game_state["players"][game_state["explorer_id"]]["status"] in ["alive", "wounded"]:
        # Kiểm tra nếu không hành động
        if game_state["explorer_target_id"] is None:
            game_state["explorer_can_act"] = False
            explorer_member = game_state["member_cache"].get(game_state["explorer_id"])
            if explorer_member:
                await explorer_member.send("Bạn đã không chọn ai để khám phá, bạn đã mất chức năng của mình!")
        else:
            # Xử lý kết quả khám phá
            target_id = game_state["explorer_target_id"]
            if target_id in game_state["players"] and game_state["players"][target_id]["status"] in ["alive", "wounded"]:
                target_role = game_state["players"][target_id]["role"]
                explorer_id = game_state["explorer_id"]
                explorer_member = game_state["member_cache"].get(explorer_id)
                
                if target_role in ["Werewolf", "Wolfman", "Assassin Werewolf", "Demon Werewolf"]:
                    # Khám phá đúng Sói
                    if target_id == game_state["witch_target_save_id"]:
                        if explorer_member:
                            await explorer_member.send("Bạn đã khám phá đúng, nhưng Phù Thủy đã cứu người đó! Bạn vẫn giữ chức năng.")
                    elif target_id != game_state["protected_player_id"]:
                        target_data = game_state["players"][target_id]
                        target_member = game_state["member_cache"].get(target_id)
                        
                        if target_member:
                            if target_data["role"] == "Tough Guy" and target_data["status"] == "alive":
                                target_data["status"] = "wounded"
                            else:
                                target_data["status"] = "dead"
                                if target_member.display_name not in dead_players:
                                    dead_players.append(target_member.display_name)
                                await handle_player_death(interaction, target_member, target_id, game_state, interaction.guild)
                            
                            if explorer_member:
                                await explorer_member.send(f"Bạn đã khám phá và giết {target_member.display_name}!")
                else:
                    # Khám phá sai - người khám phá chết
                    if explorer_id == game_state["witch_target_save_id"] or explorer_id == game_state["protected_player_id"]:
                        if explorer_member:
                            await explorer_member.send("Bạn đã khám phá sai nhưng được bảo vệ! Bạn vẫn giữ chức năng.")
                    else:
                        explorer_data = game_state["players"][explorer_id]
                        if explorer_data["role"] == "Tough Guy" and explorer_data["status"] == "alive":
                            explorer_data["status"] = "wounded"
                        else:
                            explorer_data["status"] = "dead"
                            if explorer_member and explorer_member.display_name not in dead_players:
                                dead_players.append(explorer_member.display_name)
                            await handle_player_death(interaction, explorer_member, explorer_id, game_state, interaction.guild)
                        
                        if explorer_member:
                            await explorer_member.send("Bạn đã khám phá sai và tự sát!")
    
    # 5. Xử lý hành động của Sói Ám Sát
    if game_state["assassin_werewolf_has_acted"] and game_state["assassin_werewolf_target_id"] and game_state["assassin_werewolf_role_guess"]:
        target_id = game_state["assassin_werewolf_target_id"]
        role_guess = game_state["assassin_werewolf_role_guess"]
        assassin_id = next((uid for uid, d in game_state["players"].items() if d["role"] == "Assassin Werewolf"), None)
        
        if target_id in game_state["players"] and game_state["players"][target_id]["status"] in ["alive", "wounded"]:
            actual_role = game_state["players"][target_id]["role"]
            target_member = game_state["member_cache"].get(target_id)
            assassin_member = game_state["member_cache"].get(assassin_id)
            
            if actual_role == role_guess:
                # Đoán đúng, kiểm tra xem mục tiêu có được cứu hay không
                if target_id != game_state["witch_target_save_id"] and target_id != game_state["protected_player_id"]:
                    target_data = game_state["players"][target_id]
                    if target_data["role"] == "Tough Guy" and target_data["status"] == "alive":
                        target_data["status"] = "wounded"
                    else:
                        target_data["status"] = "dead"
                        if target_member and target_member.display_name not in dead_players:
                            dead_players.append(target_member.display_name)
                        await handle_player_death(interaction, target_member, target_id, game_state, interaction.guild)
                    
                    if assassin_member:
                        await assassin_member.send(f"Bạn đoán đúng! {target_member.display_name} là {actual_role} và đã chết.")
                else:
                    if assassin_member:
                        await assassin_member.send(f"Bạn đoán đúng, nhưng {target_member.display_name} được bảo vệ!")
            else:
                # Đoán sai, Sói Ám Sát chết
                if assassin_id != game_state["witch_target_save_id"] and assassin_id != game_state["protected_player_id"]:
                    assassin_data = game_state["players"][assassin_id]
                    if assassin_data["role"] == "Tough Guy" and assassin_data["status"] == "alive":
                        assassin_data["status"] = "wounded"
                    else:
                        assassin_data["status"] = "dead"
                        if assassin_member and assassin_member.display_name not in dead_players:
                            dead_players.append(assassin_member.display_name)
                        await handle_player_death(interaction, assassin_member, assassin_id, game_state, interaction.guild)
                    
                    if assassin_member:
                        await assassin_member.send(f"Bạn đoán sai! {target_member.display_name} không phải là {role_guess}. Bạn đã chết.")
                else:
                    if assassin_member:
                        await assassin_member.send(f"Bạn đoán sai, nhưng bạn được bảo vệ!")
        
        # Reset trạng thái Sói Ám Sát
        game_state["assassin_werewolf_target_id"] = None
        game_state["assassin_werewolf_role_guess"] = None
    
    # Lưu lại protected_player_id trước đó và reset
    game_state["previous_protected_player_id"] = game_state["protected_player_id"]
    game_state["protected_player_id"] = None
    
    # Reset trạng thái Sói Quỷ
    game_state["demon_werewolf_cursed_this_night"] = False
    
    return dead_players

async def announce_night_deaths(interaction: discord.Interaction, game_state, dead_players):
    """
    Thông báo người chết sau pha đêm
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
        dead_players (List[str]): Danh sách tên người chơi đã chết
    """
    text_channel = game_state["text_channel"]
    if not text_channel:
        return
    
    if dead_players:
        # Loại bỏ các tên trùng lặp nếu có
        dead_players = list(set(dead_players))
        
        death_embed = discord.Embed(
            title="💀 Thông Báo Người Ra Đi",
            description=f"{', '.join(dead_players)} đã lên bàn thờ ngắm gà ăn xôi nếp!",
            color=discord.Color.red()
        )
        death_embed.set_image(url=GIF_URLS["death"])
        await text_channel.send(embed=death_embed)
        logger.info(f"Announced deaths: {dead_players}")
        
        # Thêm vào log game
        from db import save_game_log
        await save_game_log(interaction.guild.id, f"Đêm {game_state['night_count']}: {', '.join(dead_players)} đã chết.")
    else:
        no_death_embed = discord.Embed(
            title="💀 Thông Báo Người Ra Đi",
            description="Không ai từ bỏ làng trong đêm nay!",
            color=discord.Color.green()
        )
        await text_channel.send(embed=no_death_embed)
        logger.info("No deaths announced")
        
        # Thêm vào log game
        from db import save_game_log
        await save_game_log(interaction.guild.id, f"Đêm {game_state['night_count']}: Không ai chết.")

async def restore_permissions(interaction: discord.Interaction, game_state):
    """
    Khôi phục quyền hạn sau pha đêm
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    text_channel = game_state["text_channel"]
    voice_channel = interaction.client.get_channel(game_state["voice_channel_id"])
    guild = interaction.guild
    
    # Khôi phục quyền chat cho text channel
    if text_channel:
        try:
            await text_channel.set_permissions(guild.default_role, send_messages=True)
            villager_role = guild.get_role(game_state["villager_role_id"])
            if villager_role:
                await text_channel.set_permissions(villager_role, send_messages=True)
            logger.info("Restored text channel permissions")
        except Exception as e:
            logger.error(f"Error restoring text channel permissions: {str(e)}")
    
    # Khôi phục quyền nói cho voice channel
    if voice_channel:
        try:
            await voice_channel.set_permissions(guild.default_role, speak=True)
            logger.info("Restored voice channel permissions")
        except Exception as e:
            logger.error(f"Error restoring voice channel permissions: {str(e)}")