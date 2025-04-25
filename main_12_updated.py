import discord
from discord.ext import commands
import random
import asyncio
import os
import logging
from flask import Flask
from threading import Thread
import time
import traceback
import inspect
import socket
from collections import deque

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Log hoạt động vai trò
game_log = []

# Máy chủ Flask để giữ Replit hoạt động
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('0.0.0.0', port)) == 0

def run():
    port = 8080
    if is_port_in_use(port):
        logger.warning(f"Port {port} is in use. Trying port 8081.")
        port = 8081
    if is_port_in_use(port):
        logger.error(f"Port {port} is also in use. Cannot start Flask server.")
        return
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Khởi tạo bot với prefix và intents
intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Trạng thái game
game_state = {
    "players": {},
    "voice_channel_id": None,
    "guild_id": None,
    "is_game_running": False,
    "phase": "none",
    "is_first_day": True,
    "protected_player_id": None,
    "werewolf_target_id": None,
    "witch_target_id": None,
    "witch_action": None,
    "witch_has_power": True,
    "hunter_target_id": None,
    "hunter_has_power": True,
    "votes": {},
    "text_channel": None,
    "wolf_channel": None,
    "dead_channel": None,
    "illusionist_scanned": False,
    "illusionist_effect_active": False,
    "temp_player_count": 0,
    "temp_players": [],
    "temp_roles": {"Villager": 0, "Werewolf": 0, "Seer": 0, "Guard": 0, "Witch": 0, "Hunter": 0, "Tough Guy": 0, "Illusionist": 0, "Wolfman": 0},
    "temp_admin_id": None,
    "reset_in_progress": False,
    "math_problems": {},
    "math_results": {},
    "member_cache": {}  # Bộ nhớ đệm cho thành viên
}

# Danh sách vai trò và mô tả
ROLES = ["Villager", "Werewolf", "Seer", "Guard", "Witch", "Hunter", "Tough Guy", "Illusionist", "Wolfman"]
VILLAGER_SPECIAL_ROLES = ["Seer", "Guard", "Witch", "Hunter", "Tough Guy"]
WEREWOLF_SPECIAL_ROLES = ["Illusionist", "Wolfman"]
VILLAGER_ROLES = ["Villager", "Seer", "Guard", "Witch", "Hunter", "Tough Guy"]
WEREWOLF_ROLES = ["Werewolf", "Illusionist", "Wolfman"]
NO_NIGHT_ACTION_ROLES = ["Villager", "Tough Guy", "Illusionist"]

ROLE_DESCRIPTIONS = {
    "Villager": "Không có chức năng đặc biệt, tham gia thảo luận và bỏ phiếu ban ngày (từ ngày thứ hai). Phải chọn đáp án đúng trong bài toán cộng/trừ vào ban đêm để được quyền bỏ phiếu.",
    "Werewolf": "Mỗi đêm thảo luận trong wolf-chat và chọn giết 1 người bằng nút chọn. Biết ai là Nhà Ảo Giác (nếu có).",
    "Seer": "Mỗi đêm kiểm tra 1 người thuộc phe Dân hoặc Sói bằng nút chọn qua DM. Kleaders Kết quả có thể bị đảo ngược nếu Nhà Ảo Giác bị soi trước đó.",
    "Guard": "Mỗi đêm bảo vệ 1 người bằng nút chọn qua DM, ngăn họ bị giết bởi Sói, Phù Thủy hoặc Thợ Săn.",
    "Witch": "Mỗi đêm biết ai bị chọn giết, có 1 lần duy nhất để cứu bằng nút 'Save' hoặc giết 1 người bằng nút chọn qua DM. Nhận thông báo muộn hơn để quyết định trong 30 giây cuối.",
    "Hunter": "Có 1 lần duy nhất trong đêm để giết 1 người bằng nút chọn qua DM.",
    "Tough Guy": "Thuộc phe Dân, có 2 mạng. Phải bị giết 2 lần để chết hoàn toàn. Không có thông báo khi mất mạng. Phải chọn đáp án đúng trong bài toán cộng/trừ vào ban đêm để được quyền bỏ phiếu.",
    "Illusionist": "Thuộc phe Sói, thắng cùng Sói nhưng không thức dậy trong wolf-chat và không biết ai là Sói. Sói biết Nhà Ảo Giác. Được tính vào Phe Dân khi kiểm đếm thắng thua. Nếu bị Tiên Tri soi, ra Phe Dân. Đêm tiếp theo, kết quả soi của Tiên Tri bị đảo ngược (Dân thành Sói, Sói thành Dân). Phải chọn đáp án đúng trong bài toán cộng/trừ vào ban đêm để được quyền bỏ phiếu.",
    "Wolfman": "Thuộc phe Sói, thức dậy cùng bầy Sói trong wolf-chat và tham gia chọn giết. Được tính là Sói khi kiểm đếm thắng thua. Nếu bị Tiên Tri soi, hiển thị thuộc Phe Dân."
}

# Hàm hỗ trợ
async def generate_math_problem(used_problems):
    max_attempts = 100
    for _ in range(max_attempts):
        num1 = random.randint(1000, 99999)
        num2 = random.randint(1000, 99999)
        operation = random.choice(['+', '-'])
        problem = f"{num1} {operation} {num2}"
        if problem not in used_problems:
            answer = num1 + num2 if operation == '+' else num1 - num2
            if answer < 1000:  # Đảm bảo đáp án đủ lớn
                continue
            possible_wrong = []
            for offset in range(-1000, 1001, 100):
                wrong = answer + offset
                if wrong != answer and wrong >= 0:
                    possible_wrong.append(wrong)
            if len(possible_wrong) < 2:
                continue
            wrong1, wrong2 = random.sample(possible_wrong, 2)
            options = [answer, wrong1, wrong2]
            random.shuffle(options)
            return {"problem": problem, "answer": answer, "options": options}
    raise ValueError("Unable to generate unique math problem after maximum attempts")

async def setup_dead_channel(guild):
    dead_channel = discord.utils.get(guild.text_channels, name="dead-chat")
    if not dead_channel:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        dead_channel = await guild.create_text_channel("dead-chat", overwrites=overwrites)
        logger.info(f"Created dead-chat: channel_id={dead_channel.id}, permissions={overwrites}")
    else:
        await dead_channel.set_permissions(guild.default_role, read_messages=False, send_messages=False)
        logger.info(f"Updated dead-chat permissions: channel_id={dead_channel.id}, default_role=read_messages:False,send_messages:False")
    game_state["dead_channel"] = dead_channel
    return dead_channel

async def setup_wolf_channel(guild):
    wolf_channel = discord.utils.get(guild.text_channels, name="wolf-chat")
    if not wolf_channel:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        wolf_channel = await guild.create_text_channel("wolf-chat", overwrites=overwrites)
        logger.info(f"Created wolf-chat: channel_id={wolf_channel.id}, permissions={overwrites}")
    else:
        await wolf_channel.set_permissions(guild.default_role, read_messages=False, send_messages=False)
        logger.info(f"Updated wolf-chat permissions: channel_id={wolf_channel.id}, default_role=read_messages:False,send_messages:False")
    game_state["wolf_channel"] = wolf_channel
    return wolf_channel

async def countdown(channel, seconds, phase):
    if seconds >= 5:
        await asyncio.sleep(seconds - 5)
        for i in range(5, 0, -1):
            await channel.send(f"Còn {i} giây để {phase}!")
            await asyncio.sleep(1)
    else:
        await channel.send(f"Pha {phase} kết thúc!")

async def check_win_condition(ctx):
    if not game_state["is_game_running"]:
        logger.info("check_win_condition: Game is not running, skipping win condition check")
        return False

    werewolves = 0
    villagers = 0
    for data in game_state["players"].values():
        if data["status"] in ["alive", "wounded"]:
            if data["role"] in WEREWOLF_ROLES and data["role"] != "Illusionist":
                werewolves += 1
            elif data["role"] in VILLAGER_ROLES or data["role"] == "Illusionist":
                villagers += 1

    if werewolves == 0 and villagers > 0:
        game_log.append("Game kết thúc: Phe Dân thắng vì tất cả Sói đã bị tiêu diệt.")
        await ctx.send("Phe Dân đã thắng! Tất cả Sói đã bị tiêu diệt!")
        await reset_game_logic(ctx)
        return True
    elif werewolves >= villagers and werewolves > 0:
        game_log.append("Game kết thúc: Phe Sói thắng vì số Sói bằng hoặc vượt số Dân.")
        await ctx.send("Phe Sói đã thắng! Số Sói còn sống bằng hoặc vượt số Dân!")
        await reset_game_logic(ctx)
        return True
    return False

async def get_alive_players(ctx):
    if not game_state["member_cache"]:
        game_state["member_cache"] = {m.id: m for m in await retry_api_call(lambda: ctx.guild.members)}
    alive_players = []
    for user_id, data in game_state["players"].items():
        if data["status"] in ["alive", "wounded"]:
            member = game_state["member_cache"].get(user_id)
            if member:
                alive_players.append(member)
    return alive_players

async def retry_api_call(func, max_attempts=5, initial_delay=2):
    attempt = 1
    delay = initial_delay
    while attempt <= max_attempts:
        try:
            result = func()
            if inspect.iscoroutine(result):
                return await result
            return result
        except discord.errors.HTTPException as e:
            if e.status == 429:
                logger.warning(f"Rate limit hit, attempt {attempt}/{max_attempts}, retrying in {delay}s")
                await asyncio.sleep(delay)
                attempt += 1
                delay *= 2
            else:
                raise e
        except Exception as e:
            logger.error(f"API call failed: {str(e)}, attempt={attempt}")
            if attempt == max_attempts:
                raise e
            await asyncio.sleep(delay)
            attempt += 1
            delay *= 2
    raise discord.errors.HTTPException(response=None, message="Max retries exceeded for API call")

# View cho lựa chọn kênh voice
class VoiceChannelView(discord.ui.View):
    def __init__(self, guild, admin_id):
        super().__init__(timeout=180)
        self.add_item(VoiceChannelSelect(guild, admin_id))

class VoiceChannelSelect(discord.ui.Select):
    def __init__(self, guild, admin_id):
        voice_channels = [ch for ch in guild.voice_channels if ch.members]
        options = [
            discord.SelectOption(label=ch.name, value=str(ch.id))
            for ch in voice_channels[:25]
        ]
        super().__init__(placeholder="Chọn kênh voice", options=options, min_values=1, max_values=1)
        self.guild = guild
        self.admin_id = admin_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh !start_game được thao tác!", ephemeral=True)
            return
        await interaction.response.defer()
        await asyncio.sleep(1)
        voice_channel_id = int(self.values[0])
        voice_channel = self.guild.get_channel(voice_channel_id)
        if not voice_channel or not voice_channel.members:
            await interaction.followup.send("Kênh voice này không có người hoặc không tồn tại!", ephemeral=True)
            return
        game_state["voice_channel_id"] = voice_channel_id
        game_state["guild_id"] = self.guild.id
        await interaction.followup.send(
            f"Đã chọn kênh voice {voice_channel.name}. Chọn số lượng người chơi (tối thiểu 4, tối đa {len(voice_channel.members)}):",
            view=PlayerCountView(len(voice_channel.members), self.admin_id),
            ephemeral=True
        )

# View cho lựa chọn số lượng người chơi
class PlayerCountView(discord.ui.View):
    def __init__(self, max_players, admin_id):
        super().__init__(timeout=180)
        self.add_item(PlayerCountSelect(max_players, admin_id))

class PlayerCountSelect(discord.ui.Select):
    def __init__(self, max_players, admin_id):
        options = [
            discord.SelectOption(label=str(i), value=str(i))
            for i in range(4, min(max_players + 1, 26))
        ]
        super().__init__(placeholder="Chọn số lượng người chơi", options=options, min_values=1, max_values=1)
        self.admin_id = admin_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh !start_game được thao tác!", ephemeral=True)
            return
        await interaction.response.defer()
        await asyncio.sleep(1)
        game_state["temp_player_count"] = int(self.values[0])
        voice_channel = interaction.guild.get_channel(game_state["voice_channel_id"])
        if not voice_channel or len(voice_channel.members) < game_state["temp_player_count"]:
            await interaction.followup.send("Số người trong kênh voice không đủ cho số lượng đã chọn!", ephemeral=True)
            return
        await interaction.followup.send(
            f"Đã chọn {game_state['temp_player_count']} người chơi. Chọn danh sách người chơi:",
            view=PlayerSelectView(interaction.guild, interaction.user.id),
            ephemeral=True
        )

# View cho lựa chọn người chơi
class PlayerSelectView(discord.ui.View):
    def __init__(self, guild, admin_id):
        super().__init__(timeout=180)
        self.add_item(PlayerSelect(guild, admin_id))

class PlayerSelect(discord.ui.Select):
    def __init__(self, guild, admin_id):
        voice_channel = guild.get_channel(game_state["voice_channel_id"])
        logger.info(f"Initializing PlayerSelect: voice_channel_id={game_state.get('voice_channel_id')}, voice_channel={voice_channel}, guild_id={guild.id}")
        members = voice_channel.members[:25] if voice_channel and hasattr(voice_channel, 'members') else []
        if not members:
            options = [discord.SelectOption(label="Không có người chơi", value="none")]
            logger.warning(f"No members in voice channel: ID={game_state.get('voice_channel_id')}, voice_channel={voice_channel}")
        else:
            options = []
            for member in members:
                voice_state = member.voice
                mute_status = voice_state.mute if voice_state else False
                self_mute_status = voice_state.self_mute if voice_state else False
                voice_channel_info = voice_state.channel if voice_state else None
                logger.info(f"Player in dropdown: ID={member.id}, DisplayName={repr(member.display_name)}, Name={repr(member.name)}, Mute={mute_status}, SelfMute={self_mute_status}, VoiceChannel={voice_channel_info}")
                try:
                    options.append(discord.SelectOption(label=member.display_name, value=str(member.id)))
                except Exception as e:
                    logger.error(f"Error creating SelectOption for player ID={member.id}, DisplayName={repr(member.display_name)}, error={str(e)}")
                    continue
        super().__init__(
            placeholder="Chọn người chơi",
            options=options,
            min_values=game_state["temp_player_count"] if members else 1,
            max_values=game_state["temp_player_count"] if members else 1
        )
        self.admin_id = admin_id
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message("Chỉ người chạy lệnh !start_game được thao tác!", ephemeral=True)
            return
        await interaction.response.defer()
        await asyncio.sleep(5)
        try:
            voice_channel_id = game_state.get("voice_channel_id")
            if not voice_channel_id:
                logger.error(f"No voice_channel_id in game_state, interaction_id={interaction.id}, game_state={game_state}")
                await interaction.followup.send("Lỗi: Không tìm thấy ID kênh voice. Vui lòng chạy lại !start_game!", ephemeral=True)
                return
            voice_channel = self.guild.get_channel(voice_channel_id)
            logger.info(f"Fetched voice channel: ID={voice_channel_id}, Result={voice_channel}, guild_id={self.guild.id}")
            if not voice_channel:
                logger.error(f"Voice channel not found: ID={voice_channel_id}, interaction_id={interaction.id}")
                await interaction.followup.send("Lỗi: Kênh voice không tồn tại. Vui lòng chạy lại !start_game!", ephemeral=True)
                return
            if not isinstance(voice_channel, discord.VoiceChannel):
                logger.error(f"Invalid voice channel type: ID={voice_channel_id}, type={type(voice_channel)}, interaction_id={interaction.id}")
                await interaction.followup.send("Lỗi: Kênh voice không hợp lệ. Vui lòng chạy lại !start_game!", ephemeral=True)
                return
            logger.info(f"Voice channel confirmed: ID={voice_channel.id}, Name={voice_channel.name}, Permissions={voice_channel.permissions_for(self.guild.me)}")
            current_members = await retry_api_call(lambda: {m.id: m for m in voice_channel.members if m}, max_attempts=5, initial_delay=2)
            logger.info(f"Voice channel members: { {k: v.display_name for k, v in current_members.items()} }, count={len(current_members)}")
            if not current_members:
                logger.error(f"No members in voice channel: ID={voice_channel_id}, interaction_id={interaction.id}")
                await interaction.followup.send("Lỗi: Kênh voice không có người chơi nào! Vui lòng kiểm tra và thử lại.", ephemeral=True)
                return
            if "none" in self.values:
                logger.error(f"No players available in voice channel, interaction_id={interaction.id}")
                await interaction.followup.send("Không có người chơi trong kênh voice!", ephemeral=True)
                return
            logger.info(f"Refreshing guild members cache, guild_id={self.guild.id}, interaction_id={interaction.id}")
            game_state["member_cache"] = {m.id: m for m in await retry_api_call(lambda: self.guild.members, max_attempts=5, initial_delay=2)}
            logger.info(f"Guild members cache refreshed, interaction_id={interaction.id}")
            selected_ids = []
            for id_str in self.values:
                try:
                    user_id = int(id_str)
                    if user_id not in current_members:
                        logger.warning(f"Player ID={user_id} not in voice channel, interaction_id={interaction.id}")
                        await interaction.followup.send(f"Một người chơi (ID: {id_str}) đã rời kênh voice! Vui lòng chọn lại.", ephemeral=True)
                        return
                    member = game_state["member_cache"].get(user_id)
                    if not member or not isinstance(member, discord.Member):
                        logger.error(f"Failed to fetch member: ID={user_id}, member={member}, interaction_id={interaction.id}")
                        await interaction.followup.send(f"Không tìm thấy người chơi với ID {id_str}! Có thể họ đã rời server.", ephemeral=True)
                        return
                    voice_state = member.voice
                    if not voice_state or not voice_state.channel or voice_state.channel.id != voice_channel_id:
                        logger.error(f"Player ID={user_id} has invalid voice state: voice={voice_state}, channel={voice_state.channel if voice_state else None}, interaction_id={interaction.id}")
                        await interaction.followup.send(f"Người chơi {member.display_name} không còn trong kênh voice hợp lệ!", ephemeral=True)
                        return
                    mute_status = voice_state.mute if voice_state else False
                    self_mute_status = voice_state.self_mute if voice_state else False
                    is_admin = member.guild_permissions.administrator
                    logger.info(f"Selected player: ID={user_id}, DisplayName={repr(member.display_name)}, Name={repr(member.name)}, IsAdmin={is_admin}, Mute={mute_status}, SelfMute={self_mute_status}, VoiceChannel={voice_state.channel}, Permissions={member.guild_permissions}")
                    selected_ids.append(user_id)
                except ValueError as ve:
                    logger.error(f"Invalid ID in PlayerSelect: {id_str}, error={str(ve)}, interaction_id={interaction.id}")
                    await interaction.followup.send("Lỗi: ID người chơi không hợp lệ!", ephemeral=True)
                    return
                except Exception as e:
                    logger.error(f"Error processing player ID={id_str}, error={str(e)}, interaction_id={interaction.id}, traceback={traceback.format_exc()}")
                    await interaction.followup.send(f"Lỗi khi xử lý người chơi ID {id_str}. Vui lòng thử lại!", ephemeral=True)
                    return
            logger.info(f"Selected players: {selected_ids}, count={len(selected_ids)}, expected={game_state['temp_player_count']}, interaction_id={interaction.id}")
            if len(selected_ids) != game_state["temp_player_count"]:
                await interaction.followup.send(
                    f"Vui lòng chọn đúng {game_state['temp_player_count']} người chơi! Đã chọn: {len(selected_ids)}",
                    ephemeral=True
                )
                return
            game_state["temp_players"] = selected_ids
            logger.info(f"Proceeding to role selection, interaction_id={interaction.id}")
            await interaction.followup.send(
                f"Đã chọn {len(game_state['temp_players'])} người chơi. Chọn số lượng Sói, Dân Làng và vai đặc biệt (tổng phải bằng {game_state['temp_player_count']}):",
                view=RoleSelectView(interaction.user.id),
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Unexpected error in PlayerSelect.callback: error={str(e)}, interaction_id={interaction.id}, traceback={traceback.format_exc()}")
            await interaction.followup.send("Lỗi không xác định khi xử lý lựa chọn người chơi. Vui lòng thử lại!", ephemeral=True)

# View cho lựa chọn vai trò
class RoleSelectView(discord.ui.View):
    def __init__(self, admin_id):
        super().__init__(timeout=180)
        self.admin_id = admin_id
        logger.info(f"Initializing RoleSelectView: admin_id={admin_id}, temp_player_count={game_state['temp_player_count']}, temp_roles={game_state['temp_roles']}")
        self.add_item(WerewolfCountSelect())
        self.add_item(VillagerCountSelect())
        self.add_item(VillagerSpecialRoleSelect())
        self.add_item(WerewolfSpecialRoleSelect())
        self.add_item(ConfirmButton())
        self.add_item(ResetRolesButton())

class WerewolfCountSelect(discord.ui.Select):
    def __init__(self):
        total_roles = sum(game_state["temp_roles"].values())
        remaining = game_state["temp_player_count"] - total_roles
        options = [
            discord.SelectOption(label=str(i), value=str(i))
            for i in range(0, min(remaining + game_state["temp_roles"]["Werewolf"] + 1, game_state["temp_player_count"] + 1))
        ]
        super().__init__(
            placeholder=f"Chọn số lượng Sói (hiện tại: {game_state['temp_roles']['Werewolf']})",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != game_state["temp_admin_id"]:
            await interaction.response.send_message("Chỉ người chạy lệnh !start_game được thao tác!", ephemeral=True)
            return
        await interaction.response.defer()
        await asyncio.sleep(1)
        count = int(self.values[0])
        game_state["temp_roles"]["Werewolf"] = count
        total_roles = sum(game_state["temp_roles"].values())
        remaining = game_state["temp_player_count"] - total_roles
        logger.info(f"Werewolf count selected: count={count}, total_roles={total_roles}, remaining={remaining}, interaction_id={interaction.id}")
        role_summary = "\n".join([f"{role}: {count}" for role, count in game_state["temp_roles"].items()])
        await interaction.followup.send(
            f"Đã chọn {count} Sói. Tổng vai: {total_roles}/{game_state['temp_player_count']} (còn {remaining}).\n"
            f"Trạng thái vai trò:\n{role_summary}\n"
            f"Chọn số lượng Sói, Dân Làng hoặc vai đặc biệt tiếp theo, hoặc nhấn Xác nhận nếu đủ.",
            view=RoleSelectView(self.view.admin_id),
            ephemeral=True
        )

class VillagerCountSelect(discord.ui.Select):
    def __init__(self):
        total_roles = sum(game_state["temp_roles"].values())
        remaining = game_state["temp_player_count"] - total_roles
        options = [
            discord.SelectOption(label=str(i), value=str(i))
            for i in range(0, min(remaining + game_state["temp_roles"]["Villager"] + 1, game_state["temp_player_count"] + 1))
        ]
        super().__init__(
            placeholder=f"Chọn số lượng Dân Làng (hiện tại: {game_state['temp_roles']['Villager']})",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != game_state["temp_admin_id"]:
            await interaction.response.send_message("Chỉ người chạy lệnh !start_game được thao tác!", ephemeral=True)
            return
        await interaction.response.defer()
        await asyncio.sleep(1)
        count = int(self.values[0])
        game_state["temp_roles"]["Villager"] = count
        total_roles = sum(game_state["temp_roles"].values())
        remaining = game_state["temp_player_count"] - total_roles
        logger.info(f"Villager count selected: count={count}, total_roles={total_roles}, remaining={remaining}, interaction_id={interaction.id}")
        role_summary = "\n".join([f"{role}: {count}" for role, count in game_state["temp_roles"].items()])
        await interaction.followup.send(
            f"Đã chọn {count} Dân Làng. Tổng vai: {total_roles}/{game_state['temp_player_count']} (còn {remaining}).\n"
            f"Trạng thái vai trò:\n{role_summary}\n"
            f"Chọn số lượng Sói, Dân Làng hoặc vai đặc biệt tiếp theo, hoặc nhấn Xác nhận nếu đủ.",
            view=RoleSelectView(self.view.admin_id),
            ephemeral=True
        )

class VillagerSpecialRoleSelect(discord.ui.Select):
    def __init__(self):
        total_roles = sum(game_state["temp_roles"].values())
        remaining = game_state["temp_player_count"] - total_roles
        options = []
        for role in VILLAGER_SPECIAL_ROLES:
            if game_state["temp_roles"][role] == 0 and remaining > 0:
                options.append(discord.SelectOption(label=role, value=role))
        if not options:
            options.append(discord.SelectOption(label="Không còn vai đặc biệt Phe Dân", value="none"))
        super().__init__(
            placeholder=f"Chọn vai đặc biệt Phe Dân (còn {remaining} vai)",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != game_state["temp_admin_id"]:
            await interaction.response.send_message("Chỉ người chạy lệnh !start_game được thao tác!", ephemeral=True)
            return
        await interaction.response.defer()
        await asyncio.sleep(1)
        if self.values[0] == "none":
            await interaction.followup.send("Không còn vai đặc biệt Phe Dân để chọn! Chọn vai khác hoặc nhấn Xác nhận.", ephemeral=True)
            return
        role = self.values[0]
        game_state["temp_roles"][role] = 1
        total_roles = sum(game_state["temp_roles"].values())
        remaining = game_state["temp_player_count"] - total_roles
        logger.info(f"Villager special role selected: role={role}, count=1, total_roles={total_roles}, remaining={remaining}, interaction_id={interaction.id}")
        role_summary = "\n".join([f"{r}: {count}" for r, count in game_state["temp_roles"].items()])
        await interaction.followup.send(
            f"Đã chọn 1 {role} (Phe Dân). Tổng vai: {total_roles}/{game_state['temp_player_count']} (còn {remaining}).\n"
            f"Trạng thái vai trò:\n{role_summary}\n"
            f"Chọn số lượng Sói, Dân Làng hoặc vai đặc biệt tiếp theo, hoặc nhấn Xác nhận nếu đủ.",
            view=RoleSelectView(self.view.admin_id),
            ephemeral=True
        )

class WerewolfSpecialRoleSelect(discord.ui.Select):
    def __init__(self):
        total_roles = sum(game_state["temp_roles"].values())
        remaining = game_state["temp_player_count"] - total_roles
        options = []
        for role in WEREWOLF_SPECIAL_ROLES:
            if game_state["temp_roles"][role] == 0 and remaining > 0:
                options.append(discord.SelectOption(label=role, value=role))
        if not options:
            options.append(discord.SelectOption(label="Không còn vai đặc biệt Phe Sói", value="none"))
        super().__init__(
            placeholder=f"Chọn vai đặc biệt Phe Sói (còn {remaining} vai)",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != game_state["temp_admin_id"]:
            await interaction.response.send_message("Chỉ người chạy lệnh !start_game được thao tác!", ephemeral=True)
            return
        await interaction.response.defer()
        await asyncio.sleep(1)
        if self.values[0] == "none":
            await interaction.followup.send("Không còn vai đặc biệt Phe Sói để chọn! Chọn vai khác hoặc nhấn Xác nhận.", ephemeral=True)
            return
        role = self.values[0]
        game_state["temp_roles"][role] = 1
        total_roles = sum(game_state["temp_roles"].values())
        remaining = game_state["temp_player_count"] - total_roles
        logger.info(f"Werewolf special role selected: role={role}, count=1, total_roles={total_roles}, remaining={remaining}, interaction_id={interaction.id}")
        role_summary = "\n".joinPink0
        await interaction.followup.send(
            f"Đã chọn 1 {role} (Phe Sói). Tổng vai: {total_roles}/{game_state['temp_player_count']} (còn {remaining}).\n"
            f"Trạng thái vai trò:\n{role_summary}\n"
            f"Chọn số lượng Sói, Dân Làng hoặc vai đặc biệt tiếp theo, hoặc nhấn Xác nhận nếu đủ.",
            view=RoleSelectView(self.view.admin_id),
            ephemeral=True
        )

class ConfirmButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Xác nhận", style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != game_state["temp_admin_id"]:
            await interaction.response.send_message("Chỉ người chạy lệnh !start_game được thao tác!", ephemeral=True)
            return
        await interaction.response.defer()
        await asyncio.sleep(1)
        total_roles = sum(game_state["temp_roles"].values())
        logger.info(f"ConfirmButton clicked: total_roles={total_roles}, expected={game_state['temp_player_count']}, temp_roles={game_state['temp_roles']}, interaction_id={interaction.id}")
        if total_roles != game_state["temp_player_count"]:
            await interaction.followup.send(
                f"Tổng số vai ({total_roles}) không khớp với số người chơi ({game_state['temp_player_count']})!",
                ephemeral=True
            )
            return
        if game_state["temp_roles"]["Werewolf"] + game_state["temp_roles"]["Wolfman"] < 1:
            await interaction.followup.send("Phải có ít nhất 1 Sói hoặc Người Sói!", ephemeral=True)
            return
        if game_state["temp_roles"]["Villager"] < 0:
            await interaction.followup.send("Số Dân Làng không thể âm!", ephemeral=True)
            return
        await start_game_logic(interaction)
        for child in self.view.children:
            child.disabled = True
        await interaction.message.edit(view=self.view)

class ResetRolesButton(discordi.ui.Button):
    def __init__(self):
        super().__init__(label="Reset Roles", style=discord.ButtonStyle.red)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != game_state["temp_admin_id"]:
            await interaction.response.send_message("Chỉ người chạy lệnh !start_game được thao tác!", ephemeral=True)
            return
        await interaction.response.defer()
        await asyncio.sleep(1)
        game_state["temp_roles"] = {role: 0 for role in ROLES}
        logger.info(f"Roles reset: temp_roles={game_state['temp_roles']}, interaction_id={interaction.id}")
        await interaction.followup.send(
            "Đã đặt lại tất cả vai trò! Vui lòng chọn lại Sói, Dân Làng và vai đặc biệt.",
            view=RoleSelectView(self.view.admin_id),
            ephemeral=True
        )

# View cho bài toán ban đêm
class NightMathView(discord.ui.View):
    def __init__(self, user_id, options, correct_answer, timeout=60):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.correct_answer = correct_answer
        for option in options:
            self.add_item(MathAnswerButton(option, option == correct_answer, user_id))

class MathAnswerButton(discord.ui.Button):
    def __init__(self, answer, is_correct, user_id):
        super().__init__(label=str(answer), style=discord.ButtonStyle.primary)
        self.answer = answer
        self.is_correct = is_correct
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Đây không phải bài toán của bạn!", ephemeral=True)
            return
        if game_state["phase"] != "night":
            await interaction.response.send_message("Chưa phải pha đêm!", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("Vui lòng trả lời qua DM!", ephemeral=True)
            return
        if interaction.user.id not in game_state["math_problems"]:
            await interaction.response.send_message("Bạn đã trả lời hoặc không có bài toán!", ephemeral=True)
            return

        if self.is_correct:
            game_state["math_results"][self.user_id] = True
            game_log.append(f"{interaction.user.display_name} chọn đáp án đúng ({self.answer}) cho bài toán.")
            await interaction.response.send_message("Đúng! Bạn đã đủ điều kiện để bỏ phiếu vào ban ngày.", ephemeral=True)
        else:
            game_state["math_results"][self.user_id] = False
            game_log.append(f"{interaction.user.display_name} chọn đáp án sai ({self.answer}) cho bài toán.")
            await interaction.response.send_message("Sai! Bạn sẽ không được bỏ phiếu vào ban ngày.", ephemeral=True)

        del game_state["math_problems"][self.user_id]
        for child in self.view.children:
            child.disabled = True
        await interaction.message.edit(view=self.view)

# Hàm xử lý logic bắt đầu game
async def start_game_logic(interaction):
    ctx = await bot.get_context(interaction.message)
    ctx.author = interaction.user
    voice_channel = bot.get_channel(game_state["voice_channel_id"])

    selected_players = []
    for uid in game_state["temp_players"]:
        member = game_state["member_cache"].get(uid)
        if not member:
            await ctx.send(f"Lỗi: Không tìm thấy người chơi với ID {uid}!")
            return
        selected_players.append(member)

    game_state["voice_channel_id"] = voice_channel.id
    game_state["guild_id"] = ctx.guild.id
    game_state["text_channel"] = ctx.channel
    game_state["witch_has_power"] = game_state["temp_roles"]["Witch"] > 0
    game_state["hunter_has_power"] = game_state["temp_roles"]["Hunter"] > 0
    game_state["is_first_day"] = True
    game_state["illusionist_scanned"] = False
    game_state["illusionist_effect_active"] = False

    wolf_channel = await setup_wolf_channel(ctx.guild)
    game_state["wolf_channel"] = wolf_channel

    roles = []
    for role, count in game_state["temp_roles"].items():
        roles.extend([role] * count)
    random.shuffle(roles)

    role_counts = {role: 0 for role in ROLES}
    game_state["players"] = {}
    illusionist_id = None
    werewolf_ids = []

    for i, member in enumerate(selected_players):
        role = roles[i]
        game_state["players"][member.id] = {"role": role, "status": "alive"}
        role_counts[role] += 1
        await retry_api_call(lambda: member.send(f"Vai của bạn là: **{role}**"))
        if role == "Werewolf":
            await retry_api_call(lambda: wolf_channel.set_permissions(member, read_messages=True, send_messages=True))
            await retry_api_call(lambda: member.send("Bạn là Sói! Thảo luận với đồng đội trong kênh wolf-chat vào pha đêm và chọn mục tiêu bằng nút chọn."))
            werewolf_ids.append(member.id)
        elif role == "Wolfman":
            await retry_api_call(lambda: wolf_channel.set_permissions(member, read_messages=True, send_messages=True))
            await retry_api_call(lambda: member.send("Bạn là Người Sói! Thức dậy cùng bầy Sói trong kênh wolf-chat và chọn mục tiêu bằng nút chọn. Bạn hiển thị là Phe Dân nếu bị Tiên Tri soi."))
            werewolf_ids.append(member.id)
        elif role == "Witch":
            await retry_api_call(lambda: member.send("Bạn là Phù Thủy! Mỗi đêm, bạn sẽ nhận thông báo muộn hơn về người bị giết và có 30 giây để cứu hoặc giết bằng nút chọn."))
        elif role == "Hunter":
            await retry_api_call(lambda: member.send("Bạn là Thợ Săn! Bạn có 60 giây đầu mỗi đêm để chọn người giết bằng nút chọn qua DM."))
        elif role == "Tough Guy":
            await retry_api_call(lambda: member.send("Bạn là Người Cứng Cỏi! Bạn có 2 mạng, phải bị giết 2 lần mới chết hoàn toàn. Không ai biết khi bạn mất mạng. Bạn phải chọn đáp án đúng trong bài toán cộng/trừ vào ban đêm để được quyền bỏ phiếu."))
        elif role == "Illusionist":
            illusionist_id = member.id
            await retry_api_call(lambda: member.send("Bạn là Nhà Ảo Giác! Bạn thuộc phe Sói nhưng không thức dậy trong wolf-chat và không biết ai là Sói. Sói biết bạn là Nhà Ảo Giác. Bạn phải chọn đáp án đúng trong bài toán cộng/trừ vào ban đêm để được quyền bỏ phiếu."))
        elif role == "Villager":
            await retry_api_call(lambda: member.send("Bạn là Dân Làng! Bạn không có chức năng đặc biệt vào ban đêm, nhưng phải chọn đáp án đúng trong bài toán cộng/trừ để được quyền bỏ phiếu vào ban ngày."))

    if illusionist_id:
        illusionist_member = ctx.guild.get_member(illusionist_id)
        for wid in werewolf_ids:
            werewolf_member = ctx.guild.get_member(wid)
            if werewolf_member:
                await retry_api_call(lambda: wolf_channel.send(f"{illusionist_member.display_name} là Nhà Ảo Giác, thuộc phe Sói nhưng không thức dậy cùng các bạn."))

    game_state["is_game_running"] = True
    role_summary = f"Game đã bắt đầu với {len(selected_players)} người chơi: {role_counts['Villager']} Dân Làng, {role_counts['Werewolf']} Sói, {role_counts['Wolfman']} Người Sói"
    for role in VILLAGER_SPECIAL_ROLES + WEREWOLF_SPECIAL_ROLES:
        if role_counts[role] > 0:
            role_summary += f", {role_counts[role]} {role}"
    role_summary += f".\nNgười chơi: {', '.join([m.display_name for m in selected_players if m])}"
    role_summary += "\nĐã gửi vai qua DM. Buổi sáng đầu tiên bắt đầu ngay (30 giây thảo luận, không bỏ phiếu)."
    await ctx.send(role_summary)
    game_log.append(f"Game bắt đầu với {len(selected_players)} người chơi: {', '.join([m.display_name for m in selected_players if m])}")
    await morning_phase(ctx)

# View cho hành động đêm (Tiên Tri, Bảo Vệ, Thợ Săn, Sói)
class NightActionView(discord.ui.View):
    def __init__(self, role, alive_players, timeout):
        super().__init__(timeout=timeout)
        self.role = role
        self.alive_players = alive_players
        self.add_item(PlayerSelectAction(role, alive_players))

class PlayerSelectAction(discord.ui.Select):
    def __init__(self, role, alive_players):
        options = [
            discord.SelectOption(label=member.display_name, value=str(member.id))
            for member in alive_players
        ]
        placeholder = f"Chọn người để {'soi' if role == 'Seer' else 'bảo vệ' if role == 'Guard' else 'giết'}"
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)
        self.role = role
        self.alive_players = alive_players

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in game_state["players"] or game_state["players"][interaction.user.id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Bạn không phải người chơi hoặc đã chết!", ephemeral=True)
            return
        if game_state["players"][interaction.user.id]["role"] not in ["Werewolf", "Wolfman"] and self.role == "Werewolf":
            await interaction.response.send_message(f"Chỉ Sói hoặc Người Sói mới có thể thực hiện hành động này!", ephemeral=True)
            return
        if game_state["players"][interaction.user.id]["role"] != self.role and self.role != "Werewolf":
            await interaction.response.send_message(f"Chỉ {self.role} mới có thể thực hiện hành động này!", ephemeral=True)
            return
        if game_state["phase"] != "night":
            await interaction.response.send_message("Chưa phải pha đêm!", ephemeral=True)
            return
        if self.role in ["Seer", "Guard", "Hunter"] and not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("Vui lòng thực hiện hành động qua DM!", ephemeral=True)
            return
        if self.role == "Werewolf" and interaction.channel != game_state["wolf_channel"]:
            await interaction.response.send_message("Vui lòng thực hiện hành động trong wolf-chat!", ephemeral=True)
            return

        target_id = int(self.values[0])
        if target_id not in game_state["players"] or game_state["players"][target_id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Mục tiêu không hợp lệ!", ephemeral=True)
            return

        target_member = next((m for m in self.alive_players if m.id == target_id), None)
        if not target_member:
            logger.error(f"Target member not found in alive_players: target_id={target_id}, interaction_id={interaction.id}")
            await interaction.response.send_message("Lỗi: Không tìm thấy người chơi mục tiêu!", ephemeral=True)
            return
        target_display_name = target_member.display_name

        logger.info(f"Night action: role={self.role}, target_id={target_id}, target_display_name={target_display_name}, interaction_id={interaction.id}")

        if self.role == "Seer":
            target_role = game_state["players"][target_id]["role"]
            if target_role == "Illusionist":
                game_state["illusionist_scanned"] = True
                game_log.append(f"Tiên Tri soi {target_display_name} và thấy thuộc Phe Dân (do Nhà Ảo Giác).")
                await interaction.response.send_message(f"{target_display_name} thuộc **Phe Dân**", ephemeral=True)
            elif target_role == "Wolfman":
                game_log.append(f"Tiên Tri soi {target_display_name} và thấy thuộc Phe Dân (do Người Sói).")
                await interaction.response.send_message(f"{target_display_name} thuộc **Phe Dân**", ephemeral=True)
            else:
                faction = "Phe Dân" if target_role in VILLAGER_ROLES else "Phe Sói"
                if game_state["illusionist_effect_active"]:
                    faction = "Phe Sói" if faction == "Phe Dân" else "Phe Dân"
                    game_log.append(f"Tiên Tri soi {target_display_name} và thấy thuộc {faction} (do ảnh hưởng Nhà Ảo Giác).")
                else:
                    game_log.append(f"Tiên Tri soi {target_display_name} và thấy thuộc {faction}.")
                await interaction.response.send_message(f"{target_display_name} thuộc **{faction}**", ephemeral=True)
        elif self.role == "Guard":
            game_state["protected_player_id"] = target_id
            game_log.append(f"Bảo Vệ chọn bảo vệ {target_display_name} trong pha đêm.")
            await interaction.response.send_message(f"Bạn đã bảo vệ {target_display_name} đêm nay!", ephemeral=True)
        elif self.role == "Hunter":
            if not game_state["hunter_has_power"]:
                await interaction.response.send_message("Bạn đã sử dụng chức năng!", ephemeral=True)
                return
            game_state["hunter_target_id"] = target_id
            game_log.append(f"Thợ Săn chọn giết {target_display_name} trong pha đêm.")
            await interaction.response.send_message(f"Bạn đã chọn giết {target_display_name}. Kết quả sẽ được công bố khi pha đêm kết thúc.", ephemeral=True)
        elif self.role == "Werewolf":
            game_state["werewolf_target_id"] = target_id
            game_log.append(f"Sói/Người Sói chọn giết {target_display_name} trong pha đêm.")
            await interaction.response.send_message(f"Phe Sói đã chọn giết {target_display_name}. Kết quả sẽ được công bố khi pha đêm kết thúc.", ephemeral=True)

        self.disabled = True
        await interaction.message.edit(view=self.view)

# View cho Phù Thủy
class WitchActionView(discord.ui.View):
    def __init__(self, alive_players, potential_targets, timeout):
        super().__init__(timeout=timeout)
        self.alive_players = alive_players
        self.potential_targets = potential_targets
        self.add_item(WitchSaveSelect(potential_targets))
        self.add_item(WitchKillSelect(alive_players))

class WitchSaveSelect(discord.ui.Select):
    def __init__(self, potential_targets):
        if not potential_targets:
            options = [discord.SelectOption(label="Không cứu", value="none")]
        else:
            options = [
                discord.SelectOption(label=member.display_name, value=str(member.id))
                for member in potential_targets
            ]
        super().__init__(
            placeholder="Chọn người để cứu",
            options=options,
            min_values=1,
            max_values=1
        )
        self.potential_targets = potential_targets

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in game_state["players"] or game_state["players"][interaction.user.id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Bạn không phải người chơi hoặc đã chết!", ephemeral=True)
            return
        if game_state["players"][interaction.user.id]["role"] != "Witch":
            await interaction.response.send_message("Chỉ Phù Thủy mới có thể thực hiện hành động này!", ephemeral=True)
            return
        if game_state["phase"] != "night":
            await interaction.response.send_message("Chưa phải pha đêm!", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("Vui lòng thực hiện hành động qua DM!", ephemeral=True)
            return
        if not game_state["witch_has_power"]:
            await interaction.response.send_message("Bạn đã sử dụng chức năng!", ephemeral=True)
            return

        if self.values[0] == "none":
            await interaction.response.send_message("Bạn đã chọn không cứu ai.", ephemeral=True)
            return

        target_id = int(self.values[0])
        target_member = next((m for m in self.potential_targets if m.id == target_id), None)
        if not target_member:
            logger.error(f"Target member not found in potential_targets: target_id={target_id}, interaction_id={interaction.id}")
            await interaction.response.send_message("Lỗi: Không tìm thấy người chơi mục tiêu!", ephemeral=True)
            return

        game_state["witch_action"]IVAL = "save"
        game_state["witch_target_id"] = target_id
        game_log.append(f"Phù Thủy chọn cứu {target_member.display_name} trong pha đêm.")
        await interaction.response.send_message(f"Bạn đã chọn cứu {target_member.display_name}!", ephemeral=True)

        for child in self.view.children:
            child.disabled = True
        await interaction.message.edit(view=self.view)

class WitchKillSelect(discord.ui.Select):
    def __init__(self, alive_players):
        options = [
            discord.SelectOption(label=member.display_name, value=str(member.id))
            for member in alive_players
        ]
        super().__init__(
            placeholder="Chọn người để giết",
            options=options,
            min_values=1,
            max_values=1
        )
        self.alive_players = alive_players

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in game_state["players"] or game_state["players"][interaction.user.id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Bạn không phải người chơi hoặc đã chết!", ephemeral=True)
            return
        if game_state["players"][interaction.user.id]["role"] != "Witch":
            await interaction.response.send_message("Chỉ Phù Thủy mới có thể thực hiện hành động này!", ephemeral=True)
            return
        if game_state["phase"] != "night":
            await interaction.response.send_message("Chưa phải pha đêm!", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("Vui lòng thực hiện hành động qua DM!", ephemeral=True)
            return
        if not game_state["witch_has_power"]:
            await interaction.response.send_message("Bạn đã sử dụng chức năng!", ephemeral=True)
            return

        target_id = int(self.values[0])
        if target_id in [game_state.get("werewolf_target_id"), game_state.get("hunter_target_id")]:
            await interaction.response.send_message("Bạn không thể giết người đang bị chọn!", ephemeral=True)
            return
        if target_id not in game_state["players"] or game_state["players"][target_id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Mục tiêu không hợp lệ!", ephemeral=True)
            return

        target_member = next((m for m in self.alive_players if m.id == target_id), None)
        if not target_member:
            logger.error(f"Target member not found in alive_players: target_id={target_id}, interaction_id={interaction.id}")
            await interaction.response.send_message("Lỗi: Không tìm thấy người chơi mục tiêu!", ephemeral=True)
            return
        target_display_name = target_member.display_name

        game_state["witch_action"] = "kill"
        game_state["witch_target_id"] = target_id
        game_log.append(f"Phù Thủy chọn giết {target_display_name} trong pha đêm.")
        await interaction.response.send_message(f"Bạn đã chọn giết {target_display_name}!", ephemeral=True)

        for child in self.view.children:
            child.disabled = True
        await interaction.message.edit(view=self.view)

# View cho bỏ phiếu ngày
class VoteView(discord.ui.View):
    def __init__(self, alive_players, timeout):
        super().__init__(timeout=timeout)
        self.add_item(VoteSelect(alive_players))

class VoteSelect(discord.ui.Select):
    def __init__(self, alive_players):
        options = [
            discord.SelectOption(label=member.display_name, value=str(member.id))
            for member in alive_players
        ]
        super().__init__(placeholder="Chọn người để loại", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in game_state["players"] or game_state["players"][interaction.user.id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Bạn không phải người chơi hoặc đã chết!", ephemeral=True)
            return
        if game_state["phase"] != "voting":
            await interaction.response.send_message("Chỉ có thể bỏ phiếu trong pha bỏ phiếu!", ephemeral=True)
            return
        if game_state["is_first_day"]:
            await interaction.response.send_message("Ngày đầu tiên không có bỏ phiếu!", ephemeral=True)
            return
        user_role = game_state["players"][interaction.user.id]["role"]
        if user_role in NO_NIGHT_ACTION_ROLES and (interaction.user.id not in game_state["math_results"] or not game_state["math_results"][interaction.user.id]):
            await interaction.response.send_message("Bạn không chọn đúng đáp án bài toán đêm qua nên không được bỏ phiếu!", ephemeral=True)
            return

        target_id = int(self.values[0])
        if target_id not in game_state["players"] or game_state["players"][target_id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Mục tiêu không hợp lệ!", ephemeral=True)
            return

        target_member = interaction.guild.get_member(target_id)
        if not target_member:
            logger.error(f"Target member not found: target_id={target_id}, interaction_id={interaction.id}")
            await interaction.response.send_message("Lỗi: Không tìm thấy người chơi mục tiêu!", ephemeral=True)
            return

        game_state["votes"][interaction.user.id] = target_id
        game_log.append(f"{interaction.user.display_name} bỏ phiếu loại {target_member.display_name} trong pha bỏ phiếu.")
        await interaction.response.send_message(f"Bạn đã bỏ phiếu loại {target_member.display_name}.", ephemeral=True)
        await interaction.message.edit(view=self.view)

# Hàm pha sáng
async def morning_phase(ctx):
    game_state["phase"] = "morning"
    alive_players = await get_alive_players(ctx)

    if game_state["is_first_day"]:
        await ctx.send("Buổi sáng đầu tiên bắt đầu! Mọi người thảo luận trong 30 giây. Không có bỏ phiếu trong ngày đầu tiên.")
        await countdown(game_state["text_channel"], 30, "thảo luận sáng")
        if alive_players:
            await ctx.send(f"Danh sách người còn sống: {', '.join([p.display_name for p in alive_players])}")
        else:
            await ctx.send("Không còn người chơi nào sống!")
        game_state["is_first_day"] = False
        await night_phase(ctx)
    else:
        # Phase 1: Thảo luận (120 giây)
        await ctx.send("Pha sáng bắt đầu! Mọi người thảo luận trong 120 giây. Sau đó sẽ có 30 giây để bỏ phiếu.")
        await countdown(game_state["text_channel"], 120, "thảo luận sáng")

        # Phase 2: Bỏ phiếu (30 giây)
        game_state["phase"] = "voting"
        await ctx.send("Pha bỏ phiếu bắt đầu! Chọn người để loại bằng nút chọn trong 30 giây.", view=VoteView(alive_players, 30))
        await countdown(game_state["text_channel"], 30, "bỏ phiếu")

        # Xử lý kết quả bỏ phiếu
        vote_counts = {}
        alive_player_ids = [uid for uid, data in game_state["players"].items() if data["status"] in ["alive", "wounded"]]
        abstain_count = len(alive_player_ids)

        for voter_id, target_id in game_state["votes"].items():
            if target_id in game_state["players"] and game_state["players"][target_id]["status"] in ["alive", "wounded"]:
                vote_counts[target_id] = vote_counts.get(target_id, 0) + 1
                abstain_count -= 1

        logger.info(f"Vote results: vote_counts={vote_counts}, abstain_count={abstain_count}, alive_players={len(alive_player_ids)}")

        if not vote_counts:
            game_log.append("Không có phiếu bầu nào. Không ai bị loại trong pha sáng.")
            await ctx.send("Không có phiếu bầu nào. Không ai bị loại trong pha sáng!")
        else:
            max_votes = max(vote_counts.values())
            top_voted = [uid for uid, count in vote_counts.items() if count == max_votes]
            logger.info(f"Top voted: top_voted={top_voted}, max_votes={max_votes}")

            if abstain_count >= max_votes:
                game_log.append(f"Số phiếu bỏ qua ({abstain_count}) bằng hoặc lớn hơn số phiếu cao nhất ({max_votes}). Không ai bị loại.")
                await ctx.send(f"Số phiếu bỏ qua ({abstain_count}) bằng hoặc lớn hơn số phiếu cao nhất ({max_votes}). Không ai bị loại!")
            else:
                if len(top_voted) > 1:
                    target_id = random.choice(top_voted)
                    game_log.append(f"Có {len(top_voted)} người hòa phiếu với {max_votes} phiếu. Random chọn để loại.")
                    await ctx.send(f"Có {len(top_voted)} người hòa phiếu với {max_votes} phiếu. Random chọn để loại!")
                else:
                    target_id = top_voted[0]

                target_data = game_state["players"][target_id]
                member = game_state["member_cache"].get(target_id)
                if target_data["role"] == "Tough Guy" and target_data["status"] == "alive":
                    target_data["status"] = "wounded"
                    game_log.append(f"Người Cứng Cỏi {member.display_name} bị dân làng loại và mất một mạng (còn 1 mạng).")
                else:
                    target_data["status"] = "dead"
                    voice_channel = bot.get_channel(game_state["voice_channel_id"])
                    if voice_channel and member and member in voice_channel.members:
                        await retry_api_call(lambda: member.edit(mute=True))
                    dead_channel = await setup_dead_channel(ctx.guild)
                    await retry_api_call(lambda: dead_channel.set_permissions(member, read_messages=True, send_messages=True))
                    game_log.append(f"{member.display_name} bị dân làng loại với {max_votes} phiếu.")
                    await ctx.send(f"{member.display_name} đã bị dân làng loại với {max_votes} phiếu!")

        if alive_players:
            await ctx.send(f"Danh sách người còn sống: {', '.join([p.display_name for p in alive_players])}")
        else:
            await ctx.send("Không còn người chơi nào sống!")

        if await check_win_condition(ctx):
            return

        await night_phase(ctx)

# Hàm pha đêm
async def night_phase(ctx):
    game_state["phase"] = "night"
    game_state["werewolf_target_id"] = None
    game_state["protected_player_id"] = None
    game_state["witch_target_id"] = None
    game_state["witch_action"] = None
    game_state["hunter_target_id"] = None
    game_state["math_problems"] = {}
    game_state["math_results"] = {}
    if game_state["illusionist_scanned"]:
        game_state["illusionist_effect_active"] = True
        game_state["illusionist_scanned"] = False
        game_log.append("Nhà Ảo Giác khiến kết quả soi của Tiên Tri bị đảo ngược trong đêm này.")

    wolf_channel = game_state["wolf_channel"]
    alive_players = await get_alive_players(ctx)
    used_math_problems = set()

    role_message = "Pha đêm bắt đầu! "
    if any(data["role"] == "Seer" for data in game_state["players"].values()):
        role_message += "Tiên Tri, "
    if any(data["role"] == "Guard" for data in game_state["players"].values()):
        role_message += "Bảo Vệ, "
    if any(data["role"] == "Hunter" for data in game_state["players"].values()):
        role_message += "Thợ Săn, "
    if any(data["role"] in NO_NIGHT_ACTION_ROLES for data in game_state["players"].values()):
        role_message += "Dân Làng/Người Cứng Cỏi/Nhà Ảo Giác, "
    role_message += "kiểm tra DM để thực hiện hành động. Sói và Người Sói, chọn mục tiêu trong wolf-chat. Thời gian: 90 giây."
    await ctx.send(role_message)

    if any(data["role"] in ["Werewolf", "Wolfman"] for data in game_state["players"].values()):
        await wolf_channel.send("Sói và Người Sói ơi, chọn người để giết!", view=NightActionView("Werewolf", alive_players, 60))

    for user_id, data in game_state["players"].items():
        if data["status"] not in ["alive", "wounded"]:
            continue
        member = game_state["member_cache"].get(user_id)
        if not member:
            continue
        if data["role"] == "Seer":
            await retry_api_call(lambda: member.send("Bạn là Tiên Tri! Chọn người để soi:", view=NightActionView("Seer", alive_players, 60)))
        elif data["role"] == "Guard":
            await retry_api_call(lambda: member.send("Bạn là Bảo Vệ! Chọn người để bảo vệ:", view=NightActionView("Guard", alive_players, 60)))
        elif data["role"] == "Hunter" and game_state["hunter_has_power"]:
            await retry_api_call(lambda: member.send("Bạn là Thợ Săn! Chọn người để giết:", view=NightActionView("Hunter", alive_players, 60)))
        elif data["role"] == "Witch" and game_state["witch_has_power"]:
            await retry_api_call(lambda: member.send("Bạn là Phù Thủy! Vui lòng chờ 60 giây để nhận thông báo về người bị giết."))
        elif data["role"] in NO_NIGHT_ACTION_ROLES:
            try:
                async with asyncio.timeout(1):  # Giới hạn 1 giây
                    math_problem = await generate_math_problem(used_math_problems)
                used_math_problems.add(math_problem["problem"])
                game_state["math_problems"][user_id] = math_problem
                game_state["math_results"][user_id] = False
                options_str = "\n".join([f"{i+1}. {option}" for i, option in enumerate(math_problem["options"])])
                game_log.append(f"Gửi bài toán cho {member.display_name} ({data['role']}): {math_problem['problem']}, đáp án: {math_problem['answer']}")
                await retry_api_call(lambda: member.send(
                    f"Bạn phải giải bài toán sau để được quyền bỏ phiếu vào ban ngày: **{math_problem['problem']}**.\n"
                    f"Chọn đáp án đúng trong 60 giây:\n{options_str}",
                    view=NightMathView(user_id, math_problem["options"], math_problem["answer"])
                ))
            except asyncio.TimeoutError:
                logger.error(f"Timeout generating math problem for user_id={user_id}")
                await retry_api_call(lambda: member.send("Lỗi: Không thể tạo bài toán. Bạn không cần giải bài toán đêm nay và được quyền bỏ phiếu."))
                game_state["math_results"][user_id] = True
            except ValueError as e:
                logger.error(f"Failed to generate unique math problem for user_id={user_id}: {str(e)}")
                await retry_api_call(lambda: member.send("Lỗi: Không thể tạo bài toán. Bạn không cần giải bài toán đêm nay và được quyền bỏ phiếu."))
                game_state["math_results"][user_id] = True

    await countdown(game_state["text_channel"], 60, "hành động đêm")

    # Xác định những người sẽ thực sự chết sau khi áp dụng bảo vệ
    potential_targets = []
    target_ids = set()

    # Kiểm tra mục tiêu của Sói
    if (game_state["werewolf_target_id"] and 
        game_state["werewolf_target_id"] != game_state["protected_player_id"]):
        target = game_state["member_cache"].get(game_state["werewolf_target_id"])
        if target and game_state["players"].get(target.id, {}).get("status") in ["alive", "wounded"]:
            potential_targets.append(target)
            target_ids.add(target.id)

    # Kiểm tra mục tiêu của Thợ Săn
    if (game_state["hunter_target_id"] and 
        game_state["hunter_target_id"] != game_state["protected_player_id"]):
        target = game_state["member_cache"].get(game_state["hunter_target_id"])
        if target and game_state["players"].get(target.id, {}).get("status") in ["alive", "wounded"]:
            potential_targets.append(target)
            target_ids.add(target.id)

    # Gửi thông báo cho Phù Thủy chỉ về những người sẽ chết
    if game_state["witch_has_power"]:
        for user_id, data in game_state["players"].items():
            if data["role"] == "Witch" and data["status"] in ["alive", "wounded"]:
                member = game_state["member_cache"].get(user_id)
                if member:
                    if potential_targets:
                        target_names = ", ".join([t.display_name for t in potential_targets])
                        await retry_api_call(lambda: member.send(
                            f"Đêm nay, {target_names} sẽ bị giết. Chọn hành động trong 30 giây:",
                            view=WitchActionView(alive_players, potential_targets, timeout=30)
                        ))
                    else:
                        await retry_api_call(lambda: member.send(
                            "Không ai bị giết đêm nay! Chọn người để giết nếu muốn (30 giây):",
                            view=WitchActionView(alive_players, [], timeout=30)
                        ))
                break

    await countdown(game_state["text_channel"], 30, "đêm")

    dead_players = []

    # Xử lý hành động của Phù Thủy
    if game_state["witch_has_power"] and game_state["witch_action"]:
        if game_state["witch_action"] == "save" and game_state["witch_target_id"] in target_ids:
            if game_state["witch_target_id"] == game_state["werewolf_target_id"]:
                game_state["werewolf_target_id"] = None
            if game_state["witch_target_id"] == game_state["hunter_target_id"]:
                game_state["hunter_target_id"] = None
            game_state["witch_has_power"] = False
            for user_id, data in game_state["players"].items():
                if data["role"] == "Witch" and data["status"] in ["alive", "wounded"]:
                    member = game_state["member_cache"].get(user_id)
                    if member:
                        await retry_api_call(lambda: member.send("Bạn đã cứu một người! Bạn không còn chức năng và sẽ không nhận thông báo nữa."))
                    break
        elif game_state["witch_action"] == "kill" and game_state["witch_target_id"]:
            target_id = game_state["witch_target_id"]
            if (target_id in game_state["players"] and 
                game_state["players"][target_id]["status"] in ["alive", "wounded"] and 
                target_id != game_state["protected_player_id"]):
                target_data = game_state["players"][target_id]
                member = game_state["member_cache"].get(target_id)
                if target_data["role"] == "Tough Guy" and target_data["status"] == "alive":
                    target_data["status"] = "wounded"
                    game_log.append(f"Người Cứng Cỏi {member.display_name} bị Phù Thủy giết và mất một mạng (còn 1 mạng).")
                else:
                    target_data["status"] = "dead"
                    voice_channel = bot.get_channel(game_state["voice_channel_id"])
                    if voice_channel and member and member in voice_channel.members:
                        await retry_api_call(lambda: member.edit(mute=True))
                    dead_channel = await setup_dead_channel(ctx.guild)
                    await retry_api_call(lambda: dead_channel.set_permissions(member, read_messages=True, send_messages=True))
                    await retry_api_call(lambda: dead_channel.send(f"{member.mention} đã tham gia kênh người chết! Chào mừng đến với nghĩa địa!"))
                    dead_players.append(member.display_name)
                    game_log.append(f"{member.display_name} bị Phù Thủy giết và đã chết.")
                game_state["witch_has_power"] = False
                for user_id, data in game_state["players"].items():
                    if data["role"] == "Witch" and data["status"] in ["alive", "wounded"]:
                        member = game_state["member_cache"].get(user_id)
                        if member:
                            await retry_api_call(lambda: member.send("Bạn đã giết một người! Bạn không còn chức năng và sẽ không nhận thông báo nữa."))
                        break

    # Xử lý mục tiêu của Sói
    if (game_state["werewolf_target_id"] and 
        game_state["werewolf_target_id"] != game_state["protected_player_id"]):
        target_id = game_state["werewolf_target_id"]
        target_data = game_state["players"].get(target_id)
        if target_data and target_data["status"] in ["alive", "wounded"]:
            member = game_state["member_cache"].get(target_id)
            if target_data["role"] == "Tough Guy" and target_data["status"] == "alive":
                target_data["status"] = "wounded"
                game_log.append(f"Người Cứng Cỏi {member.display_name} bị Sói giết và mất một mạng (còn 1 mạng).")
            else:
                target_data["status"] = "dead"
                voice_channel = bot.get_channel(game_state["voice_channel_id"])
                if voice_channel and member and member in voice_channel.members:
                    await retry_api_call(lambda: member.edit(mute=True))
                dead_channel = await setup_dead_channel(ctx.guild)
                await retry_api_call(lambda: dead_channel.set_permissions(member, read_messages=True, send_messages=True))
                await retry_api_call(lambda: dead_channel.send(f"{member.mention} đã tham gia kênh người chết! Chào mừng đến với nghĩa địa!"))
                dead_players.append(member.display_name)
                game_log.append(f"{member.display_name} bị Sói giết và đã chết.")

    # Xử lý mục tiêu của Thợ Săn
    if (game_state["hunter_target_id"] and 
        game_state["hunter_target_id"] != game_state["protected_player_id"]):
        target_id = game_state["hunter_target_id"]
        target_data = game_state["players"].get(target_id)
        if target_data and target_data["status"] in ["alive", "wounded"]:
            member = game_state["member_cache"].get(target_id)
            if target_data["role"] == "Tough Guy" and target_data["status"] == "alive":
                target_data["status"] = "wounded"
                game_log.append(f"Người Cứng Cỏi {member.display_name} bị Thợ Săn giết và mất một mạng (còn 1 mạng).")
            else:
                target_data["status"] = "dead"
                voice_channel = bot.get_channel(game_state["voice_channel_id"])
                if voice_channel and member and member in voice_channel.members:
                    await retry_api_call(lambda: member.edit(mute=True))
                dead_channel = await setup_dead_channel(ctx.guild)
                await retry_api_call(lambda: dead_channel.set_permissions(member, read_messages=True, send_messages=True))
                await retry_api_call(lambda: dead_channel.send(f"{member.mention} đã tham gia kênh người chết! Chào mừng đến với nghĩa địa!"))
                dead_players.append(member.display_name)
                game_log.append(f"{member.display_name} bị Thợ Săn giết và đã chết.")
                game_state["hunter_has_power"] = False
                for user_id_hunter, data_hunter in game_state["players"].items():
                    if data_hunter["role"] == "Hunter" and data_hunter["status"] in ["alive", "wounded"]:
                        member = game_state["member_cache"].get(user_id_hunter)
                        if member:
                            await retry_api_call(lambda: member.send("Bạn đã giết một người! Bạn không còn chức năng nữa."))
                        break

    messages = []
    if dead_players:
        messages.append(f"{', '.join(dead_players)} đã bị giết!")
    if not messages:
        messages.append("Không ai bị giết trong đêm nay!")

    await ctx.send(" ".join(messages))

    if not game_state["witch_has_power"]:
        for user_id, data in game_state["players"].items():
            if data["role"] == "Witch" and data["status"] in ["alive", "wounded"]:
                member = game_state["member_cache"].get(user_id)
                if member:
                    await retry_api_call(lambda: member.send("Không ai bị giết đêm nay!"))
                break

    if await check_win_condition(ctx):
        return

    await morning_phase(ctx)

# Hàm reset game logic
async def reset_game_logic(ctx):
    if game_state["reset_in_progress"]:
        logger.warning(f"Reset already in progress, ignoring reset request by {ctx.author.id}")
        await ctx.send("Đang thực hiện reset, vui lòng chờ!")
        return

    if not game_state["is_game_running"]:
        logger.info(f"No game running to reset, requested by {ctx.author.id}")
        await ctx.send("Chưa có game nào để reset!")
        return

    game_state["reset_in_progress"] = True
    logger.info(f"Resetting game: is_game_running={game_state['is_game_running']}, guild_id={game_state.get('guild_id')}, voice_channel_id={game_state.get('voice_channel_id')}, players={list(game_state['players'].keys())}")

    # Gửi log hoạt động
    if game_log:
        embed = discord.Embed(title="Log Hoạt Động Vai Trò", color=discord.Color.blue())
        for entry in game_log:
            embed.add_field(name="Hành động", value=entry, inline=False)
        role_list = []
        for user_id, data in game_state["players"].items():
            member = game_state["member_cache"].get(user_id)
            if member:
                role_list.append(f"{member.display_name}: {data['role']} ({data['status']})")
        embed.add_field(name="Danh sách vai trò", value="\n".join(role_list) if role_list else "Không có người chơi", inline=False)
        embed.set_footer(text=f"Log được gửi bởi {ctx.author.name}")
        await ctx.send(embed=embed)
    else:
        await ctx.send("Không có hoạt động nào được ghi lại trong game.")

    dead_channel = game_state["dead_channel"] or discord.utils.get(ctx.guild.text_channels, name="dead-chat")
    wolf_channel = game_state["wolf_channel"] or discord.utils.get(ctx.guild.text_channels, name="wolf-chat")
    voice_channel = bot.get_channel(game_state["voice_channel_id"])

    # Sử dụng hàng đợi để xử lý API call tuần tự
    api_queue = deque()

    for user_id in game_state["players"]:
        member = game_state["member_cache"].get(user_id)
        if member:
            if dead_channel:
                api_queue.append(lambda: dead_channel.set_permissions(member, read_messages=False, send_messages=False))
            if wolf_channel:
                api_queue.append(lambda: wolf_channel.set_permissions(member, read_messages=False, send_messages=False))
            if voice_channel and member in voice_channel.members:
                api_queue.append(lambda: member.edit(mute=False))

    # Xóa kênh
    if dead_channel:
        api_queue.append(lambda: dead_channel.delete())
    if wolf_channel:
        api_queue.append(lambda: wolf_channel.delete())

    # Xử lý hàng đợi
    errors = []
    while api_queue:
        api_call = api_queue.popleft()
        try:
            await retry_api_call(api_call)
        except Exception as e:
            logger.error(f"Error in reset API call: {str(e)}")
            errors.append(str(e))

    if errors:
        await ctx.send(f"Có lỗi khi reset game: {', '.join(errors)}")
    else:
        logger.info(f"All reset API calls completed successfully")

    # Reset trạng thái game
    game_state["players"].clear()
    game_state["is_game_running"] = False
    game_state["phase"] = "none"
    game_state["is_first_day"] = True
    game_state["voice_channel_id"] = None
    game_state["guild_id"] = None
    game_state["protected_player_id"] = None
    game_state["werewolf_target_id"] = None
    game_state["witch_target_id"] = None
    game_state["witch_action"] = None
    game_state["witch_has_power"] = True
    game_state["hunter_target_id"] = None
    game_state["hunter_has_power"] = True
    game_state["votes"] = {}
    game_state["text_channel"] = None
    game_state["wolf_channel"] = None
    game_state["dead_channel"] = None
    game_state["illusionist_scanned"] = False
    game_state["illusionist_effect_active"] = False
    game_state["temp_player_count"] = 0
    game_state["temp_players"] = []
    game_state["temp_roles"] = {role: 0 for role in ROLES}
    game_state["temp_admin_id"] = None
    game_state["reset_in_progress"] = False
    game_state["member_cache"].clear()

    game_log.clear()

    logger.info(f"Game reset completed: is_game_running={game_state['is_game_running']}")
    await ctx.send("Game đã được reset! Tất cả mic đã bật lại, kênh dead-chat và wolf-chat đã được xóa.")

# Lệnh và sự kiện
@bot.event
async def on_ready():
    print(f"Bot đã sẵn sàng với tên {bot.user}")
    logger.info(f"Bot started as {bot.user}, guilds={len(bot.guilds)}")
    keep_alive()

@bot.command()
async def help_masoi(ctx):
    embed = discord.Embed(
        title="Hướng Dẫn Bot Ma Sói",
        description="Danh sách lệnh và cách sử dụng để chơi Ma Sói.",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="!start_game",
        value="Bắt đầu game mới, chọn kênh voice, số lượng người chơi, danh sách người chơi và vai trò.",
        inline=False
    )
    embed.add_field(
        name="!reset_game",
        value="Reset game hiện tại, xóa kênh wolf-chat và dead-chat, bật lại mic, gửi log hoạt động vai trò và danh sách vai trò.",
        inline=False
    )
    embed.add_field(
        name="!end_game",
        value="Kết thúc game, gửi log hoạt động vai trò, danh sách vai trò và reset game.",
        inline=False
    )
    embed.add_field(
        name="!list_roles",
        value="Hiển thị danh sách các vai trò và mô tả chức năng của chúng trong game, phân chia theo Phe Dân và Phe Sói.",
        inline=False
    )
    embed.add_field(
        name="!status",
        value="Kiểm tra trạng thái hiện tại của bot (game đang chạy, số người chơi, pha hiện tại).",
        inline=False
    )
    embed.add_field(
        name="!help_masoi",
        value="Hiển thị hướng dẫn này.",
        inline=False
    )
    embed.set_footer(text="Bot Ma Sói được tạo bởi xAI")
    await ctx.send(embed=embed)

@bot.command()
async def list_roles(ctx):
    embed = discord.Embed(
        title="Danh Sách Vai Trò Ma Sói",
        description="Mô tả các vai trò trong game, phân chia theo phe.",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="Phe Dân",
        value="\n".join([f"**{role}**: {ROLE_DESCRIPTIONS[role]}" for role in VILLAGER_ROLES]),
        inline=False
    )
    embed.add_field(
        name="Phe Sói",
        value="\n".join([f"**{role}**: {ROLE_DESCRIPTIONS[role]}" for role in WEREWOLF_ROLES]),
        inline=False
    )
    embed.set_footer(text="Bot Ma Sói được tạo bởi xAI")
    await ctx.send(embed=embed)

@bot.command()
async def start_game(ctx):
    if game_state["is_game_running"]:
        await ctx.send("Game đang chạy! Dùng !reset_game hoặc !end_game để kết thúc game hiện tại.")
        return
    game_state["temp_admin_id"] = ctx.author.id
    guild = ctx.guild
    voice_channels = [ch for ch in guild.voice_channels if ch.members]
    if not voice_channels:
        await ctx.send("Không có kênh voice nào có người chơi!")
        return
    await ctx.send(
        "Chọn kênh voice để bắt đầu game:",
        view=VoiceChannelView(guild, ctx.author.id)
    )

@bot.command()
async def reset_game(ctx):
    if not game_state["is_game_running"]:
        await ctx.send("Chưa có game nào để reset!")
        return
    await reset_game_logic(ctx)

@bot.command()
async def end_game(ctx):
    if not game_state["is_game_running"]:
        await ctx.send("Chưa có game nào để kết thúc!")
        return
    await reset_game_logic(ctx)

@bot.command()
async def status(ctx):
    embed = discord.Embed(title="Trạng thái Bot Ma Sói", color=discord.Color.green())
    embed.add_field(name="Game đang chạy", value=str(game_state["is_game_running"]), inline=False)
    embed.add_field(name="Số người chơi", value=str(len(game_state["players"])), inline=False)
    embed.add_field(name="Pha hiện tại", value=game_state["phase"], inline=False)
    await ctx.send(embed=embed)

# Khởi động máy chủ web và bot
keep_alive()
bot.run(os.getenv("TOKEN"))
