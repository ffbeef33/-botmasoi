# constants.py
# Hằng số và biến cố định cho toàn bộ ứng dụng

# Các vai trò trong game
ROLES = ["Villager", "Werewolf", "Seer", "Guard", "Witch", "Hunter", "Tough Guy", "Illusionist", "Wolfman", "Explorer", "Demon Werewolf", "Assassin Werewolf", "Detective"]
VILLAGER_SPECIAL_ROLES = ["Seer", "Guard", "Witch", "Hunter", "Tough Guy", "Explorer", "Detective"]
WEREWOLF_SPECIAL_ROLES = ["Illusionist", "Wolfman", "Demon Werewolf", "Assassin Werewolf"]
VILLAGER_ROLES = ["Villager", "Seer", "Guard", "Witch", "Hunter", "Tough Guy", "Explorer", "Detective"]
WEREWOLF_ROLES = ["Werewolf", "Illusionist", "Wolfman", "Demon Werewolf", "Assassin Werewolf"]
NO_NIGHT_ACTION_ROLES = ["Villager", "Tough Guy", "Illusionist"]

# URL các GIF cho các pha của game
GIF_URLS = {
    "morning": "https://cdn.discordapp.com/attachments/1365707789321633813/1372115998525620335/Phase_day.gif?ex=68259a1a&is=6824489a&hm=c01364ba79cba7d7aed13a993a24850c2e0d17a2cf27af95a95389789d79a7a6&",
    "night": "https://cdn.discordapp.com/attachments/1365707789321633813/1372117342380621855/Phase_night.gif?ex=68259b5b&is=682449db&hm=1bafb461bb02b41ed95b43de2753d09254bed7bd052bbf5d2136f397f89850b0&",
    "hang": "https://cdn.discordapp.com/attachments/1365707789321633813/1372117715707232266/Phase_deadbyvote.gif?ex=68259bb4&is=68244a34&hm=6cb3e2864efd785a39be137defbcc2fe4a27636a83b80192602bc378a95666e7&",
    "vote": "https://cdn.discordapp.com/attachments/1365707789321633813/1372117883957678080/Phase_vote.gif?ex=68259bdc&is=68244a5c&hm=1c16c879de3730319169681f6325fced29953b63d688433c9baa0b44dc683ef7&",
    "villager_win": "https://cdn.discordapp.com/attachments/1365707789321633813/1372118299856474184/Phase_humanwin.gif?ex=68259c3f&is=68244abf&hm=64f37b2b28a0790a990469bf14c6bcddf36b438629c1902b21d8ab425f6c2f5d&",
    "werewolf_win": "https://cdn.discordapp.com/attachments/1365707789321633813/1372118396673458217/Phase_wolfwin.gif?ex=68259c56&is=68244ad6&hm=e1e53652db3548081e3e3a5ea419ff785d7e1e434cd168284da334682e1083e6&",
    "death": "https://cdn.discordapp.com/attachments/1365707789321633813/1372118623287509002/Phase_deadbynight.gif?ex=68259c8c&is=68244b0c&hm=ea2f732c04d7bae102f00612f75c81ec5b0c54db7a65ea4f034cdd4626ff0c1a&"
}

# URL các icon cho vai trò 
ROLE_ICONS = {
    "Villager": "https://cdn.discordapp.com/attachments/1365707789321633813/1372853615445676143/villager-512.png?ex=68284910&is=6826f790&hm=21ba4ed9e3293b568f09edf5861a92f5472c11cef09db470c9400e813cf9c180&",
    "Werewolf": "https://cdn.discordapp.com/attachments/1365707789321633813/1372853692226736128/werewolf-512.png?ex=68284922&is=6826f7a2&hm=f931eea427ae3a00a1a2c7f8cf38b41d3c3fa77774b3ff262c031eedf687e1c5&",
    "Seer": "https://cdn.discordapp.com/attachments/1365707789321633813/1372853452555943966/seer-512.png?ex=682848e9&is=6826f769&hm=98e371c02b99c848a39c3267f14eb166bcf4c5a687ed9a9e24f39e35e5900afd&",
    "Guard": "https://cdn.discordapp.com/attachments/1365707789321633813/1372853215065931867/guard-512.png?ex=682848b0&is=6826f730&hm=afc74125559a3d35912aae771c4d8391efedba4d261e6d3935d91b54648c320f&",
    "Witch": "https://cdn.discordapp.com/attachments/1365707789321633813/1372853774682558514/witch-512.png?ex=68284936&is=6826f7b6&hm=1491fa773b223745034fd88a86409bbe99754a4a19afe1573f176ef05912fb50&",
    "Hunter": "https://cdn.discordapp.com/attachments/1365707789321633813/1372853304211669054/hunter-512.png?ex=682848c6&is=6826f746&hm=2c6a8b0968442879facea46e89b417a234922ea4ff3a7791b5fb76d50ba34726&",
    "Tough Guy": "https://cdn.discordapp.com/attachments/1365707789321633813/1372853538669199390/touchguy-512.png?ex=682848fe&is=6826f77e&hm=e4d44f6a9993361f46469fb9b2b91f642efab2032697eaf8b4eb9c976e7ce936&",
    "Illusionist": "https://cdn.discordapp.com/attachments/1365707789321633813/1372853384280805446/illusionist-512.png?ex=682848d9&is=6826f759&hm=bbb99c57d8fd36b0cd88babbfc8c9309a31d8c88fd36993740df0a96732db975&",
    "Wolfman": "https://cdn.discordapp.com/attachments/1365707789321633813/1372853876017070120/wolfman-512.png?ex=6828494e&is=6826f7ce&hm=eb72a7ed9bc15e33982364aa2aef1113916038ebac81a8beed94b69ccf8ae0db&",
    "Explorer": "https://cdn.discordapp.com/attachments/1365707789321633813/1372852429489704960/explorer-512.png?ex=682847f5&is=6826f675&hm=c799a97a59fe90b3dfa62804b4ff38f964502ad06e20eea9097174742efa4e78&",
    "Demon Werewolf": "https://cdn.discordapp.com/attachments/1365707789321633813/1372852300435034122/demonwolf-512.png?ex=682847d6&is=6826f656&hm=0f6bf383e2d72d73fb7b0a98ffb5c9cebbf6444fcb9aa16903eba37a66e74424&",
    "Assassin Werewolf": "https://cdn.discordapp.com/attachments/1365707789321633813/1374432785833394186/assassinwolf-512.png?ex=682e07c7&is=682cb647&hm=191deea5033471f7fb2ec86f7a59ebd4f8259a1c53f9e61ac0a5d52593a375a3&",
    "Detective": "https://cdn.discordapp.com/attachments/1365707789321633813/1374694217527463956/detective-512_2.png?ex=682efb42&is=682da9c2&hm=1763595fbe72496342badea2b85a262c961a7ab05971ba8d036b2fd6a033985b&"
}

# Link đến trang web mô tả vai trò
ROLE_LINKS = {
    "Villager": "https://www.dewolfvie.net/vn/chucnang#h.72xuy5mwxslh",
    "Werewolf": "https://www.dewolfvie.net/vn/chucnang#h.hvhyxzcxp8ha",
    "Seer": "https://www.dewolfvie.net/vn/chucnang#h.2s0avvgyr6t9",
    "Guard": "https://www.dewolfvie.net/vn/chucnang#h.ne683ss63imm",
    "Witch": "https://www.dewolfvie.net/vn/chucnang#h.jb8i4v8ruvpi",
    "Hunter": "https://www.dewolfvie.net/vn/chucnang#h.30wa7yki033k",
    "Tough Guy": "https://www.dewolfvie.net/vn/chucnang#h.8ofxyfsrchwy",
    "Illusionist": "https://www.dewolfvie.net/vn/chucnang#h.22uhems1a6om",
    "Wolfman": "https://www.dewolfvie.net/vn/chucnang#h.4vfb9srnjzej",
    "Explorer": "https://www.dewolfvie.net/vn/chucnang#h.5n2k068a52q0",
    "Demon Werewolf": "https://www.dewolfvie.net/vn/chucnang#h.ln7finvlqa8r",
    "Assassin Werewolf": "https://www.dewolfvie.net/vn/chucnang#h.w0d62d7aiqjw",
    "Detective": "https://www.dewolfvie.net/vn/chucnang#h.g8we49sefmk"
}

# Mô tả chi tiết các vai trò
ROLE_DESCRIPTIONS = {
    "Villager": "Không có chức năng đặc biệt, tham gia thảo luận và bỏ phiếu ban ngày (từ ngày thứ hai). Phải chọn đáp án đúng trong bài toán cộng/trừ vào ban đêm để được quyền bỏ phiếu.",
    "Werewolf": "Mỗi đêm thảo luận trong wolf-chat và chọn giết 1 người bằng nút chọn. Biết ai là Nhà Ảo Giác (nếu có).",
    "Seer": "Mỗi đêm kiểm tra 1 người thuộc phe Dân hoặc Sói bằng nút chọn qua DM. Kết quả có thể bị đảo ngược nếu Nhà Ảo Giác bị soi trước đó.",
    "Guard": "Mỗi đêm bảo vệ 1 người bằng nút chọn qua DM, ngăn họ bị giết bởi Sói, Phù Thủy hoặc Thợ Săn.",
    "Witch": "Mỗi đêm biết ai bị chọn giết, có 1 lần duy nhất để cứu bằng nút 'Save' hoặc giết 1 người bằng nút chọn qua DM. Nhận thông báo muộn hơn để quyết định trong 20 giây cuối. Sau khi sử dụng chức năng, sẽ không còn nhận thông tin về người bị giết và nhận thông báo 'Không ai bị giết đêm nay!' mỗi đêm.",
    "Hunter": "Có 1 lần duy nhất trong đêm để giết 1 người bằng nút chọn qua DM.",
    "Tough Guy": "Thuộc phe Dân, có 2 mạng đối với các hành động giết vào ban đêm (Sói, Phù Thủy, Thợ Săn). Phải bị giết 2 lần vào ban đêm để chết hoàn toàn. Không có thông báo khi mất mạng. Tuy nhiên, nếu bị ngồi ghế điện (loại bởi bỏ phiếu ban ngày), sẽ chết ngay lập tức bất kể còn bao nhiêu mạng. Phải chọn đáp án đúng trong bài toán cộng/trừ vào ban đêm để được quyền bỏ phiếu.",
    "Illusionist": "Thuộc phe Sói, thắng cùng Sói nhưng không thức dậy trong wolf-chat và không biết ai là Sói. Sói biết Nhà Ảo Giác. Được tính vào Phe Dân khi kiểm đếm thắng thua. Nếu bị Tiên Tri soi, ra Phe Dân. Đêm tiếp theo, kết quả soi của Tiên Tri bị đảo ngược (Dân thành Sói, Sói thành Dân). Phải chọn đáp án đúng trong bài toán cộng/trừ vào ban đêm để được quyền bỏ phiếu.",
    "Wolfman": "Thuộc phe Sói, thức dậy cùng bầy Sói trong wolf-chat và tham gia chọn giết. Được tính là Sói khi kiểm đếm thắng thua. Nếu bị Tiên Tri soi, hiển thị thuộc Phe Dân.",
    "Explorer": "Từ đêm thứ hai, mỗi đêm phải chọn giết một người qua DM. Nếu chọn đúng Sói (không tính Nhà Ảo Giác), Sói sẽ chết. Nếu chọn trúng Phe Dân (tính cả Nhà Ảo Giác), Người Khám Phá sẽ chết. Có thể được bảo vệ bởi Bảo Vệ và cứu bởi Phù Thủy theo nguyên tắc game.",
    "Demon Werewolf": "Thuộc phe Sói, thức dậy cùng bầy Sói. Khi một Sói bất kỳ chết, Sói Quỷ có thể nguyền một người chơi duy nhất qua DM, biến họ thành Sói vào đêm tiếp theo. Người bị nguyền mất chức năng cũ và tham gia bầy Sói, ảnh hưởng đến kiểm đếm thắng thua. Trong đêm nguyền, mục tiêu của bầy Sói không chết.",
    "Assassin Werewolf": "Thuộc phe Sói, thức dậy cùng bầy Sói và tham gia chọn giết. Có một lần duy nhất trong game để chọn một người chơi và đoán vai trò của họ vào ban đêm. Nếu đoán đúng, người đó chết; nếu sai, Sói Ám Sát chết. Sói Ám Sát sẽ không ám sát được Dân Làng",
    "Detective": "Một lần duy nhất trong game, vào ban đêm, thám tử có thể chọn hai người chơi để xem họ có cùng phe hay không. Ảo giác và người sói được tính vào phe sói. Thám tử không thể tự chọn chính mình."
}

# Đường dẫn đến các tệp âm thanh
AUDIO_FILES = {
    "morning": "day_phase.wav",
    "night": "night_phase.mp3",
    "vote": "vote_phase.mp3",
    "hang": "sad_sound.mp3",
    "end_game": "end_game.mp3" 
}

# Phiên bản bot
BOT_VERSION = "DeWolfVie ver 5.15"