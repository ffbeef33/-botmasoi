# phases/voting.py
# Module quản lý pha bỏ phiếu trong game

import discord
import logging
import asyncio
import traceback
from typing import Dict, List, Optional, Tuple

from constants import GIF_URLS, AUDIO_FILES, WEREWOLF_ROLES  # Thêm import WEREWOLF_ROLES
from utils.api_utils import play_audio, countdown, safe_send_message
from db import update_leaderboard, update_all_player_stats  # Thêm import update_all_player_stats

logger = logging.getLogger(__name__)

async def voting_phase(interaction: discord.Interaction, game_state):
    """
    Xử lý pha bỏ phiếu
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    if not game_state["is_game_running"] or game_state["is_game_paused"]:
        logger.info("voting_phase: Game stopped or paused, skipping")
        return
        
    logger.info(f"Starting voting phase in guild {interaction.guild.id}")
    game_state["phase"] = "voting"
    text_channel = game_state["text_channel"]
    
    try:
        # Lấy danh sách người chơi còn sống
        alive_players = await get_alive_players(interaction, game_state)
        
        # Tạo và gửi embed bỏ phiếu
        vote_embed = discord.Embed(
            title="🗳️ Pha Bỏ Phiếu",
            description="Chọn người để loại trong 45 giây.",
            color=discord.Color.gold()
        )
        vote_embed.set_image(url=GIF_URLS["vote"])
        
        # Import view
        from views.voting_views import VoteView
        
        # Tạo view và gửi tin nhắn
        vote_message = await text_channel.send(embed=vote_embed, view=VoteView(alive_players, game_state, 45))
        await vote_message.pin()
        
        # Phát âm thanh không đồng bộ
        asyncio.create_task(play_audio(AUDIO_FILES["vote"], game_state["voice_connection"]))
        
        # Tạo một timer tổng thể cho pha bỏ phiếu (45 giây)
        # Thay vì sử dụng các reminder tasks riêng biệt, dùng một timer duy nhất
        vote_start_time = asyncio.get_event_loop().time()
        voting_duration = 45  # tổng thời gian bỏ phiếu là 45 giây
        
        # Hiển thị nhắc nhở đầu tiên sau 15 giây
        await asyncio.sleep(15)
        if game_state["is_game_running"] and not game_state["is_game_paused"]:
            await text_channel.send("🗳️ **Nhắc nhở:** Còn 30 giây để bỏ phiếu!")
        
        # Hiển thị nhắc nhở thứ hai và kết quả tạm thời sau 30 giây
        await asyncio.sleep(15)  # thêm 15 giây nữa (tổng 30 giây)
        if game_state["is_game_running"] and not game_state["is_game_paused"]:
            await text_channel.send("🗳️ **Nhắc nhở cuối:** Còn 15 giây để bỏ phiếu!")
            await display_current_votes(interaction, game_state)
        
        # Đếm ngược 15 giây cuối (để đạt tổng 45 giây)
        await countdown(text_channel, 15, "bỏ phiếu", game_state)
        
        # Bỏ ghim tin nhắn vote
        try:
            await vote_message.unpin()
        except:
            logger.warning("Could not unpin vote message")
        
        # Hiển thị kết quả phiếu bầu cuối cùng
        if game_state["is_game_running"] and not game_state["is_game_paused"]:
            await display_final_votes(interaction, game_state)
            await process_vote_results(interaction, game_state)
        
        # Kiểm tra điều kiện thắng sau khi xử lý phiếu
        win_team = await check_win_condition(interaction, game_state)
        if win_team:
            # Lưu thông tin phe thắng cuộc để sử dụng trong end_game
            game_state["last_winner"] = win_team
            
            # Cập nhật leaderboard khi kết thúc game
            await update_leaderboard_from_game(interaction, game_state, win_team)
            return
        
        # Chuyển sang pha đêm nếu game vẫn tiếp tục
        if game_state["is_game_running"] and not game_state["is_game_paused"]:
            await text_channel.send("Pha bỏ phiếu đã kết thúc. Chuẩn bị chuyển sang pha đêm trong 10 giây...")
            await countdown(text_channel, 10, "chuẩn bị pha đêm", game_state)
            
            if game_state["is_game_running"] and not game_state["is_game_paused"]:
                from phases.night import night_phase
                await night_phase(interaction, game_state)
    
    except Exception as e:
        logger.error(f"Error in voting_phase: {str(e)}")
        traceback.print_exc()
        if text_channel:
            await text_channel.send(f"Đã xảy ra lỗi trong pha bỏ phiếu: {str(e)[:100]}...")

async def get_alive_players(interaction: discord.Interaction, game_state) -> List[discord.Member]:
    """
    Lấy danh sách người chơi còn sống
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    
    Returns:
        List[discord.Member]: Danh sách Member còn sống
    """
    alive_players = []
    for player_id, data in game_state["players"].items():
        if data["status"] in ["alive", "wounded"]:
            member = game_state["member_cache"].get(player_id)
            if member:
                alive_players.append(member)
    return alive_players

async def display_current_votes(interaction: discord.Interaction, game_state):
    """
    Hiển thị phiếu bầu hiện tại
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    text_channel = game_state["text_channel"]
    if not text_channel:
        return
    
    try:
        # Đếm phiếu
        vote_counts, skip_votes, ineligible_count = count_votes(game_state)
        non_vote_count = skip_votes + ineligible_count
        
        # Tạo nội dung hiển thị
        embed = discord.Embed(
            title="🗳️ Thống Kê Phiếu Bầu Tạm Thời",
            color=discord.Color.gold()
        )
        
        # Hiển thị phiếu bầu cho từng người
        if vote_counts:
            vote_lines = []
            for target_id, count in sorted(vote_counts.items(), key=lambda x: x[1], reverse=True):
                target_member = game_state["member_cache"].get(target_id)
                if target_member:
                    vote_lines.append(f"**{target_member.display_name}**: {count} phiếu")
            
            embed.add_field(name="Phiếu bầu", value="\n".join(vote_lines) or "Không có phiếu bầu", inline=False)
        else:
            embed.add_field(name="Phiếu bầu", value="Chưa có ai nhận được phiếu bầu", inline=False)
        
        # Gộp số phiếu bỏ qua và không đủ điều kiện
        embed.add_field(name="Bỏ qua/Không đủ điều kiện", value=str(non_vote_count), inline=False)
        
        embed.set_footer(text="Kết quả tạm thời, còn 15 giây để bỏ phiếu...")
        await text_channel.send(embed=embed)
    except Exception as e:
        logger.error(f"Error displaying current votes: {str(e)}")
        traceback.print_exc()

async def display_final_votes(interaction: discord.Interaction, game_state):
    """
    Hiển thị kết quả phiếu bầu cuối cùng
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    text_channel = game_state["text_channel"]
    if not text_channel:
        return
    
    try:
        # Đếm phiếu
        vote_counts, skip_votes, ineligible_count = count_votes(game_state)
        non_vote_count = skip_votes + ineligible_count
        
        # Tạo nội dung hiển thị
        embed = discord.Embed(
            title="📊 Kết Quả Phiếu Bầu Cuối Cùng",
            color=discord.Color.gold()
        )
        
        # Hiển thị phiếu bầu cho từng người
        if vote_counts:
            vote_lines = []
            for target_id, count in sorted(vote_counts.items(), key=lambda x: x[1], reverse=True):
                target_member = game_state["member_cache"].get(target_id)
                if target_member:
                    vote_lines.append(f"**{target_member.display_name}**: {count} phiếu")
            
            embed.add_field(name="Phiếu bầu", value="\n".join(vote_lines) or "Không có phiếu bầu", inline=False)
        else:
            embed.add_field(name="Phiếu bầu", value="Không ai nhận được phiếu bầu", inline=False)
        
        # Gộp số phiếu bỏ qua và không đủ điều kiện
        embed.add_field(name="Bỏ qua/Không đủ điều kiện", value=str(non_vote_count), inline=False)
        
        # Thêm thống kê tổng quát
        alive_count = len([p for pid, p in game_state["players"].items() if p["status"] in ["alive", "wounded"]])
        total_votes = sum(vote_counts.values()) + non_vote_count
        
        stats = [
            f"**Tổng người chơi còn sống**: {alive_count}",
            f"**Tổng phiếu đã bầu**: {total_votes}"
        ]
        
        embed.add_field(name="Thống kê", value="\n".join(stats), inline=False)
        
        await text_channel.send(embed=embed)
    except Exception as e:
        logger.error(f"Error displaying final votes: {str(e)}")
        traceback.print_exc()

def count_votes(game_state) -> Tuple[Dict[int, int], int, int]:
    """
    Đếm số phiếu bầu cho từng người chơi
    
    Args:
        game_state (dict): Trạng thái game
        
    Returns:
        Tuple[Dict[int, int], int, int]: (vote_counts, skip_votes, ineligible_count)
    """
    vote_counts = {}
    skip_votes = 0
    ineligible_count = 0
    
    for user_id, data in game_state["players"].items():
        if not data["status"] in ["alive", "wounded"]:
            continue
            
        # Kiểm tra điều kiện để vote
        from constants import NO_NIGHT_ACTION_ROLES
        eligible_to_vote = True
        
        if data["role"] in NO_NIGHT_ACTION_ROLES:
            if user_id not in game_state["math_results"] or not game_state["math_results"][user_id]:
                eligible_to_vote = False
                ineligible_count += 1
                continue
        
        # Xử lý phiếu bầu
        if eligible_to_vote:
            target_id = game_state["votes"].get(user_id, "skip")
            if target_id == "skip":
                skip_votes += 1
            elif isinstance(target_id, int):
                vote_counts[target_id] = vote_counts.get(target_id, 0) + 1
    
    return vote_counts, skip_votes, ineligible_count

async def process_vote_results(interaction: discord.Interaction, game_state):
    """
    Xử lý kết quả bỏ phiếu để loại người chơi
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    text_channel = game_state["text_channel"]
    if not text_channel:
        return
    
    # Đếm phiếu
    vote_counts, skip_votes, ineligible_count = count_votes(game_state)
    
    # Total non-vote = skip_votes + ineligible_count (dùng để hiển thị)
    display_non_vote_count = skip_votes + ineligible_count
    
    # THAY ĐỔI: Chỉ sử dụng skip_votes (không bao gồm ineligible_count) khi so sánh với số phiếu cao nhất
    # để quyết định người bị loại
    
    if vote_counts:
        # Tìm người có số phiếu cao nhất
        max_votes = max(vote_counts.values()) if vote_counts else 0
        candidates = [k for k, v in vote_counts.items() if v == max_votes]
        
        # THAY ĐỔI: Chỉ loại người chơi nếu:
        # 1. Có một người duy nhất có số phiếu cao nhất (không có đồng phiếu)
        # 2. Số phiếu cao nhất phải lớn hơn số phiếu bỏ qua (không tính người không đủ điều kiện)
        if len(candidates) == 1 and max_votes > skip_votes:
            # Có một người được chọn duy nhất với số phiếu cao nhất
            eliminated_id = candidates[0]
            eliminated_member = game_state["member_cache"].get(eliminated_id)
            
            if (eliminated_member and eliminated_id in game_state["players"] and 
                game_state["players"][eliminated_id]["status"] in ["alive", "wounded"]):
                # Xử lý người chơi bị loại
                game_state["players"][eliminated_id]["status"] = "dead"
                
                # Import hàm xử lý người chơi chết
                from utils.role_utils import handle_player_death
                await handle_player_death(interaction, eliminated_member, eliminated_id, game_state, interaction.guild)
                
                # Hiển thị thông báo
                hang_embed = discord.Embed(
                    title="⚰️ Kết Quả Bỏ Phiếu",
                    description=f"**{eliminated_member.display_name}** đã bị ngồi ghế điện với {max_votes} phiếu!",
                    color=discord.Color.red()
                )
                hang_embed.set_image(url=GIF_URLS["hang"])
                await text_channel.send(embed=hang_embed)
                
                # Phát âm thanh
                await play_audio(AUDIO_FILES["hang"], game_state["voice_connection"])
                
                # Thêm vào log
                if hasattr(interaction, 'guild') and interaction.guild.id in globals().get('game_logs', {}):
                    game_logs[interaction.guild.id].append(f"{eliminated_member.display_name} bị ngồi ghế điện với {max_votes} phiếu.")
                    
                return True  # Có người bị loại
        
        elif len(candidates) > 1:
            # Có đồng phiếu giữa các người chơi
            candidate_names = [game_state["member_cache"].get(c).display_name for c in candidates if game_state["member_cache"].get(c)]
            await text_channel.send(f"**Có đồng phiếu giữa {', '.join(candidate_names)}! Không ai bị loại.**")
            
        else:
            # Số phiếu bỏ qua cao hơn hoặc bằng số phiếu cao nhất
            await text_channel.send(f"**Không ai bị loại!** Số phiếu 'bỏ qua' cao hơn hoặc bằng số phiếu cao nhất ({max_votes}).")
            
    else:
        # Không có phiếu bầu nào
        await text_channel.send("**Không ai bị loại!** Tất cả phiếu đều là 'bỏ qua' hoặc 'không đủ điều kiện'.")
    
    return False  # Không có người bị loại

async def check_win_condition(interaction: discord.Interaction, game_state):
    """
    Kiểm tra điều kiện thắng và kết thúc game nếu đã có đội thắng
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
        
    Returns:
        str or None: "villagers", "werewolves" nếu đã có đội thắng, None nếu chưa
    """
    # Đếm số lượng người còn sống theo phe
    werewolf_count = 0
    villager_count = 0
    
    for user_id, data in game_state["players"].items():
        if data["status"] not in ["alive", "wounded"]:
            continue
            
        if data["role"] in ["Werewolf", "Wolfman", "Demon Werewolf", "Assassin Werewolf"]:
            werewolf_count += 1
        else:
            villager_count += 1
    
    text_channel = game_state["text_channel"]
    
    # Phe Dân chỉ thắng khi không còn Sói và không có lời nguyền đang chờ
    if werewolf_count == 0 and villager_count > 0 and game_state["demon_werewolf_cursed_player"] is None:
        if text_channel:
            win_embed = discord.Embed(
                title="🎉 Kết Thúc Game - Phe Dân Thắng!",
                description="Tất cả Sói đã bị loại! Dân làng có thể sống yên bình!",
                color=discord.Color.green()
            )
            win_embed.set_image(url=GIF_URLS["villager_win"])
            await text_channel.send(embed=win_embed)
            
            # Gửi thông báo giải tích
            await send_game_analysis(interaction, game_state, "villagers")
            
            # Đánh dấu đã hiển thị thông báo tóm tắt để tránh hiển thị lần nữa
            game_state["summary_already_shown"] = True
            
            # Lưu thông tin về phe thắng để sử dụng sau này
            game_state["last_winner"] = "villagers"
            
        logger.info(f"Villagers win! (Werewolves: {werewolf_count}, Villagers: {villager_count})")
        
        # Kết thúc game
        from phases.end_game import handle_game_end
        await handle_game_end(interaction, game_state)
        return "villagers"
        
    # Phe Sói thắng nếu số Sói bằng hoặc vượt số Dân
    elif (werewolf_count >= villager_count and werewolf_count > 0) or villager_count == 0:
        if text_channel:
            win_embed = discord.Embed(
                title="🐺 Kết Thúc Game - Phe Sói Thắng!",
                description="Số lượng Sói đã bằng hoặc vượt số Dân làng! Làng đã thuộc về Sói!",
                color=discord.Color.red()
            )
            win_embed.set_image(url=GIF_URLS["werewolf_win"])
            await text_channel.send(embed=win_embed)
            
            # Gửi thông báo giải tích
            await send_game_analysis(interaction, game_state, "werewolves")
            
            # Đánh dấu đã hiển thị thông báo tóm tắt để tránh hiển thị lần nữa
            game_state["summary_already_shown"] = True
            
            # Lưu thông tin về phe thắng để sử dụng sau này
            game_state["last_winner"] = "werewolves"
            
        logger.info(f"Werewolves win! (Werewolves: {werewolf_count}, Villagers: {villager_count})")
        
        # Kết thúc game
        from phases.end_game import handle_game_end
        await handle_game_end(interaction, game_state)
        return "werewolves"
        
    # Game chưa kết thúc
    return None

async def send_game_analysis(interaction: discord.Interaction, game_state, winning_team):
    """
    Gửi phân tích kết quả game
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
        winning_team (str): Đội thắng cuộc
    """
    text_channel = game_state["text_channel"]
    if not text_channel:
        return
        
    # Phân tích vai trò và trạng thái cuối cùng
    role_analysis = []
    for user_id, data in game_state["players"].items():
        member = game_state["member_cache"].get(user_id)
        if not member:
            continue
            
        status = "🟢 Sống" if data["status"] == "alive" else \
                "🟡 Bị Thương" if data["status"] == "wounded" else "💀 Đã Chết"
                
        team = "Phe Dân" if data["role"] in ["Villager", "Seer", "Guard", "Witch", 
                                            "Hunter", "Tough Guy", "Explorer", "Detective"] else "Phe Sói"
        
        role_analysis.append(f"**{member.display_name}**: {data['role']} ({team}) - {status}")
    
    # Tạo embed phân tích
    embed = discord.Embed(
        title=f"📊 Phân Tích Kết Thúc Game - {winning_team.title()} Thắng!",
        color=discord.Color.blue()
    )
    
    # Chia thành nhiều field nếu quá dài
    chunks = [role_analysis[i:i+10] for i in range(0, len(role_analysis), 10)]
    for i, chunk in enumerate(chunks):
        embed.add_field(name=f"Vai Trò Người Chơi {i+1}", value="\n".join(chunk), inline=False)
    
    # Thêm thống kê game
    stats = [
        f"**Số đêm:** {game_state['night_count']}",
        f"**Số người ban đầu:** {len(game_state['players'])}",
        f"**Số người còn sống:** {sum(1 for d in game_state['players'].values() if d['status'] in ['alive', 'wounded'])}"
    ]
    embed.add_field(name="Thống Kê Game", value="\n".join(stats), inline=False)
    
    await text_channel.send(embed=embed)

async def update_leaderboard_from_game(interaction: discord.Interaction, game_state, winning_team):
    """
    Cập nhật leaderboard từ kết quả game - Sử dụng cả hai phương pháp để đảm bảo dữ liệu được cập nhật
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
        winning_team (str): "villagers" hoặc "werewolves"
    """
    try:
        # Thiết lập cờ để tránh cập nhật nhiều lần
        if game_state.get("leaderboard_updated", False):
            logger.info("Leaderboard đã được cập nhật trước đó, bỏ qua")
            return
            
        logger.info(f"Bắt đầu cập nhật leaderboard với phe thắng: {winning_team}")
        
        # Phương pháp 1: Sử dụng update_all_player_stats (đáng tin cậy hơn)
        try:
            logger.info("Đang cập nhật leaderboard bằng update_all_player_stats...")
            result = await update_all_player_stats(game_state, winning_team)
            if result:
                logger.info("Cập nhật leaderboard thành công với update_all_player_stats")
                game_state["leaderboard_updated"] = True
                if game_state["text_channel"]:
                    await game_state["text_channel"].send("🏆 Leaderboard đã được cập nhật!")
                return
            else:
                logger.warning("update_all_player_stats trả về False, thử phương pháp khác")
        except Exception as e:
            logger.error(f"Lỗi khi sử dụng update_all_player_stats: {str(e)}")
            traceback.print_exc()
        
        # Phương pháp 2: Sử dụng update_leaderboard - phương pháp backup
        guild_id = interaction.guild.id
        player_updates = {}
        
        for user_id, data in game_state["players"].items():
            # Đảm bảo user_id là int
            user_id_int = int(user_id)
            
            member = game_state["member_cache"].get(user_id_int) or game_state["member_cache"].get(str(user_id_int))
            
            if not member:
                logger.warning(f"Không tìm thấy member cho user_id {user_id_int} trong cache")
                continue
                
            # Xác định vai trò và điểm thưởng
            is_werewolf = data["role"] in WEREWOLF_ROLES
            player_team = "werewolves" if is_werewolf else "villagers"
            
            # SỬA ĐỔI: Kiểm tra trạng thái người chơi
            is_alive = data["status"] in ["alive", "wounded"]
            
            # SỬA ĐỔI: Logic tính điểm mới
            if player_team == winning_team:
                score_increment = 3 if is_alive else 1
            else:
                score_increment = -1  # Phe thua luôn -1 điểm
                              
            player_updates[user_id_int] = {
                "name": member.display_name,
                "score": score_increment
            }
            
            # Ghi log chi tiết
            logger.debug(f"Chuẩn bị cập nhật điểm cho {member.display_name} ({user_id_int}): +{score_increment} điểm (Team: {player_team}, Win: {player_team == winning_team}, Alive: {is_alive})")
        
        # Cập nhật leaderboard trong database
        try:
            logger.info(f"Đang cập nhật leaderboard cho {len(player_updates)} người chơi...")
            success = await update_leaderboard(guild_id, player_updates)
            
            if success:
                logger.info("Cập nhật leaderboard thành công với update_leaderboard")
                game_state["leaderboard_updated"] = True
                if game_state["text_channel"]:
                    await game_state["text_channel"].send("🏆 Leaderboard đã được cập nhật!")
                return True
            else:
                logger.warning("Cập nhật leaderboard thất bại với update_leaderboard")
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật leaderboard với update_leaderboard: {str(e)}")
            traceback.print_exc()
            
        return False
    except Exception as e:
        logger.error(f"Lỗi tổng thể khi cập nhật leaderboard: {str(e)}")
        traceback.print_exc()
        return False
