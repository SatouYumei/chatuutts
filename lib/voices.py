"""音色、风格和角色目录。界面上的名字对应接口里的语音参数。"""

STYLE_LABELS = {
    "general": "一般",
    "affectionate": "亲切",
    "angry": "生气",
    "assistant": "助手",
    "calm": "平静",
    "chat": "聊天",
    "cheerful": "欢快",
    "customerservice": "客服",
    "disgruntled": "不满",
    "fearful": "害怕",
    "gentle": "温柔",
    "lyrical": "抒情",
    "newscast": "新闻",
    "poetry-reading": "朗诵",
    "sad": "难过",
    "serious": "严肃",
    "depressed": "沮丧",
    "embarrassed": "尴尬",
    "envious": "羡慕",
    "narration-professional": "专业旁白",
    "newscast-casual": "轻松新闻",
    "narration-relaxed": "松弛旁白",
    "sports-commentary": "解说",
    "sports-commentary-excited": "激动解说",
    "advertisement-upbeat": "广告",
}

ROLE_LABELS = {
    "Default": "默认",
    "Girl": "女孩",
    "Boy": "男孩",
    "YoungAdultFemale": "青年女",
    "YoungAdultMale": "青年男",
    "OlderAdultFemale": "中年女",
    "OlderAdultMale": "中年男",
    "SeniorFemale": "老年女",
    "SeniorMale": "老年男",
    "Narrator": "旁白",
}

_AGE_ROLES = (
    "Girl",
    "Boy",
    "YoungAdultFemale",
    "YoungAdultMale",
    "OlderAdultFemale",
    "OlderAdultMale",
    "SeniorFemale",
    "SeniorMale",
)

VOICES = [
    {
        "id": "zh-CN-XiaomoNeural",
        "short": "Xiaomo",
        "desc": "女声 · 柔和",
        "styles": (
            "affectionate",
            "angry",
            "calm",
            "cheerful",
            "depressed",
            "disgruntled",
            "embarrassed",
            "envious",
            "fearful",
            "gentle",
            "sad",
            "serious",
        ),
        "roles": _AGE_ROLES,
    },
    {
        "id": "zh-CN-XiaoxiaoNeural",
        "short": "Xiaoxiao",
        "desc": "女声 · 清晰",
        "styles": (
            "affectionate",
            "angry",
            "assistant",
            "calm",
            "chat",
            "cheerful",
            "customerservice",
            "disgruntled",
            "fearful",
            "gentle",
            "lyrical",
            "newscast",
            "poetry-reading",
            "sad",
            "serious",
        ),
        "roles": _AGE_ROLES,
    },
    {
        "id": "zh-CN-YunxiNeural",
        "short": "Yunxi",
        "desc": "男声 · 稳重",
        "styles": (
            "angry",
            "assistant",
            "cheerful",
            "depressed",
            "disgruntled",
            "embarrassed",
            "fearful",
            "narration-relaxed",
            "sad",
            "serious",
        ),
        "roles": ("Narrator", "YoungAdultMale", "Boy"),
    },
    {
        "id": "zh-CN-YunyangNeural",
        "short": "Yunyang",
        "desc": "男声 · 新闻",
        "styles": ("customerservice", "narration-professional", "newscast-casual"),
        "roles": (),
    },
    {
        "id": "zh-CN-XiaoyiNeural",
        "short": "Xiaoyi",
        "desc": "女声 · 活泼",
        "styles": (
            "affectionate",
            "angry",
            "cheerful",
            "disgruntled",
            "embarrassed",
            "fearful",
            "gentle",
            "sad",
            "serious",
        ),
        "roles": (),
    },
    {
        "id": "zh-CN-XiaoxuanNeural",
        "short": "Xiaoxuan",
        "desc": "女声 · 成熟",
        "styles": ("angry", "calm", "cheerful", "depressed", "disgruntled", "fearful", "gentle", "serious"),
        "roles": _AGE_ROLES,
    },
    {
        "id": "zh-CN-XiaohanNeural",
        "short": "Xiaohan",
        "desc": "女声 · 沉稳",
        "styles": (
            "affectionate",
            "angry",
            "calm",
            "cheerful",
            "disgruntled",
            "embarrassed",
            "fearful",
            "gentle",
            "sad",
            "serious",
        ),
        "roles": _AGE_ROLES,
    },
    {
        "id": "zh-CN-YunjianNeural",
        "short": "Yunjian",
        "desc": "男声 · 运动",
        "styles": ("narration-relaxed", "sports-commentary", "sports-commentary-excited"),
        "roles": (),
    },
    {
        "id": "zh-CN-YunfengNeural",
        "short": "Yunfeng",
        "desc": "男声 · 激情",
        "styles": ("angry", "cheerful", "depressed", "disgruntled", "fearful", "sad", "serious"),
        "roles": (),
    },
    {
        "id": "zh-CN-YunhaoNeural",
        "short": "Yunhao",
        "desc": "男声 · 阳光",
        "styles": ("advertisement-upbeat",),
        "roles": (),
    },
]

# 本地 Kokoro 模型的说话人编号。3–57 是女声，58–102 是男声。
_LOCAL_VOICES = (
    (3, "本地 女1"),
    (18, "本地 女2"),
    (30, "本地 女3"),
    (45, "本地 女4"),
    (60, "本地 男1"),
    (72, "本地 男2"),
    (85, "本地 男3"),
    (95, "本地 男4"),
)

VOICES += [
    {
        "id": f"local:{sid}",
        "short": short,
        "desc": "离线 · " + ("女声" if sid < 58 else "男声"),
        "styles": (),
        "roles": (),
    }
    for sid, short in _LOCAL_VOICES
]


def voice_by_id(voice_id):
    for voice in VOICES:
        if voice["id"] == voice_id:
            return voice
    return None


def voice_choices(current_id):
    choices = [(voice["id"], voice["short"], voice["desc"]) for voice in VOICES]
    if current_id and not any(item[0] == current_id for item in choices):
        short = current_id.split("-")[-1].replace("Neural", "") or current_id
        choices.insert(0, (current_id, short, "当前音色"))
    return choices


def style_choices(voice_id, current_id=None):
    voice = voice_by_id(voice_id)
    styles = ["general"]
    if voice:
        styles.extend(voice["styles"])
    if current_id and current_id not in styles:
        styles.append(current_id)
    return [(style_id, STYLE_LABELS.get(style_id, style_id)) for style_id in styles]


def role_choices(voice_id, current_id=None):
    voice = voice_by_id(voice_id)
    roles = ["Default"]
    if voice:
        roles.extend(voice["roles"])
    if current_id and current_id not in roles:
        roles.append(current_id)
    return [(role_id, ROLE_LABELS.get(role_id, role_id)) for role_id in roles]


def voice_short(voice_id):
    for item_id, short, _desc in voice_choices(voice_id):
        if item_id == voice_id:
            return short
    return voice_id or ""


def style_label(style_id):
    return STYLE_LABELS.get(style_id, style_id or "")


def role_label(role_id):
    return ROLE_LABELS.get(role_id, role_id or "")


def profile_summary(profile):
    parts = [
        voice_short(profile["VOICE"]),
        style_label(profile["VOICE_STYLE"]),
        f"语速 {int(profile['SPEED'])}",
    ]
    role = profile.get("VOICE_ROLE") or "Default"
    if role != "Default":
        parts.append(role_label(role))
    volume = int(profile.get("VOLUME", 100))
    if volume != 100:
        parts.append(f"音量 {volume}")
    return " · ".join(parts)
