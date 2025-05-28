# game_state.py
# Quản lý trạng thái game

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
import discord
import random
import logging
import asyncio
from constants import ROLES, VILLAGER_ROLES, WEREWOLF_ROLES

logger = logging.getLogger(__name__)

@dataclass
class PlayerData:
    """
    Lưu trữ thông tin của một người chơi trong game
    """
    user_id: int
    role: str
    status: str = "alive"  # alive, wounded, dead
    muted: bool = False
    channel_id: Optional[int] = None
    
    def is_alive(self) -> bool:
        """Kiểm tra người chơi còn sống không"""
        return self.status in ["alive", "wounded"]
    
    def is_werewolf(self) -> bool:
        """Kiểm tra người chơi có phải là sói không"""
        return self.role in WEREWOLF_ROLES and self.role != "Illusionist"
    
    def is_villager(self) -> bool:
        """Kiểm tra người chơi có phải là dân không"""
        return self.role in VILLAGER_ROLES or self.role == "Illusionist"
    
    def get_team(self) -> str:
        """Trả về phe của người chơi"""
        if self.role in ["Illusionist", "Wolfman", "Werewolf", "Demon Werewolf", "Assassin Werewolf"]:
            return "werewolves"
        elif self.role in VILLAGER_ROLES:
            return "villagers"
        else:
            return "unknown"

# game_state.py
# Class quản lý trạng thái game

class GameState:
    def __init__(self, guild_id):
        # Thông tin cơ bản
        self.guild_id = guild_id
        self.is_game_running = False
        self.is_game_paused = False
        self.phase = "none"
        self.reset_in_progress = False
        
        # Thông tin người chơi và vai trò
        self.players = {}
        self.member_cache = {}
        self.temp_admin_id = None
        self.temp_players = []
        self.temp_roles = []
        
        # Thông tin kênh và voice
        self.text_channel = None
        self.wolf_channel = None
        self.dead_channel = None
        self.voice_channel_id = None
        self.voice_connection = None
        self.player_channels = {}
        
        # Thông tin vai trò và team
        self.villager_role_id = None
        self.dead_role_id = None
        self.werewolf_role_id = None
        
        # Thông tin pha đêm
        self.night_count = 0
        self.is_first_day = True
        self.protected_player_id = None
        self.previous_protected_player_id = None
        self.werewolf_target_id = None
        self.witch_target_save_id = None
        self.witch_target_kill_id = None
        self.witch_action_save = False
        self.witch_action_kill = False
        self.witch_has_power = True
        self.hunter_target_id = None
        self.hunter_has_power = True
        self.explorer_target_id = None
        self.explorer_id = None
        self.explorer_can_act = True
        self.seer_target_id = None
        
        # Thông tin pha bỏ phiếu
        self.votes = {}
        self.math_problems = {}
        self.math_results = {}
        
        # Thông tin vai trò đặc biệt
        self.detective_has_used_power = False
        self.detective_target1_id = None
        self.detective_target2_id = None
        self.illusionist_scanned = False
        self.illusionist_effect_active = False
        self.illusionist_effect_night = 0
        
        # Thông tin Sói Quỷ và Sói Ám Sát
        self.assassin_werewolf_has_acted = False
        self.assassin_werewolf_target_id = None
        self.assassin_werewolf_role_guess = None
        self.demon_werewolf_activated = False
        self.demon_werewolf_cursed_player = None
        self.demon_werewolf_has_cursed = False
        self.demon_werewolf_cursed_this_night = False
        
    # Các phương thức để hỗ trợ truy cập kiểu dictionary
    def __getitem__(self, key):
        """Cho phép truy cập game_state[key]"""
        return getattr(self, key)
        
    def __setitem__(self, key, value):
        """Cho phép gán game_state[key] = value"""
        setattr(self, key, value)
        
    def __contains__(self, key):
        """Cho phép kiểm tra 'key in game_state'"""
        return hasattr(self, key)
    
    def get(self, key, default=None):
        """Mô phỏng phương thức get() của dictionary"""
        return getattr(self, key, default)
    
    def keys(self):
        """Mô phỏng phương thức keys() của dictionary"""
        return [attr for attr in dir(self) if not attr.startswith('_') and not callable(getattr(self, attr))]
    
    def values(self):
        """Mô phỏng phương thức values() của dictionary"""
        return [getattr(self, attr) for attr in dir(self) if not attr.startswith('_') and not callable(getattr(self, attr))]
    
    def items(self):
        """Mô phỏng phương thức items() của dictionary"""
        return [(attr, getattr(self, attr)) for attr in dir(self) if not attr.startswith('_') and not callable(getattr(self, attr))]
    
    def update(self, other_dict):
        """Mô phỏng phương thức update() của dictionary"""
        for key, value in other_dict.items():
            setattr(self, key, value)
    
    # =========== Các phương thức cập nhật ===========
    
    def reset(self):
        """Reset game state về trạng thái mặc định"""
        self.is_game_running = False
        self.is_game_paused = False
        self.phase = "none"
        self.night_count = 0
        self.is_first_day = True
        
        # Xóa dữ liệu người chơi
        self.players.clear()
        self.votes.clear()
        self.math_problems.clear()
        self.math_results.clear()
        
        # Xóa thông tin kênh
        self.wolf_channel = None
        self.dead_channel = None
        
        # Reset các trạng thái đặc biệt
        self.protected_player_id = None
        self.previous_protected_player_id = None
        self.werewolf_target_id = None
        self.hunter_target_id = None
        self.hunter_has_power = True
        self.witch_action_save = False
        self.witch_action_kill = False
        self.witch_target_save_id = None
        self.witch_target_kill_id = None
        self.witch_has_power = True
        self.explorer_target_id = None
        self.explorer_can_act = True
        
        self.illusionist_scanned = False
        self.illusionist_effect_active = False
        self.illusionist_effect_night = 0
        
        self.demon_werewolf_activated = False
        self.demon_werewolf_cursed_player = None
        self.demon_werewolf_has_cursed = False
        self.demon_werewolf_cursed_this_night = False
        
        self.assassin_werewolf_has_acted = False
        self.assassin_werewolf_target_id = None
        self.assassin_werewolf_role_guess = None
        
        self.detective_has_used_power = False
        self.detective_target1_id = None
        self.detective_target2_id = None
        
        logger.info(f"Game state reset cho guild ID {self.guild_id}")
    
    def initialize_from_setup(self):
        """Khởi tạo game state từ thông tin setup"""
        self.is_game_running = True
        self.is_game_paused = False
        self.phase = "none"
        self.night_count = 0
        self.is_first_day = True
        
        # Xóa dữ liệu người chơi cũ
        self.players.clear()
        self.votes.clear()
        
        # Reset các trạng thái đặc biệt
        self.protected_player_id = None
        self.previous_protected_player_id = None
        self.werewolf_target_id = None
        self.hunter_target_id = None
        self.hunter_has_power = self.temp_roles["Hunter"] > 0
        self.witch_has_power = self.temp_roles["Witch"] > 0
        self.explorer_can_act = True
        
        self.illusionist_scanned = False
        self.illusionist_effect_active = False
        self.illusionist_effect_night = 0
        
        self.demon_werewolf_activated = False
        self.demon_werewolf_cursed_player = None
        self.demon_werewolf_has_cursed = False
        self.demon_werewolf_cursed_this_night = False
        
        self.assassin_werewolf_has_acted = False
        self.assassin_werewolf_target_id = None
        self.assassin_werewolf_role_guess = None
        
        self.detective_has_used_power = False
        self.detective_target1_id = None
        self.detective_target2_id = None
        
        logger.info(f"Game state khởi tạo từ setup cho guild ID {self.guild_id}")
    
    def add_player(self, user_id: int, role: str):
        """Thêm người chơi vào game"""
        self.players[user_id] = PlayerData(user_id=user_id, role=role)
        if role == "Explorer":
            self.explorer_id = user_id
        logger.debug(f"Thêm người chơi {user_id} với vai trò {role}")
    
    def mark_player_dead(self, user_id: int):
        """Đánh dấu người chơi đã chết"""
        if user_id in self.players:
            self.players[user_id].status = "dead"
            logger.info(f"Người chơi {user_id} đã chết")
            return True
        return False
    
    def mark_player_wounded(self, user_id: int):
        """Đánh dấu người chơi bị thương (Tough Guy)"""
        if user_id in self.players:
            self.players[user_id].status = "wounded"
            logger.info(f"Người chơi {user_id} bị thương")
            return True
        return False
    
    def register_vote(self, voter_id: int, target_id: int) -> bool:
        """Đăng ký phiếu bầu từ voter cho target"""
        if voter_id not in self.players or not self.players[voter_id].is_alive():
            logger.warning(f"Người chơi {voter_id} không thể vote (không tồn tại hoặc đã chết)")
            return False
            
        self.votes[voter_id] = target_id
        logger.debug(f"Người chơi {voter_id} vote cho {target_id}")
        return True
    
    def count_votes(self) -> Dict[int, int]:
        """Đếm số phiếu bầu cho từng người chơi"""
        vote_counts = {}
        skip_votes = 0
        ineligible_count = 0
        
        for user_id, data in self.players.items():
            if not data.is_alive():
                continue
                
            # Kiểm tra điều kiện để vote
            from constants import NO_NIGHT_ACTION_ROLES
            eligible_to_vote = True
            
            if data.role in NO_NIGHT_ACTION_ROLES:
                if user_id not in self.math_results or not self.math_results[user_id]:
                    eligible_to_vote = False
                    ineligible_count += 1
                    continue
            
            # Xử lý phiếu bầu
            if eligible_to_vote:
                target_id = self.votes.get(user_id, "skip")
                if target_id == "skip":
                    skip_votes += 1
                elif isinstance(target_id, int):
                    vote_counts[target_id] = vote_counts.get(target_id, 0) + 1
        
        return vote_counts, skip_votes, ineligible_count
    
    def check_win_condition(self) -> Optional[str]:
        """
        Kiểm tra điều kiện thắng
        
        Returns:
            str: "villagers", "werewolves" hoặc None nếu chưa có bên nào thắng
        """
        werewolves = self.get_alive_count(werewolf_only=True)
        villagers = self.get_alive_count(villager_only=True)
        
        # Phe Dân chỉ thắng nếu không còn Sói và không có lời nguyền đang chờ
        if werewolves == 0 and villagers > 0 and self.demon_werewolf_cursed_player is None:
            logger.info(f"Phe Dân thắng (Sói: {werewolves}, Dân: {villagers})")
            return "villagers"
        # Phe Sói thắng nếu số Sói bằng hoặc vượt số Dân
        elif werewolves >= villagers and werewolves > 0:
            logger.info(f"Phe Sói thắng (Sói: {werewolves}, Dân: {villagers})")
            return "werewolves"
            
        return None

# Lớp quản lý tất cả các game đang chạy
class GameStateManager:
    def __init__(self):
        self.game_states: Dict[int, GameState] = {}
        self.game_logs: Dict[int, List[str]] = {}
        
    def get_game_state(self, guild_id: int) -> GameState:
        """Lấy hoặc tạo mới game state cho guild"""
        if guild_id not in self.game_states:
            self.game_states[guild_id] = GameState(guild_id)
            self.game_logs[guild_id] = []
        return self.game_states[guild_id]
    
    def remove_game_state(self, guild_id: int):
        """Xóa game state của guild"""
        if guild_id in self.game_states:
            del self.game_states[guild_id]
        if guild_id in self.game_logs:
            del self.game_logs[guild_id]
    
    def add_log(self, guild_id: int, message: str):
        """Thêm log cho guild"""
        if guild_id not in self.game_logs:
            self.game_logs[guild_id] = []
        self.game_logs[guild_id].append(message)
        logger.info(f"[Guild {guild_id}] {message}")
    
    def get_logs(self, guild_id: int) -> List[str]:
        """Lấy logs của guild"""
        return self.game_logs.get(guild_id, [])