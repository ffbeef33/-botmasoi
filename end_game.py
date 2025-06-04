# phases/end_game.py
# Module xử lý kết thúc game

import discord
import logging
import asyncio
import traceback
from typing import Dict, List, Optional

from constants import AUDIO_FILES, BOT_VERSION
from utils.api_utils import play_audio
from views.voting_views import GameEndView
from db import update_all_player_stats  # Thêm import này

logger = logging.getLogger(__name__)

async def end_game(interaction, game_state, winner="no_one", reason="Game đã kết thúc", show_roles=True):
    """
    Kết thúc game và dọn dẹp tài nguyên
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
        winner (str): Phe thắng cuộc ("wolves", "villagers", "no_one")
        reason (str): Lý do kết thúc game
        show_roles (bool): Hiển thị vai trò người chơi hay không
    """
    try:
        # Kiểm tra game có đang chạy không
        is_running = False
        try:
            is_running = game_state.is_game_running
        except:
            is_running = game_state.get("is_game_running", False)
            
        if not is_running:
            await interaction.response.send_message("Không có game nào đang chạy!", ephemeral=True)
            return
            
        # Thông báo game kết thúc
        try:
            await interaction.response.send_message(f"Game đã kết thúc! {reason}")
        except:
            try:
                await interaction.followup.send(f"Game đã kết thúc! {reason}")
            except:
                logger.warning("Không thể gửi response hoặc followup khi kết thúc game")
                
        # ===== CẬP NHẬT LEADERBOARD TRƯỚC KHI LÀM BẤT CỨ ĐIỀU GÌ KHÁC =====
        try:
            # Chuẩn hóa winner để đảm bảo đúng định dạng
            normalized_winner = winner
            if winner == "wolves":
                normalized_winner = "werewolves"
            elif winner == "humans":
                normalized_winner = "villagers"
                
            # Sử dụng last_winner từ game_state nếu không có winner được chỉ định
            if normalized_winner == "no_one":
                try:
                    normalized_winner = game_state.last_winner
                except:
                    normalized_winner = game_state.get("last_winner", "no_one")
                    
            logger.info(f"Cập nhật leaderboard cho game kết thúc với winner: {normalized_winner}")
            
            # Kiểm tra nếu leaderboard đã được cập nhật để tránh trùng lặp
            if game_state.get("leaderboard_updated", False):
                logger.info("Leaderboard đã được cập nhật trước đó, bỏ qua")
            else:
                update_success = await update_all_player_stats(game_state, normalized_winner)
                if update_success:
                    logger.info("Cập nhật leaderboard thành công")
                    text_channel = game_state.get("text_channel") or interaction.channel
                    if text_channel:
                        await text_channel.send("🏆 Leaderboard đã được cập nhật!")
                else:
                    logger.error("Cập nhật leaderboard thất bại")
                    
                # Đánh dấu rằng leaderboard đã được cập nhật để tránh cập nhật lặp lại
                game_state["leaderboard_updated"] = True
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật leaderboard: {str(e)}")
            traceback.print_exc()
                
        # Phát âm thanh kết thúc game
        try:
            voice_conn = None
            try:
                voice_conn = game_state.voice_connection
            except:
                voice_conn = game_state.get("voice_connection")
                
            if voice_conn and voice_conn.is_connected():
                await play_audio(AUDIO_FILES["end_game"], voice_conn)
                await asyncio.sleep(2)  # Đợi âm thanh phát xong
        except Exception as e:
            logger.error(f"Lỗi khi phát âm thanh kết thúc: {str(e)}")
        
        # QUAN TRỌNG: Di chuyển người chơi về kênh chính TRƯỚC
        await restore_player_states(interaction, game_state)
        
        # Đợi một chút để đảm bảo việc di chuyển hoàn tất
        await asyncio.sleep(2)
        
        # Thực hiện dọn dẹp và xóa kênh
        await cleanup_channels(interaction, game_state)
        await cleanup_roles(interaction, game_state)
        
        # Gửi tóm tắt game
        guild_id = interaction.guild.id
        await send_game_summary(interaction, game_state, guild_id)
        
        # Reset trạng thái game
        reset_game_variables(game_state)
        
        # Hiển thị menu kết thúc
        text_channel = None
        try:
            text_channel = game_state.text_channel
        except:
            text_channel = game_state.get("text_channel")
            
        if text_channel:
            admin_id = None
            try:
                admin_id = game_state.temp_admin_id
            except:
                admin_id = game_state.get("temp_admin_id")
                
            await text_channel.send("Game đã kết thúc. Chọn hành động tiếp theo:", 
                                  view=GameEndView(admin_id, interaction, game_state))
        
    except Exception as e:
        logger.error(f"Lỗi khi kết thúc game: {str(e)}")
        traceback.print_exc()
        await interaction.channel.send(f"Đã xảy ra lỗi khi kết thúc game: {str(e)}")

async def handle_game_end(interaction: discord.Interaction, game_state):
    """
    Xử lý kết thúc game và cung cấp tùy chọn
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    if game_state["text_channel"] is not None:
        await game_state["text_channel"].send("Game đang kết thúc và dữ liệu đang được xóa, vui lòng chờ...")
    else:
        logger.warning("Text channel not set, cannot send game ending message")
    
    # THÊM: Cập nhật leaderboard trước khi reset game state
    if not game_state.get("leaderboard_updated", False):
        try:
            # Lấy thông tin phe thắng từ game_state
            winner = "no_one"
            try:
                winner = game_state.last_winner
            except:
                winner = game_state.get("last_winner", "no_one")
                
            logger.info(f"Cập nhật leaderboard từ handle_game_end với winner: {winner}")
            
            if winner != "no_one":
                # Cập nhật leaderboard
                update_success = await update_all_player_stats(game_state, winner)
                if update_success:
                    logger.info("Cập nhật leaderboard thành công từ handle_game_end")
                    # Thông báo cập nhật leaderboard thành công
                    text_channel = game_state.get("text_channel")
                    if text_channel:
                        await text_channel.send("🏆 Leaderboard đã được cập nhật!")
                else:
                    logger.error("Cập nhật leaderboard thất bại từ handle_game_end")
            else:
                logger.warning("Không xác định được phe thắng cuộc để cập nhật leaderboard")
                
            # Đánh dấu rằng leaderboard đã được cập nhật
            game_state["leaderboard_updated"] = True
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật leaderboard từ handle_game_end: {str(e)}")
            traceback.print_exc()
    
    # Lưu thông tin setup trước khi reset
    try:
        # Tạo bản sao cụ thể của dữ liệu setup
        try:
            game_state.preserved_setup = {
                "temp_admin_id": game_state.temp_admin_id,
                "temp_players": game_state.temp_players.copy() if hasattr(game_state, 'temp_players') and game_state.temp_players else [],
                "temp_roles": game_state.temp_roles.copy() if hasattr(game_state, 'temp_roles') and game_state.temp_roles else {}
            }
        except:
            game_state["preserved_setup"] = {
                "temp_admin_id": game_state.get("temp_admin_id"),
                "temp_players": game_state.get("temp_players", [])[:],  # Tạo bản sao
                "temp_roles": game_state.get("temp_roles", {}).copy()  # Tạo bản sao
            }
        
        # Đánh dấu rằng setup được lưu trữ
        game_state["setup_preserved"] = True
        
        logger.info("Game setup preserved successfully")
    except Exception as e:
        logger.error(f"Error preserving game setup: {str(e)}")
    
    # Reset game state
    await reset_game_state(interaction, game_state)
    
    # Thêm khoảng thời gian chờ để đảm bảo các tác vụ reset hoàn tất
    await asyncio.sleep(3)
    
    # Phát âm thanh end_game.mp3 trước khi bot rời kênh voice
    if game_state["voice_connection"] and game_state["voice_connection"].is_connected():
        await play_audio(AUDIO_FILES["end_game"], game_state["voice_connection"])
    
    # Thêm thời gian chờ cho âm thanh phát xong
    await asyncio.sleep(2)
    
    # Bot rời kênh voice sau khi phát âm thanh
    if game_state["voice_connection"] and game_state["voice_connection"].is_connected():
        try:
            await game_state["voice_connection"].disconnect()
            logger.info(f"Bot disconnected from voice channel: ID={game_state['voice_channel_id']}")
        except Exception as e:
            logger.error(f"Failed to disconnect from voice channel ID={game_state['voice_channel_id']}: {str(e)}")
        game_state["voice_connection"] = None
    
    if game_state["text_channel"] is not None:
        await game_state["text_channel"].send("Game đã kết thúc. Chọn hành động tiếp theo:", 
                                            view=GameEndView(game_state["temp_admin_id"], interaction, game_state))
    else:
        logger.warning("Text channel not set, cannot send game end options message")

async def reset_game_state(interaction: discord.Interaction, game_state):
    """
    Reset trạng thái game mà không xóa thông tin tạm thời
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    if not isinstance(interaction, discord.Interaction):
        logger.error(f"reset_game_state called with invalid type: {type(interaction)}")
        logger.error(f"Call stack: {''.join(traceback.format_stack())}")
        if hasattr(interaction, 'channel'):
            await interaction.channel.send("Lỗi: Hàm này chỉ hỗ trợ slash commands!")
        return
    
    guild_id = interaction.guild.id if interaction.guild else game_state.get("guild_id")
    if not guild_id:
        logger.error("Cannot determine guild ID for reset_game_state")
        return
        
    if game_state["reset_in_progress"]:
        logger.warning(f"Reset already in progress, ignoring reset request by {interaction.user.id if interaction.user else 'Unknown'}")
        await interaction.channel.send("Đang thực hiện reset, vui lòng chờ!")
        return
        
    if not game_state["is_game_running"]:
        logger.info(f"No game running to reset, requested by {interaction.user.id if interaction.user else 'Unknown'}")
        await interaction.channel.send("Chưa có game nào để reset!")
        return
        
    game_state["reset_in_progress"] = True
    logger.info(f"Resetting game state: is_game_running={game_state['is_game_running']}, guild_id={game_state.get('guild_id')}")

    try:
        # Kiểm tra nếu summary đã được hiển thị trong check_win_condition
        summary_already_shown = game_state.get("summary_already_shown", False)
        
        # Gửi log kết quả game nếu chưa hiển thị
        if not summary_already_shown:
            await send_game_summary(interaction, game_state, guild_id)
        else:
            logger.info("Summary already shown, skipping duplicate summary")
        
        # QUAN TRỌNG: Thứ tự thực hiện reset - di chuyển người chơi TRƯỚC, sau đó mới dọn dẹp kênh và vai trò
        await restore_player_states(interaction, game_state)  # Di chuyển người chơi và unmute TRƯỚC
        
        # Thêm độ trễ để đảm bảo việc di chuyển hoàn tất
        await asyncio.sleep(1.5)
        
        # Sau đó mới thực hiện các tác vụ dọn dẹp
        tasks = [
            cleanup_channels(interaction, game_state),     # Dọn dẹp kênh wolf-chat và dead-chat
            cleanup_roles(interaction, game_state)         # Xóa vai trò game
        ]
        
        await asyncio.gather(*tasks)
        
        # Reset game state
        reset_game_variables(game_state)
        
        # Chỉ hiển thị thông báo này nếu là reset từ nút reset, không phải từ kết thúc game
        if not summary_already_shown:
            await interaction.channel.send("Game đã được reset thành công! Tất cả trạng thái đã được khôi phục.")
    except Exception as e:
        logger.error(f"Error during game reset: {str(e)}")
        traceback.print_exc()
        await interaction.channel.send(f"Lỗi khi reset game: {str(e)[:100]}...")
    finally:
        game_state["reset_in_progress"] = False

async def send_game_summary(interaction, game_state, guild_id):
    """
    Gửi tóm tắt kết quả game
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
        guild_id (int): ID của guild
    """
    # Lấy channel để gửi
    text_channel = game_state.get("text_channel") or (interaction.channel if interaction else None)
    if not text_channel:
        logger.warning("No text channel found to send game summary")
        return
    
    try:
        # Tạo summary từ logs và trạng thái game
        from db import get_game_logs
        
        embed = discord.Embed(title="Kết Quả Game", color=discord.Color.blue())
        
        # Lấy logs và xử lý đúng định dạng
        try:
            game_logs = await get_game_logs(guild_id)
            
            # Hiển thị logs nếu có
            if game_logs:
                # Xử lý dữ liệu log từ định dạng dict
                log_entries = []
                for log_entry in game_logs[:10]:  # Lấy 10 log gần nhất
                    # Log có thể là dictionary với cấu trúc khác nhau
                    if isinstance(log_entry, dict):
                        if "players_data" in log_entry:
                            log_entries.append(str(log_entry.get("players_data", "")))
                        else:
                            # Cố gắng tạo dòng log từ các trường khả dụng
                            timestamp = log_entry.get("timestamp", "")
                            winner = log_entry.get("winner", "")
                            log_entries.append(f"{timestamp}: {winner}")
                    else:
                        log_entries.append(str(log_entry))
                
                if log_entries:
                    embed.add_field(
                        name="Diễn biến", 
                        value="\n".join(log_entries) or "Không có dữ liệu chi tiết", 
                        inline=False
                    )
                else:
                    embed.add_field(name="Diễn biến", value="Không có dữ liệu", inline=False)
            else:
                embed.add_field(name="Diễn biến", value="Không có dữ liệu game logs", inline=False)
        except Exception as log_error:
            logger.error(f"Error processing game logs: {str(log_error)}")
            embed.add_field(name="Diễn biến", value=f"Lỗi khi tải logs: {str(log_error)[:100]}", inline=False)
        
        # Hiển thị vai trò và trạng thái người chơi
        try:
            role_list = []
            for user_id, data in game_state.get("players", {}).items():
                member = game_state.get("member_cache", {}).get(user_id)
                if member:
                    status = "Sống" if data.get("status") == "alive" else "Bị thương" if data.get("status") == "wounded" else "Chết"
                    role_list.append(f"{member.display_name}: {data.get('role', 'Unknown')} ({status})")
            
            if role_list:
                embed.add_field(name="Người chơi", value="\n".join(role_list), inline=False)
            else:
                embed.add_field(name="Người chơi", value="Không có dữ liệu", inline=False)
        except Exception as player_error:
            logger.error(f"Error processing player data: {str(player_error)}")
            embed.add_field(name="Người chơi", value="Lỗi khi hiển thị thông tin người chơi", inline=False)
        
        # Hiển thị số đêm và thống kê khác
        try:
            stats = [
                f"Số đêm: {game_state.get('night_count', 0)}",
                f"Số người chơi: {len(game_state.get('players', {}))}"
            ]
            embed.add_field(name="Thống kê", value="\n".join(stats), inline=False)
        except Exception as stats_error:
            logger.error(f"Error processing game stats: {str(stats_error)}")
            embed.add_field(name="Thống kê", value="Lỗi khi hiển thị thống kê", inline=False)
        
        # Footer có thể gây lỗi nếu interaction.user là None
        try:
            user_name = interaction.user.name if interaction and interaction.user else "Unknown"
            embed.set_footer(text=f"Log được gửi bởi {user_name} | {BOT_VERSION}")
        except:
            embed.set_footer(text=f"Log kết quả game | {BOT_VERSION}")
        
        await text_channel.send(embed=embed)
    except Exception as e:
        logger.error(f"Error sending game summary: {str(e)}")
        try:
            await text_channel.send("Lỗi: Không thể gửi tóm tắt game.")
        except:
            logger.error("Cannot send error message to text channel")

async def restore_player_states(interaction, game_state):
    """
    Khôi phục trạng thái người chơi (di chuyển, unmute, v.v.)
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    try:
        # Lấy kênh voice chính
        voice_channel_id = None
        try:
            voice_channel_id = game_state.voice_channel_id
        except:
            voice_channel_id = game_state.get("voice_channel_id")
            
        main_channel = interaction.guild.get_channel(voice_channel_id)
        if not main_channel:
            logger.error(f"Main voice channel not found: ID={voice_channel_id}")
            return
        
        # Di chuyển người chơi từ các kênh riêng về kênh chính
        logger.info(f"Starting to move players to main voice channel: {main_channel.name}")
        player_channels = {}
        try:
            player_channels = game_state.player_channels
        except:
            player_channels = game_state.get("player_channels", {})
            
        # Di chuyển từng người chơi trong các kênh riêng
        moved_count = 0
        for user_id, channel in player_channels.items():
            try:
                member = interaction.guild.get_member(int(user_id))
                if member and member.voice and member.voice.channel:
                    await member.move_to(main_channel)
                    logger.info(f"Moved player {member.display_name} to main channel")
                    moved_count += 1
                    
                    # Nếu bị mute thì unmute
                    if member.voice.mute:
                        try:
                            await member.edit(mute=False)
                            logger.info(f"Unmuted player {member.display_name}")
                        except:
                            logger.warning(f"Failed to unmute player {member.display_name}")
                    
                    # Thêm độ trễ nhỏ để tránh rate limit
                    await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Error moving player ID {user_id}: {str(e)}")
                
        # Di chuyển người chơi từ kênh sói và kênh người chết
        for channel_attr in ["wolf_channel", "dead_channel"]:
            special_channel = None
            try:
                special_channel = getattr(game_state, channel_attr)
            except:
                special_channel = game_state.get(channel_attr)
                
            if special_channel:
                try:
                    # Di chuyển tất cả thành viên trong kênh này về kênh chính
                    for member in special_channel.members:
                        if not member.bot and member.voice and member.voice.channel:
                            try:
                                await member.move_to(main_channel)
                                logger.info(f"Moved player {member.display_name} from {channel_attr} to main channel")
                                moved_count += 1
                                
                                # Nếu bị mute thì unmute
                                if member.voice.mute:
                                    await member.edit(mute=False)
                                
                                # Thêm độ trễ nhỏ để tránh rate limit
                                await asyncio.sleep(0.3)
                            except Exception as e:
                                logger.error(f"Error moving player {member.display_name} from {channel_attr}: {str(e)}")
                except Exception as e:
                    logger.error(f"Error processing {channel_attr}: {str(e)}")
                    
        logger.info(f"Successfully moved {moved_count} players to main channel")
        
        # Đảm bảo mọi người đều được unmute
        players = {}
        try:
            players = game_state.players
        except:
            players = game_state.get("players", {})
            
        # Unmute tất cả người chơi (một lần nữa để chắc chắn)
        for user_id in players:
            try:
                member = interaction.guild.get_member(int(user_id))
                if member and member.voice and member.voice.mute:
                    await member.edit(mute=False)
            except Exception as e:
                logger.error(f"Error unmuting player ID {user_id}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error restoring player states: {str(e)}")
        traceback.print_exc()

async def cleanup_channels(interaction, game_state):
    """
    Dọn dẹp các kênh voice và text liên quan đến game
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    guild = interaction.guild
    
    # Lấy các kênh cần xử lý
    text_channel = None
    dead_channel = None
    wolf_channel = None
    player_channels = {}
    
    try:
        text_channel = game_state.text_channel
        dead_channel = game_state.dead_channel
        wolf_channel = game_state.wolf_channel
        player_channels = game_state.player_channels
    except:
        text_channel = game_state.get("text_channel") or interaction.channel
        dead_channel = game_state.get("dead_channel")
        wolf_channel = game_state.get("wolf_channel")
        player_channels = game_state.get("player_channels", {})
    
    try:
        # Khôi phục quyền cho kênh text
        if text_channel:
            if text_channel.category:
                await text_channel.edit(sync_permissions=True)
                logger.info(f"Synchronized permissions for channel {text_channel.name}")
            else:
                await text_channel.set_permissions(guild.default_role, send_messages=True)
                logger.info(f"Restored send permission for channel {text_channel.name}")
        
        # Xóa các kênh voice riêng
        voice_deletion_tasks = []
        for user_id, channel in player_channels.items():
            if channel:
                voice_deletion_tasks.append(channel.delete())
        
        # Xóa kênh wolf-chat và dead-chat
        text_deletion_tasks = []
        if dead_channel:
            text_deletion_tasks.append(dead_channel.delete())
        if wolf_channel:
            text_deletion_tasks.append(wolf_channel.delete())
        
        # Thực hiện các task xóa kênh cùng lúc
        if voice_deletion_tasks:
            await asyncio.gather(*voice_deletion_tasks, return_exceptions=True)
            logger.info(f"Deleted {len(voice_deletion_tasks)} private voice channels")
            
        if text_deletion_tasks:
            await asyncio.gather(*text_deletion_tasks, return_exceptions=True)
            logger.info(f"Deleted wolf-chat and dead-chat channels")
        
        # Xóa thông tin kênh từ game state
        try:
            game_state.player_channels = {}
            game_state.wolf_channel = None
            game_state.dead_channel = None
        except:
            game_state["player_channels"] = {}
            game_state["wolf_channel"] = None
            game_state["dead_channel"] = None
    except Exception as e:
        logger.error(f"Error cleaning up channels: {str(e)}")
        traceback.print_exc()

async def cleanup_roles(interaction, game_state):
    """
    Xóa các vai trò Discord liên quan đến game
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        game_state (dict): Trạng thái game hiện tại
    """
    guild = interaction.guild
    
    # Lấy các roles cần xóa
    villager_role_id = None
    dead_role_id = None
    werewolf_role_id = None
    
    try:
        villager_role_id = game_state.villager_role_id
        dead_role_id = game_state.dead_role_id
        werewolf_role_id = game_state.werewolf_role_id
    except:
        villager_role_id = game_state.get("villager_role_id")
        dead_role_id = game_state.get("dead_role_id")
        werewolf_role_id = game_state.get("werewolf_role_id")
    
    villager_role = guild.get_role(villager_role_id) if villager_role_id else None
    dead_role = guild.get_role(dead_role_id) if dead_role_id else None
    werewolf_role = guild.get_role(werewolf_role_id) if werewolf_role_id else None
    
    try:
        # Xóa các roles khỏi người chơi
        remove_role_tasks = []
        
        # Lấy danh sách người chơi
        players = {}
        try:
            players = game_state.players
        except:
            players = game_state.get("players", {})
            
        for user_id in players:
            member = guild.get_member(int(user_id))
            if not member:
                continue
                
            roles_to_remove = []
            if villager_role and villager_role in member.roles:
                roles_to_remove.append(villager_role)
            if dead_role and dead_role in member.roles:
                roles_to_remove.append(dead_role)
            if werewolf_role and werewolf_role in member.roles:
                roles_to_remove.append(werewolf_role)
                
            if roles_to_remove:
                remove_role_tasks.append(member.remove_roles(*roles_to_remove, reason="Game reset"))
        
        # Thực hiện xóa roles khỏi người chơi cùng lúc
        if remove_role_tasks:
            await asyncio.gather(*remove_role_tasks, return_exceptions=True)
            logger.info(f"Removed roles from {len(remove_role_tasks)} players")
        
        # Xóa các roles
        delete_role_tasks = []
        if villager_role:
            delete_role_tasks.append(villager_role.delete(reason="Game reset"))
        if dead_role:
            delete_role_tasks.append(dead_role.delete(reason="Game reset"))
        if werewolf_role:
            delete_role_tasks.append(werewolf_role.delete(reason="Game reset"))
            
        # Thực hiện xóa roles cùng lúc
        if delete_role_tasks:
            await asyncio.gather(*delete_role_tasks, return_exceptions=True)
            logger.info("Deleted game roles")
            
        # Xóa thông tin roles từ game state
        try:
            game_state.villager_role_id = None
            game_state.dead_role_id = None
            game_state.werewolf_role_id = None
        except:
            game_state["villager_role_id"] = None
            game_state["dead_role_id"] = None
            game_state["werewolf_role_id"] = None
    except Exception as e:
        logger.error(f"Error cleaning up roles: {str(e)}")
        traceback.print_exc()

def reset_game_variables(game_state):
    """
    Reset tất cả biến trạng thái game
    
    Args:
        game_state (dict): Trạng thái game hiện tại
    """
    # Giữ lại thông tin để khởi động lại game
    try:
        temp_admin_id = game_state.temp_admin_id
        temp_players = game_state.temp_players.copy() if hasattr(game_state, 'temp_players') and game_state.temp_players else []
        temp_roles = game_state.temp_roles.copy() if hasattr(game_state, 'temp_roles') and game_state.temp_roles else {}
        guild_id = game_state.guild_id
        voice_channel_id = game_state.voice_channel_id
        text_channel = game_state.text_channel
        member_cache = game_state.member_cache
    except:
        temp_admin_id = game_state.get("temp_admin_id")
        temp_players = game_state.get("temp_players", [])[:]  # Tạo bản sao
        temp_roles = game_state.get("temp_roles", {}).copy()  # Tạo bản sao
        guild_id = game_state.get("guild_id")
        voice_channel_id = game_state.get("voice_channel_id")
        text_channel = game_state.get("text_channel")
        member_cache = game_state.get("member_cache")
    
    # Đánh dấu setup đã được lưu
    setup_preserved = True
    
    # Reset tất cả biến game state
    try:
        game_state.players.clear()
        game_state.votes.clear()
        game_state.is_game_running = False
        game_state.is_game_paused = False
        game_state.phase = "none"
        game_state.is_first_day = True
        game_state.protected_player_id = None
        game_state.previous_protected_player_id = None
        game_state.werewolf_target_id = None
        game_state.witch_target_id = None
        game_state.witch_action = None
        game_state.witch_action_save = False
        game_state.witch_action_kill = False
        game_state.witch_has_power = True
        game_state.hunter_target_id = None
        game_state.hunter_has_power = True
        game_state.explorer_target_id = None
        game_state.explorer_id = None
        game_state.explorer_can_act = True
        game_state.illusionist_scanned = False
        game_state.illusionist_effect_active = False
        game_state.illusionist_effect_night = 0
        game_state.night_count = 0
        game_state.demon_werewolf_activated = False
        game_state.demon_werewolf_cursed_player = None
        game_state.demon_werewolf_has_cursed = False
        game_state.demon_werewolf_cursed_this_night = False
        game_state.assassin_werewolf_has_acted = False
        game_state.assassin_werewolf_target_id = None
        game_state.assassin_werewolf_role_guess = None
        game_state.detective_has_used_power = False
        game_state.detective_target1_id = None
        game_state.detective_target2_id = None
        game_state.math_problems.clear() if hasattr(game_state, 'math_problems') else None
        game_state.math_results.clear() if hasattr(game_state, 'math_results') else None
        
        # THÊM: Reset cờ liên quan đến leaderboard
        game_state.leaderboard_updated = False
        game_state.last_winner = None
        game_state.summary_already_shown = False
    except:
        game_state["players"] = {}
        game_state["votes"] = {}
        game_state["is_game_running"] = False
        game_state["is_game_paused"] = False
        game_state["phase"] = "none"
        game_state["is_first_day"] = True
        game_state["protected_player_id"] = None
        game_state["previous_protected_player_id"] = None
        game_state["werewolf_target_id"] = None
        game_state["witch_target_id"] = None
        game_state["witch_action"] = None
        game_state["witch_action_save"] = False
        game_state["witch_action_kill"] = False
        game_state["witch_has_power"] = True
        game_state["hunter_target_id"] = None
        game_state["hunter_has_power"] = True
        game_state["explorer_target_id"] = None
        game_state["explorer_id"] = None
        game_state["explorer_can_act"] = True
        game_state["illusionist_scanned"] = False
        game_state["illusionist_effect_active"] = False
        game_state["illusionist_effect_night"] = 0
        game_state["night_count"] = 0
        game_state["demon_werewolf_activated"] = False
        game_state["demon_werewolf_cursed_player"] = None
        game_state["demon_werewolf_has_cursed"] = False
        game_state["demon_werewolf_cursed_this_night"] = False
        game_state["assassin_werewolf_has_acted"] = False
        game_state["assassin_werewolf_target_id"] = None
        game_state["assassin_werewolf_role_guess"] = None
        game_state["detective_has_used_power"] = False
        game_state["detective_target1_id"] = None
        game_state["detective_target2_id"] = None
        game_state["math_problems"] = {}
        game_state["math_results"] = {}
        
        # THÊM: Reset cờ liên quan đến leaderboard
        game_state["leaderboard_updated"] = False
        game_state["last_winner"] = None
        game_state["summary_already_shown"] = False
    
    # Khôi phục thông tin tạm thời
    try:
        game_state.temp_admin_id = temp_admin_id
        game_state.temp_players = temp_players
        game_state.temp_roles = temp_roles
        game_state.guild_id = guild_id
        game_state.voice_channel_id = voice_channel_id
        game_state.text_channel = text_channel
        game_state.member_cache = member_cache
        game_state.setup_preserved = setup_preserved  # Thêm dòng này
    except:
        game_state["temp_admin_id"] = temp_admin_id
        game_state["temp_players"] = temp_players
        game_state["temp_roles"] = temp_roles
        game_state["guild_id"] = guild_id
        game_state["voice_channel_id"] = voice_channel_id
        game_state["text_channel"] = text_channel
        game_state["member_cache"] = member_cache
        game_state["setup_preserved"] = setup_preserved
    
    logger.info(f"Reset game variables for guild {guild_id} and preserved game setup")
