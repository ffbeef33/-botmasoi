# views/action_views.py
# UI Components cho các hành động trong game

import discord
import logging
from typing import List, Dict, Optional
from constants import NO_NIGHT_ACTION_ROLES

logger = logging.getLogger(__name__)

class NightMathView(discord.ui.View):
    """View cho bài toán ban đêm"""
    def __init__(self, user_id, options, correct_answer, game_state, timeout=40):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.correct_answer = correct_answer
        self.game_state = game_state
        for option in options:
            self.add_item(MathAnswerButton(option, option == correct_answer, user_id, game_state))

class MathAnswerButton(discord.ui.Button):
    """Button trả lời bài toán"""
    def __init__(self, answer, is_correct, user_id, game_state):
        super().__init__(label=str(answer), style=discord.ButtonStyle.primary)
        self.answer = answer
        self.is_correct = is_correct
        self.user_id = user_id
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Đây không phải bài toán của bạn!", ephemeral=True)
            return
        if self.game_state["phase"] != "night":
            await interaction.response.send_message("Chưa phải pha đêm!", ephemeral=True)
            return
        if self.game_state["is_game_paused"]:
            await interaction.response.send_message("Game đang tạm dừng, không thể thực hiện hành động!", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("Vui lòng trả lời qua DM!", ephemeral=True)
            return
        if interaction.user.id not in self.game_state["math_problems"]:
            await interaction.response.send_message("Bạn đã trả lời hoặc không có bài toán!", ephemeral=True)
            return

        if self.is_correct:
            self.game_state["math_results"][self.user_id] = True
            await interaction.response.send_message("✅ **Đúng!** Bạn đã đủ điều kiện để bỏ phiếu vào ban ngày.", ephemeral=True)
        else:
            self.game_state["math_results"][self.user_id] = False
            await interaction.response.send_message("❌ **Sai!** Bạn sẽ không được bỏ phiếu vào ban ngày.", ephemeral=True)

        del self.game_state["math_problems"][self.user_id]
        for child in self.view.children:
            child.disabled = True
        await interaction.message.edit(view=self.view)

class NightActionView(discord.ui.View):
    """View cho hành động đêm"""
    def __init__(self, role, players, game_state, timeout=40):
        super().__init__(timeout=timeout)
        self.role = role
        self.game_state = game_state
        self.add_item(NightActionSelect(role, players, game_state))

class NightActionSelect(discord.ui.Select):
    """Select menu cho hành động đêm"""
    def __init__(self, role, players, game_state):
        options = [
            discord.SelectOption(
                label=p.display_name[:25],
                value=str(p.id),
                description=f"ID: {p.id % 10000}"  # Hiển thị 4 số cuối của ID
            )
            for p in players
        ]
        options.append(discord.SelectOption(label="Bỏ qua", value="skip"))
        super().__init__(
            placeholder=f"Chọn người để thực hiện hành động ({role})",
            options=options,
            min_values=1,
            max_values=1
        )
        self.role = role
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.game_state["players"]:
            await interaction.response.send_message("Bạn không phải người chơi!", ephemeral=True)
            return
        if self.game_state["phase"] != "night":
            await interaction.response.send_message("Chưa phải pha đêm!", ephemeral=True)
            return
        if self.game_state["is_game_paused"]:
            await interaction.response.send_message("Game đang tạm dừng, không thể thực hiện hành động!", ephemeral=True)
            return
        if self.role == "Werewolf" and not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Vui lòng thực hiện hành động trong wolf-chat!", ephemeral=True)
            return
        if self.role != "Werewolf" and not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("Vui lòng thực hiện hành động qua DM!", ephemeral=True)
            return
            
        if self.values[0] == "skip":
            await interaction.response.send_message(f"Bạn đã chọn bỏ qua hành động {self.role}.", ephemeral=True)
            return
            
        user_id = interaction.user.id
        target_id = int(self.values[0])
        
        # Xử lý theo từng vai trò
        if self.role == "Seer":
            await self.handle_seer_action(interaction, user_id, target_id)
        elif self.role == "Guard":
            await self.handle_guard_action(interaction, user_id, target_id)
        elif self.role == "Werewolf":
            await self.handle_werewolf_action(interaction, user_id, target_id)
        elif self.role == "Hunter":
            await self.handle_hunter_action(interaction, user_id, target_id)
        elif self.role == "Explorer":
            await self.handle_explorer_action(interaction, user_id, target_id)
        elif self.role == "Demon Werewolf":
            await self.handle_demon_werewolf_action(interaction, user_id, target_id)
            
        # Vô hiệu hóa view sau khi thực hiện
        for child in self.view.children:
            child.disabled = True
        await interaction.message.edit(view=self.view)
    
    async def handle_seer_action(self, interaction, user_id, target_id):
        """Xử lý hành động của Tiên Tri"""
        self.game_state["seer_target_id"] = target_id
        target_role = self.game_state["players"][target_id]["role"]
        target_name = self.game_state["member_cache"][target_id].display_name
        
        # Kiểm tra hiệu ứng Illusionist
        if target_role == "Illusionist":
            if self.game_state["illusionist_effect_active"]:
                embed = discord.Embed(
                    title="🔮 Kết quả Soi",
                    description=f"Người chơi **{target_name}** thuộc **Phe Sói**!",
                    color=discord.Color.red()
                )
            else:
                embed = discord.Embed(
                    title="🔮 Kết quả Soi",
                    description=f"Người chơi **{target_name}** thuộc **Phe Dân**!",
                    color=discord.Color.green()
                )
                
            self.game_state["illusionist_effect_night"] = self.game_state["night_count"] + 1
            self.game_state["illusionist_scanned"] = True
        
        # XỬ LÝ WOLFMAN THEO LOGIC MỚI
        elif target_role == "Wolfman":
            if self.game_state["illusionist_effect_active"]:
                # Nếu tiên tri bị ảo giác: Wolfman hiện là phe Sói
                embed = discord.Embed(
                    title="🔮 Kết quả Soi",
                    description=f"Người chơi **{target_name}** thuộc **Phe Sói**!",
                    color=discord.Color.red()
                )
                logger.info(f"Seer scanned Wolfman {target_id} ({target_name}), showing as Werewolf due to illusion effect")
            else:
                # Nếu tiên tri không bị ảo giác: Wolfman hiện là phe Dân
                embed = discord.Embed(
                    title="🔮 Kết quả Soi",
                    description=f"Người chơi **{target_name}** thuộc **Phe Dân**!",
                    color=discord.Color.green()
                )
                logger.info(f"Seer scanned Wolfman {target_id} ({target_name}), showing as Villager (no illusion effect)")
                
        else:
            # Xác định kết quả thực tế với hiệu ứng Illusionist (nếu có)
            # Loại bỏ Wolfman khỏi danh sách này vì đã xử lý riêng ở trên
            is_werewolf_team = target_role in ["Werewolf", "Demon Werewolf", "Assassin Werewolf"]
            
            # Đảo ngược kết quả nếu hiệu ứng Illusionist đang hoạt động
            if self.game_state["illusionist_effect_active"]:
                is_werewolf_team = not is_werewolf_team
                
            if is_werewolf_team:
                embed = discord.Embed(
                    title="🔮 Kết quả Soi",
                    description=f"Người chơi **{target_name}** thuộc **Phe Sói**!",
                    color=discord.Color.red()
                )
            else:
                embed = discord.Embed(
                    title="🔮 Kết quả Soi",
                    description=f"Người chơi **{target_name}** thuộc **Phe Dân**!",
                    color=discord.Color.green()
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"Tiên Tri {user_id} đã soi {target_id} ({target_name})")
    
    async def handle_guard_action(self, interaction, user_id, target_id):
        """Xử lý hành động của Bảo Vệ"""
        # Kiểm tra xem có bảo vệ cùng một người hai đêm liên tiếp không
        if target_id == self.game_state["previous_protected_player_id"]:
            await interaction.response.send_message("Bạn không thể bảo vệ cùng một người hai đêm liên tiếp!", ephemeral=True)
            return
            
        target = self.game_state["member_cache"].get(target_id)
        if not target:
            await interaction.response.send_message("Không tìm thấy người chơi!", ephemeral=True)
            return
            
        self.game_state["protected_player_id"] = target_id
        
        embed = discord.Embed(
            title="🛡️ Hành Động Bảo Vệ",
            description=f"Bạn đã chọn bảo vệ **{target.display_name}**!",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"Bảo Vệ {user_id} đã bảo vệ {target_id} ({target.display_name})")
    
    async def handle_werewolf_action(self, interaction, user_id, target_id):
        """Xử lý hành động của Sói"""
        target = self.game_state["member_cache"].get(target_id)
        if not target:
            await interaction.response.send_message("Không tìm thấy người chơi!", ephemeral=True)
            return
            
        self.game_state["werewolf_target_id"] = target_id
        
        embed = discord.Embed(
            title="🐺 Hành Động Sói",
            description=f"Bầy Sói đã chọn giết **{target.display_name}**!",
            color=discord.Color.dark_red()
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"Sói {user_id} đã chọn giết {target_id} ({target.display_name})")
    
    async def handle_hunter_action(self, interaction, user_id, target_id):
        """Xử lý hành động của Thợ Săn"""
        if not self.game_state["hunter_has_power"]:
            await interaction.response.send_message("Bạn đã sử dụng chức năng Thợ Săn!", ephemeral=True)
            return
            
        target = self.game_state["member_cache"].get(target_id)
        if not target:
            await interaction.response.send_message("Không tìm thấy người chơi!", ephemeral=True)
            return
            
        self.game_state["hunter_target_id"] = target_id
        
        embed = discord.Embed(
            title="🏹 Hành Động Thợ Săn",
            description=f"Bạn đã chọn giết **{target.display_name}**!",
            color=discord.Color.dark_orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"Thợ Săn {user_id} đã chọn giết {target_id} ({target.display_name})")
    
    async def handle_explorer_action(self, interaction, user_id, target_id):
        """Xử lý hành động của Người Khám Phá"""
        if not self.game_state.get("explorer_can_act", True):
            await interaction.response.send_message("Bạn đã mất chức năng Người Khám Phá!", ephemeral=True)
            return
            
        if self.game_state["night_count"] < 2:
            await interaction.response.send_message("Bạn chưa thể khám phá vào đêm đầu tiên!", ephemeral=True)
            return
            
        target = self.game_state["member_cache"].get(target_id)
        if not target:
            await interaction.response.send_message("Không tìm thấy người chơi!", ephemeral=True)
            return
            
        self.game_state["explorer_target_id"] = target_id
        
        embed = discord.Embed(
            title="🧭 Hành Động Người Khám Phá",
            description=f"Bạn đã chọn khám phá **{target.display_name}**!",
            color=discord.Color.gold()
        )
        embed.add_field(name="Lưu ý", value="Kết quả sẽ được xử lý vào cuối đêm.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"Người Khám Phá {user_id} đã chọn khám phá {target_id} ({target.display_name})")
    
    async def handle_demon_werewolf_action(self, interaction, user_id, target_id):
        """Xử lý hành động của Sói Quỷ"""
        if not self.game_state["demon_werewolf_activated"]:
            await interaction.response.send_message("Chức năng Sói Quỷ chưa được kích hoạt!", ephemeral=True)
            return
            
        if self.game_state["demon_werewolf_has_cursed"]:
            await interaction.response.send_message("Bạn đã sử dụng chức năng nguyền!", ephemeral=True)
            return
            
        target = self.game_state["member_cache"].get(target_id)
        if not target:
            await interaction.response.send_message("Không tìm thấy người chơi!", ephemeral=True)
            return
            
        self.game_state["demon_werewolf_has_cursed"] = True
        self.game_state["demon_werewolf_cursed_player"] = target_id
        self.game_state["demon_werewolf_cursed_this_night"] = True
        
        embed = discord.Embed(
            title="👹 Hành Động Sói Quỷ",
            description=f"Bạn đã nguyền **{target.display_name}**! Người này sẽ trở thành Sói vào đêm tiếp theo.",
            color=discord.Color.dark_red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"Sói Quỷ {user_id} đã nguyền {target_id} ({target.display_name})")

class DetectiveSelectView(discord.ui.View):
    """View cho Thám Tử chọn người để kiểm tra"""
    def __init__(self, detective_id, alive_players, game_state):
        super().__init__(timeout=60)
        self.detective_id = detective_id
        self.game_state = game_state
        
        # Tạo dropdown với các người chơi được phân loại theo thứ tự alphabet
        sorted_players = sorted(alive_players, key=lambda m: m.display_name.lower())
        options = [
            discord.SelectOption(
                label=member.display_name[:25],  # Giới hạn độ dài tên
                description=f"ID: {member.id % 10000}",  # Hiển thị 4 số cuối ID
                value=str(member.id)
            )
            for member in sorted_players if member.id != detective_id
        ]
        
        self.select = discord.ui.Select(
            placeholder="Chọn hai người chơi để kiểm tra",
            options=options,
            min_values=2,
            max_values=2
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
        # Thêm nút hủy
        self.add_item(CancelButton())

    async def select_callback(self, interaction: discord.Interaction):
        # Validation logic
        if interaction.user.id != self.detective_id:
            await interaction.response.send_message("Chỉ thám tử được thao tác!", ephemeral=True)
            return
        if self.game_state["phase"] != "night":
            await interaction.response.send_message("Chưa phải pha đêm!", ephemeral=True)
            return
        if self.game_state["is_game_paused"]:
            await interaction.response.send_message("Game đang tạm dừng, không thể thực hiện hành động!", ephemeral=True)
            return
        if self.game_state["detective_has_used_power"]:
            await interaction.response.send_message("Bạn đã sử dụng quyền của mình!", ephemeral=True)
            return
        
        target1_id = int(self.select.values[0])
        target2_id = int(self.select.values[1])
        
        if target1_id == target2_id:
            await interaction.response.send_message("Bạn phải chọn hai người chơi khác nhau!", ephemeral=True)
            return
            
        # Lấy tên người chơi để hiển thị kết quả
        target1_name = next((p.display_name for p in self.game_state["member_cache"].values() 
                         if p.id == target1_id), "Người chơi 1")
        target2_name = next((p.display_name for p in self.game_state["member_cache"].values() 
                         if p.id == target2_id), "Người chơi 2")
        
        # Logic kiểm tra vai trò
        from utils.role_utils import get_player_team
        target1_role = self.game_state["players"][target1_id]["role"]
        target2_role = self.game_state["players"][target2_id]["role"]
        target1_team = get_player_team(target1_role)
        target2_team = get_player_team(target2_role)
        
        if target1_team == target2_team:
            result = f"**{target1_name}** và **{target2_name}** cùng phe."
        else:
            result = f"**{target1_name}** và **{target2_name}** khác phe."
        
        # Tạo embed để hiển thị kết quả
        embed = discord.Embed(
            title="🔍 Kết Quả Điều Tra",
            description=result,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Cập nhật trạng thái game
        self.game_state["detective_has_used_power"] = True
        self.game_state["detective_target1_id"] = target1_id
        self.game_state["detective_target2_id"] = target2_id
        
        # Vô hiệu hóa view
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        
        # Gửi thông báo xác nhận
        await interaction.followup.send("Bạn đã sử dụng quyền của Thám Tử. Chức năng này không còn sử dụng được nữa.", ephemeral=True)

class CancelButton(discord.ui.Button):
    """Button hủy hành động"""
    def __init__(self):
        super().__init__(label="Hủy", style=discord.ButtonStyle.secondary)
        
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Bạn đã hủy hành động.", ephemeral=True)
        for child in self.view.children:
            child.disabled = True
        await interaction.message.edit(view=self.view)

class AssassinActionView(discord.ui.View):
    """View cho Sói Ám Sát chọn người và đoán vai trò"""
    def __init__(self, game_state, assassin_id):
        super().__init__(timeout=40)
        self.game_state = game_state
        self.assassin_id = assassin_id
        self.target_id = None
        self.role_guess = None
        
        # Cập nhật giao diện người dùng
        self.update_components()
    
    def update_components(self):
        self.clear_items()
        
        # Tạo dropdown người chơi
        player_options = [
            discord.SelectOption(
                label=self.game_state["member_cache"][pid].display_name[:25],
                description=f"ID: {pid % 10000}",
                value=str(pid)
            )
            for pid, data in self.game_state["players"].items()
            if data["status"] in ["alive", "wounded"] and pid != self.assassin_id
        ]
        
        player_select = discord.ui.Select(
            placeholder="1. Chọn người chơi",
            options=player_options,
            min_values=1,
            max_values=1,
            custom_id="player_select"
        )
        player_select.callback = self.player_select_callback
        self.add_item(player_select)
        
        # Tạo dropdown vai trò (không bao gồm Dân Làng)
        from constants import ROLES
        role_options = [
            discord.SelectOption(label=role, value=role)
            for role in ROLES if role != "Villager"
        ]
        
        role_select = discord.ui.Select(
            placeholder="2. Đoán vai trò",
            options=role_options,
            min_values=1,
            max_values=1,
            custom_id="role_select",
            disabled=self.target_id is None  # Chỉ cho phép chọn vai trò sau khi đã chọn người
        )
        role_select.callback = self.role_select_callback
        self.add_item(role_select)
        
        # Thêm nút xác nhận
        confirm_button = discord.ui.Button(
            label="Xác nhận",
            style=discord.ButtonStyle.danger,
            disabled=self.target_id is None or self.role_guess is None  # Chỉ bật khi đã chọn cả người và vai trò
        )
        confirm_button.callback = self.confirm_callback
        self.add_item(confirm_button)
    
    async def player_select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.assassin_id:
            await interaction.response.send_message("Chỉ Sói Ám Sát được thao tác!", ephemeral=True)
            return
            
        self.target_id = int(interaction.data["values"][0])
        await interaction.response.defer()
        
        # Cập nhật trạng thái của view
        self.update_components()
        await interaction.message.edit(view=self)
    
    async def role_select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.assassin_id:
            await interaction.response.send_message("Chỉ Sói Ám Sát được thao tác!", ephemeral=True)
            return
            
        self.role_guess = interaction.data["values"][0]
        await interaction.response.defer()
        
        # Cập nhật trạng thái của view
        self.update_components()
        await interaction.message.edit(view=self)
    
    async def confirm_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.assassin_id:
            await interaction.response.send_message("Chỉ Sói Ám Sát được thao tác!", ephemeral=True)
            return
        
        # Lưu thông tin vào game_state
        self.game_state["assassin_werewolf_target_id"] = self.target_id
        self.game_state["assassin_werewolf_role_guess"] = self.role_guess
        self.game_state["assassin_werewolf_has_acted"] = True
        
        target_name = self.game_state["member_cache"][self.target_id].display_name
        
        embed = discord.Embed(
            title="🗡️ Hành Động Sói Ám Sát",
            description=f"Bạn đã chọn đoán **{self.role_guess}** cho người chơi **{target_name}**.\n\nKết quả sẽ được xử lý vào cuối pha đêm.",
            color=discord.Color.red()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Vô hiệu hóa tất cả components
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

class WitchActionView(discord.ui.View):
    """View cho Phù Thủy chọn người để cứu hoặc giết"""
    def __init__(self, alive_players, potential_targets, game_state, timeout=20):
        super().__init__(timeout=timeout)
        self.game_state = game_state
        self.alive_players = alive_players
        self.potential_targets = potential_targets
        
        # Thêm các components theo điều kiện
        if potential_targets:
            self.add_item(WitchSaveSelect(potential_targets, game_state))
            
        self.add_item(WitchKillSelect(alive_players, game_state))
        self.add_item(WitchSkipButton(game_state))

class WitchSaveSelect(discord.ui.Select):
    """Select menu cho Phù Thủy chọn người để cứu"""
    def __init__(self, potential_targets, game_state):
        options = [
            discord.SelectOption(
                label=member.display_name[:25],
                description=f"ID: {member.id % 10000}",
                value=str(member.id)
            )
            for member in potential_targets
        ]
        super().__init__(
            placeholder="Cứu người bị giết",
            options=options,
            min_values=1,
            max_values=1
        )
        self.potential_targets = potential_targets
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        # Kiểm tra quyền thao tác
        if interaction.user.id not in self.view.game_state["players"] or self.view.game_state["players"][interaction.user.id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Bạn không phải người chơi hoặc đã chết!", ephemeral=True)
            return
            
        if self.view.game_state["is_game_paused"]:
            await interaction.response.send_message("Game đang tạm dừng, không thể thực hiện hành động!", ephemeral=True)
            return
            
        if self.view.game_state["players"][interaction.user.id]["role"] != "Witch":
            await interaction.response.send_message("Chỉ Phù Thủy mới có thể thực hiện hành động này!", ephemeral=True)
            return
            
        if self.view.game_state["phase"] != "night":
            await interaction.response.send_message("Chưa phải pha đêm!", ephemeral=True)
            return
            
        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("Vui lòng thực hiện hành động qua DM!", ephemeral=True)
            return
            
        if not self.view.game_state["witch_has_power"]:
            await interaction.response.send_message("Bạn đã sử dụng chức năng!", ephemeral=True)
            return
            
        target_id = int(self.values[0])
        if target_id not in [m.id for m in self.potential_targets]:
            await interaction.response.send_message("Mục tiêu không hợp lệ!", ephemeral=True)
            return
            
        # Cập nhật game state
        self.view.game_state["witch_action_save"] = True
        self.view.game_state["witch_target_save_id"] = target_id
        
        # Gửi thông báo
        target_member = next((m for m in self.potential_targets if m.id == target_id), None)
        if target_member:
            embed = discord.Embed(
                title="🧙‍♀️ Hành Động Phù Thủy",
                description=f"Bạn đã chọn cứu **{target_member.display_name}**!",
                color=discord.Color.purple()
            )
            embed.add_field(name="Lưu ý", value="Từ đêm sau, bạn sẽ không còn nhận thông tin về người bị giết.", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Bạn đã chọn cứu một người, nhưng không tìm thấy mục tiêu!", ephemeral=True)
            
        logger.info(f"Witch chose to save player: target_id={target_id}, target_name={target_member.display_name if target_member else 'Unknown'}, interaction_id={interaction.id}")
        
        # Vô hiệu hóa view
        for child in self.view.children:
            child.disabled = True
            
        try:
            await interaction.message.edit(view=self.view)
        except discord.errors.NotFound:
            logger.warning(f"Message not found when editing WitchSaveSelect view for interaction_id={interaction.id}")

class WitchKillSelect(discord.ui.Select):
    """Select menu cho Phù Thủy chọn người để giết"""
    def __init__(self, alive_players, game_state):
        options = [
            discord.SelectOption(
                label=member.display_name[:25],
                description=f"ID: {member.id % 10000}",
                value=str(member.id)
            )
            for member in alive_players
        ]
        super().__init__(
            placeholder="Giết một người",
            options=options,
            min_values=1,
            max_values=1
        )
        self.alive_players = alive_players
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        # Kiểm tra quyền thao tác
        if interaction.user.id not in self.view.game_state["players"] or self.view.game_state["players"][interaction.user.id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Bạn không phải người chơi hoặc đã chết!", ephemeral=True)
            return
            
        if self.view.game_state["is_game_paused"]:
            await interaction.response.send_message("Game đang tạm dừng, không thể thực hiện hành động!", ephemeral=True)
            return
            
        if self.view.game_state["players"][interaction.user.id]["role"] != "Witch":
            await interaction.response.send_message("Chỉ Phù Thủy mới có thể thực hiện hành động này!", ephemeral=True)
            return
            
        if self.view.game_state["phase"] != "night":
            await interaction.response.send_message("Chưa phải pha đêm!", ephemeral=True)
            return
            
        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("Vui lòng thực hiện hành động qua DM!", ephemeral=True)
            return
            
        if not self.view.game_state["witch_has_power"]:
            await interaction.response.send_message("Bạn đã sử dụng chức năng!", ephemeral=True)
            return
            
        target_id = int(self.values[0])
        if target_id not in self.view.game_state["players"] or self.view.game_state["players"][target_id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Mục tiêu không hợp lệ!", ephemeral=True)
            return
            
        # Cập nhật game state
        self.view.game_state["witch_action_kill"] = True
        self.view.game_state["witch_target_kill_id"] = target_id
        
        # Gửi thông báo
        target_member = next((m for m in self.alive_players if m.id == target_id), None)
        if target_member:
            embed = discord.Embed(
                title="🧙‍♀️ Hành Động Phù Thủy",
                description=f"Bạn đã chọn giết **{target_member.display_name}**!",
                color=discord.Color.purple()
            )
            embed.add_field(name="Lưu ý", value="Từ đêm sau, bạn sẽ không còn nhận thông tin về người bị giết.", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Bạn đã chọn giết một người, nhưng không tìm thấy mục tiêu!", ephemeral=True)
            
        logger.info(f"Witch chose to kill player: target_id={target_id}, target_name={target_member.display_name if target_member else 'Unknown'}, interaction_id={interaction.id}")
        
        # Vô hiệu hóa view
        for child in self.view.children:
            child.disabled = True
            
        try:
            await interaction.message.edit(view=self.view)
        except discord.errors.NotFound:
            logger.warning(f"Message not found when editing WitchKillSelect view for interaction_id={interaction.id}")

class WitchSkipButton(discord.ui.Button):
    """Button cho Phù Thủy bỏ qua hành động"""
    def __init__(self, game_state):
        super().__init__(label="Bỏ qua", style=discord.ButtonStyle.grey)
        self.game_state = game_state

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.view.game_state["players"] or self.view.game_state["players"][interaction.user.id]["status"] not in ["alive", "wounded"]:
            await interaction.response.send_message("Bạn không phải người chơi hoặc đã chết!", ephemeral=True)
            return
            
        if self.view.game_state["is_game_paused"]:
            await interaction.response.send_message("Game đang tạm dừng, không thể thực hiện hành động!", ephemeral=True)
            return
            
        if self.view.game_state["players"][interaction.user.id]["role"] != "Witch":
            await interaction.response.send_message("Chỉ Phù Thủy mới có thể thực hiện hành động này!", ephemeral=True)
            return
            
        if self.view.game_state["phase"] != "night":
            await interaction.response.send_message("Chưa phải pha đêm!", ephemeral=True)
            return
            
        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("Vui lòng thực hiện hành động qua DM!", ephemeral=True)
            return
            
        # Cập nhật game state
        self.view.game_state["witch_action_save"] = False
        self.view.game_state["witch_action_kill"] = False
        self.view.game_state["witch_target_save_id"] = None
        self.view.game_state["witch_target_kill_id"] = None
        
        # Gửi thông báo
        await interaction.response.send_message("Bạn đã chọn bỏ qua hành động đêm nay.", ephemeral=True)
        logger.info(f"Witch skipped action: interaction_id={interaction.id}")
        
        # Vô hiệu hóa view
        for child in self.view.children:
            child.disabled = True
            
        try:
            await interaction.message.edit(view=self.view)
        except discord.errors.NotFound:
            logger.warning(f"Message not found when editing WitchSkipButton view for interaction_id={interaction.id}")
