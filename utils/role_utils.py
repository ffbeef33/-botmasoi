# utils/role_utils.py
# Tiện ích cho vai trò và xử lý vai trò người chơi

import discord
import logging
import random
from typing import Dict, List, Optional, Tuple
import asyncio

from constants import ROLE_DESCRIPTIONS, ROLE_ICONS, ROLE_LINKS, ROLES, VILLAGER_ROLES, WEREWOLF_ROLES
from utils.api_utils import retry_api_call, safe_send_message

logger = logging.getLogger(__name__)

def get_player_team(role: str) -> str:
    """
    Xác định phe của một vai trò
    
    Args:
        role (str): Tên vai trò
    
    Returns:
        str: "werewolves", "villagers", hoặc "unknown"
    """
    if role in ["Illusionist", "Wolfman", "Werewolf", "Demon Werewolf", "Assassin Werewolf"]:
        return "werewolves"
    elif role in VILLAGER_ROLES:
        return "villagers"
    else:
        return "unknown"

async def assign_random_roles(game_state, guild):
    """
    Phân vai ngẫu nhiên cho người chơi
    
    Args:
        game_state: Trạng thái game hiện tại
        guild (discord.Guild): Guild đang chơi game
    """
    roles = []
    for role, count in game_state.temp_roles.items():
        roles.extend([role] * count)
    
    random.shuffle(roles)
    
    # Lấy các role và channel cần thiết
    villager_role = guild.get_role(game_state.villager_role_id)
    werewolf_role = guild.get_role(game_state.werewolf_role_id)
    wolf_channel = game_state.wolf_channel
    
    # Phân vai và gửi DM
    werewolf_players = []
    illusionist_player = None
    
    tasks = []
    for i, user_id in enumerate(game_state.temp_players):
        member = game_state.member_cache.get(user_id)
        if not member:
            logger.error(f"Không tìm thấy thành viên ID={user_id} trong cache")
            continue
        
        role = roles[i]
        game_state.players[user_id] = {
            "role": role, 
            "status": "alive", 
            "muted": False
        }
        
        # Gán Discord roles
        role_tasks = [member.add_roles(villager_role)]
        
        if role in ["Werewolf", "Wolfman", "Demon Werewolf", "Assassin Werewolf"]:
            role_tasks.append(member.add_roles(werewolf_role))
            role_tasks.append(wolf_channel.set_permissions(member, read_messages=True, send_messages=True))
            werewolf_players.append(member)
        elif role == "Illusionist":
            illusionist_player = member
        
        # Thực hiện các thao tác role Discord song song
        tasks.append(asyncio.gather(*role_tasks))
        
        # CẢI THIỆN: Gửi thông báo vai trò qua DM với embed đẹp hơn
        role_icon_url = ROLE_ICONS.get(role, "https://example.com/default_icon.png")
        role_link = ROLE_LINKS.get(role, "")
        
        embed = discord.Embed(
            title="Vai Trò Của Bạn",
            description=f"Bạn đã được phân vai: **{role}**",
            color=discord.Color.blue()
        )
        
        # Thêm mô tả vai trò
        embed.add_field(name="Mô tả", value=ROLE_DESCRIPTIONS.get(role, "Không có mô tả"), inline=False)
        
        # Thêm link thông tin chi tiết nếu có
        if role_link:
            embed.add_field(
                name="Thông tin chi tiết",
                value=f"[Click here để xem]({role_link})",
                inline=False
            )
            
        # Đặt thumbnail là icon của vai trò
        embed.set_thumbnail(url=role_icon_url)
        
        # Thêm footer với thông tin bổ sung
        embed.set_footer(text="Ma Sói | Giữ bí mật vai trò của bạn!")
        
        tasks.append(retry_api_call(lambda m=member, e=embed: m.send(embed=e)))
        
        # Gửi hướng dẫn bổ sung cho vai trò cụ thể
        await send_role_instructions(member, role, game_state)
    
    # Đợi tất cả các tác vụ hoàn thành
    await asyncio.gather(*tasks)
    
    # Gửi thông báo trong Wolf Channel về danh sách sói và ảo giác
    if wolf_channel:
        embed = discord.Embed(
            title="Danh sách Sói phe Sói",
            color=discord.Color.red()
        )
        
        if werewolf_players:
            werewolf_names = ", ".join([m.display_name for m in werewolf_players])
            embed.add_field(name="Sói", value=werewolf_names, inline=False)
        
        if illusionist_player:
            embed.add_field(name="Ảo Giác", value=illusionist_player.display_name, inline=False)
            embed.add_field(
                name="Lưu ý", 
                value="Ảo Giác thuộc phe Sói nhưng không thức dậy cùng các bạn và không biết ai là Sói. "
                      "Tuy nhiên nó được tính vào phe Dân khi đếm điều kiện thắng.",
                inline=False
            )
        
        await wolf_channel.send(embed=embed)

async def send_role_instructions(member, role, game_state):
    """
    Gửi hướng dẫn cụ thể cho vai trò
    
    Args:
        member (discord.Member): Thành viên cần gửi
        role (str): Vai trò của thành viên
        game_state: Trạng thái game hiện tại
    """
    if role == "Werewolf":
        await member.send(
            "🐺 **Hướng dẫn cho Sói:**\n"
            "- Mỗi đêm bạn sẽ thức dậy cùng bầy sói trong kênh wolf-chat\n"
            "- Thảo luận và chọn một người để giết qua nút chọn\n"
            "- Nếu có Nhà Ảo Giác, bạn sẽ biết đó là ai nhưng họ không biết bạn\n"
            "- Ban ngày, giả vờ là Dân để tránh bị phát hiện"
        )
    
    elif role == "Seer":
        await member.send(
            "👁️ **Hướng dẫn cho Tiên Tri:**\n"
            "- Mỗi đêm bạn có thể kiểm tra một người để biết họ thuộc phe Dân hay Sói\n"
            "- Kết quả soi có thể bị đảo ngược nếu Nhà Ảo Giác đã bị soi trước đó\n"
            "- Sử dụng thông tin một cách khôn ngoan để giúp phe Dân chiến thắng"
        )
    
    elif role == "Guard":
        await member.send(
            "🛡️ **Hướng dẫn cho Bảo Vệ:**\n"
            "- Mỗi đêm bạn có thể bảo vệ một người khỏi bị giết\n"
            "- Bạn không thể bảo vệ cùng một người hai đêm liên tiếp\n"
            "- Bạn có thể bảo vệ chính mình"
        )
    
    elif role == "Witch":
        await member.send(
            "🧙‍♀️ **Hướng dẫn cho Phù Thủy:**\n"
            "- Mỗi đêm bạn sẽ biết ai bị chọn để giết\n"
            "- Bạn có một lần duy nhất để cứu người đó\n"
            "- Bạn cũng có một lần duy nhất để giết một người\n"
            "- Sau khi sử dụng chức năng, bạn sẽ không còn nhận thông tin về người bị giết"
        )
    
    elif role == "Hunter":
        await member.send(
            "🏹 **Hướng dẫn cho Thợ Săn:**\n"
            "- Bạn có một lần duy nhất trong game để giết một người\n"
            "- Sử dụng quyền năng này một cách khôn ngoan\n"
            "- Sau khi sử dụng, bạn trở thành Dân thường"
        )
    
    elif role == "Tough Guy":
        await member.send(
            "💪 **Hướng dẫn cho Người Cứng Cỏi:**\n"
            "- Bạn có 2 mạng đối với các hành động giết vào ban đêm\n"
            "- Nếu bị ngồi ghế điện (vote ban ngày), bạn sẽ chết ngay lập tức\n"
            "- Bạn phải chọn đáp án đúng trong bài toán cộng/trừ để được quyền bỏ phiếu"
        )
    
    elif role == "Illusionist":
        await member.send(
            "🎭 **Hướng dẫn cho Nhà Ảo Giác:**\n"
            "- Bạn thuộc phe Sói nhưng không biết ai là Sói\n"
            "- Sói biết bạn là Nhà Ảo Giác\n"
            "- Nếu bị Tiên Tri soi, kết quả sẽ là Phe Dân\n"
            "- Đêm tiếp theo, kết quả soi của Tiên Tri sẽ bị đảo ngược\n"
            "- Bạn phải chọn đáp án đúng trong bài toán để được bỏ phiếu"
        )
    
    elif role == "Wolfman":
        await member.send(
            "🐺👤 **Hướng dẫn cho Người Sói:**\n"
            "- Bạn thức dậy cùng bầy Sói và tham gia chọn giết\n"
            "- Nếu bị Tiên Tri soi, kết quả sẽ là Phe Dân\n"
            "- Bạn vẫn được tính là Sói khi đếm điều kiện thắng"
        )
    
    elif role == "Explorer":
        game_state["explorer_id"] = member.id
        game_state["explorer_can_act"] = True
        await member.send(
            "🧭 **Hướng dẫn cho Người Khám Phá:**\n"
            "- Từ đêm thứ hai, mỗi đêm bạn phải chọn giết một người\n"
            "- Nếu chọn đúng Sói, Sói sẽ chết\n"
            "- Nếu chọn trúng Dân, bạn sẽ chết\n"
            "- Nếu không chọn, bạn sẽ mất chức năng"
        )
    
    elif role == "Demon Werewolf":
        await member.send(
            "👹 **Hướng dẫn cho Sói Quỷ:**\n"
            "- Bạn thức dậy cùng bầy Sói và tham gia chọn giết\n"
            "- Khi một Sói bất kỳ chết, bạn được kích hoạt\n"
            "- Bạn có thể nguyền một người để biến họ thành Sói vào đêm tiếp theo\n"
            "- Trong đêm nguyền, mục tiêu của bầy Sói không chết"
        )
    
    elif role == "Assassin Werewolf":
        await member.send(
            "🗡️ **Hướng dẫn cho Sói Ám Sát:**\n"
            "- Bạn thức dậy cùng bầy Sói và tham gia chọn giết\n"
            "- Bạn có một lần duy nhất để chọn người và đoán vai trò\n"
            "- Nếu đoán đúng, người đó chết; nếu sai, bạn chết\n"
            "- Bạn không thể đoán vai trò Dân Làng"
        )
    
    elif role == "Detective":
        await member.send(
            "🔍 **Hướng dẫn cho Thám Tử:**\n"
            "- Bạn có một lần duy nhất để chọn hai người chơi\n"
            "- Bạn sẽ biết hai người đó có cùng phe hay không\n"
            "- Ảo Giác được tính vào phe Sói khi kiểm tra\n"
            "- Sử dụng thông tin này để tìm ra Sói"
        )
    
    elif role == "Villager":
        await member.send(
            "👨‍🌾 **Hướng dẫn cho Dân Làng:**\n"
            "- Bạn không có chức năng đặc biệt vào ban đêm\n"
            "- Tham gia thảo luận và bỏ phiếu vào ban ngày\n"
            "- Bạn phải chọn đáp án đúng trong bài toán để được bỏ phiếu\n"
            "- Cố gắng tìm ra ai là Sói để loại bỏ"
        )

async def handle_player_death(interaction, member, user_id, game_state, guild):
    """
    Xử lý khi người chơi chết
    
    Args:
        interaction (discord.Interaction): Interaction gốc
        member (discord.Member): Thành viên đã chết
        user_id (int): ID của người chết
        game_state: Trạng thái game hiện tại
        guild (discord.Guild): Guild đang chơi game
    """
    if not guild or not member:
        logger.error(f"Guild hoặc member không tìm thấy trong handle_player_death, user_id={user_id}")
        return
        
    try:
        # Lấy các roles và channels cần thiết
        dead_role = guild.get_role(game_state.dead_role_id)
        villager_role = guild.get_role(game_state.villager_role_id)
        werewolf_role = guild.get_role(game_state.werewolf_role_id)
        wolf_channel = game_state.wolf_channel
        dead_channel = game_state.dead_channel
        text_channel = game_state.text_channel
        
        if not (dead_role and villager_role and dead_channel):
            logger.error(f"Thiếu roles/channels cần thiết trong handle_player_death")
            if text_channel:
                await text_channel.send("Lỗi: Không tìm thấy vai trò hoặc kênh cần thiết.")
            return
        
        # Cập nhật trạng thái người chơi trước tiên
        game_state.players[user_id]["status"] = "dead"
        
        # Tạo các tasks để thực hiện đồng thời
        tasks = []
        
        # Task gán vai trò Dead và xóa vai trò Villager/Werewolf
        async def update_roles():
            try:
                roles_to_remove = []
                if villager_role in member.roles:
                    roles_to_remove.append(villager_role)
                
                if werewolf_role and werewolf_role in member.roles:
                    roles_to_remove.append(werewolf_role)
                
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason="Người chơi đã chết")
                
                await member.add_roles(dead_role, reason="Người chơi đã chết")
                logger.info(f"Đã cập nhật vai trò cho người chết: {member.display_name}")
            except Exception as e:
                logger.error(f"Lỗi cập nhật vai trò cho người chết {member.id}: {str(e)}")
        
        # Task cấp quyền truy cập kênh dead-chat
        async def update_dead_channel():
            try:
                await dead_channel.set_permissions(member, read_messages=True, send_messages=True)
                embed = discord.Embed(
                    title="💀 Chào Mừng Đến Nghĩa Địa",
                    description=f"{member.mention} đã tham gia kênh người chết!",
                    color=discord.Color.greyple()
                )
                await dead_channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Lỗi cập nhật dead channel cho người chơi {member.id}: {str(e)}")
        
        # Task thu hồi quyền truy cập wolf-chat nếu là sói
        async def revoke_wolf_access():
            try:
                player_role = game_state.players[user_id]["role"]
                if player_role in WEREWOLF_ROLES and wolf_channel:
                    await wolf_channel.set_permissions(member, read_messages=False, send_messages=False)
                    await wolf_channel.send(f"⚰️ **{member.display_name}** ({player_role}) đã chết và không còn truy cập kênh này.")
            except Exception as e:
                logger.error(f"Lỗi thu hồi quyền wolf channel cho người chơi {member.id}: {str(e)}")
        
        # Thêm các task vào danh sách
        tasks.append(update_roles())
        tasks.append(update_dead_channel())
        tasks.append(revoke_wolf_access())
        
        # Thực hiện tất cả các tasks cùng một lúc
        await asyncio.gather(*tasks)
        
        # Kiểm tra các hành động đặc biệt khi người chơi chết
        player_role = game_state.players[user_id]["role"]
        
        # Kích hoạt Sói Quỷ nếu một con sói chết
        if player_role in ["Werewolf", "Wolfman", "Assassin Werewolf"]:
            for pid, data in game_state.players.items():
                if data["role"] == "Demon Werewolf" and data["status"] in ["alive", "wounded"] and not game_state.demon_werewolf_has_cursed:
                    game_state.demon_werewolf_activated = True
                    demon_player = game_state.member_cache.get(pid)
                    if demon_player:
                        await demon_player.send("⚡ **Một con sói đã chết!** Bạn có thể chọn nguyền một người chơi trong đêm tiếp theo.")
                    break
                    
    except Exception as e:
        logger.error(f"Lỗi trong handle_player_death: {str(e)}")
        if game_state.text_channel:
            await game_state.text_channel.send(f"Có lỗi khi xử lý cái chết của người chơi: {str(e)[:100]}...")