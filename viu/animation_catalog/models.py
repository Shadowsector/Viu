"""Каталог «желаемых» анимаций — как prop_catalog, но для движений Шани."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .categories import ANIMATION_CATEGORIES

STATUS_WISHED = "wished"
STATUS_IMPORTED = "imported"
STATUS_LINKED = "linked"  # в Animator
STATUS_PENDING_REVIEW = "pending_review"

# Кому назначается клип. applies_to_shanya() — попадёт в Shanya_Idle_Stand.controller.
ANIMATION_SCOPES: Dict[str, Tuple[str, str]] = {
    "female_humanoid": (
        "Девушки-biped (Шаня + NPC)",
        "Female Humanoid (Mixamo). Идёт в Animator Шани и в общий пул для всех девушек игры.",
    ),
    "shanya_only": (
        "Только Шаня (уникальное)",
        "Только главная героиня — не предлагать NPC автоматически (особая походка, NSFW…).",
    ),
    "humanoid_npc_female": (
        "NPC: девушки (без Шани)",
        "Female biped, но осознанно не кладём на Shanya_Erisa — отдельный prefab позже.",
    ),
    "humanoid_any": (
        "Любой biped (м/ж)",
        "Универсальный humanoid — мужские NPC, общие клипы. Пока не в Animator Шани.",
    ),
    "creature_quadruped": (
        "Четвероногие",
        "Не humanoid — другой скелет/Animator. На Шаню не ставится.",
    ),
}

# Алиасы из старых версий каталога
SCOPE_ALIASES: Dict[str, str] = {
    "shanya_humanoid": "female_humanoid",
    "humanoid_female": "female_humanoid",
}

DEFAULT_SCOPE = "female_humanoid"


def normalize_scope(scope: str) -> str:
    s = (scope or "").strip() or DEFAULT_SCOPE
    return SCOPE_ALIASES.get(s, s)


def applies_to_shanya(scope: str) -> bool:
    """Клип попадёт в Shanya_Idle_Stand при sync."""
    return normalize_scope(scope) in ("female_humanoid", "shanya_only")


def scope_save_warning(scope: str) -> str:
    """Текст предупреждения при сохранении, или пусто."""
    s = normalize_scope(scope)
    if applies_to_shanya(s):
        return ""
    if s == "humanoid_npc_female":
        return (
            "Scope «NPC: девушки (без Шани)» — клип **не** попадёт в Animator Шани.\n"
            "Если нужно «все девушки включая Шаню» — выбери «Девушки-biped (Шаня + NPC)»."
        )
    if s == "humanoid_any":
        return (
            "Scope «Любой biped» — пока **не** кладём в Animator Шани "
            "(задумано для м/ж NPC). Для бега назад у девушек — «Девушки-biped (Шаня + NPC)»."
        )
    if s == "creature_quadruped":
        return "Четвероногие — не для Шани и не для humanoid Animator."
    return ""


def import_review_id(original_name: str) -> str:
    return hashlib.sha256(original_name.lower().encode("utf-8")).hexdigest()[:16]


def wish_id(slug: str) -> str:
    return hashlib.sha256(slug.lower().encode("utf-8")).hexdigest()[:16]


@dataclass
class AnimationWish:
    """Одна «ячейка» каталога — что нужно игре и как это выглядит."""

    slug: str
    category: str
    title_ru: str
    when_used: str
    looks_like: str
    purpose: str
    mixamo_hints: List[str] = field(default_factory=list)
    animator_state: str = ""
    wave: int = 1
    status: str = STATUS_WISHED
    clip_file: str = ""
    notes: str = ""
    scope: str = DEFAULT_SCOPE
    reviewed: bool = False
    id: str = ""
    # Граф переходов + Comfy-референс (MoCap)
    enters_from: List[str] = field(default_factory=list)
    exits_to: List[str] = field(default_factory=list)
    ref_video: str = ""
    seed_frame: str = ""
    comfy_score: int = 0

    def __post_init__(self) -> None:
        if not self.id:
            self.id = wish_id(self.slug)
        if not self.animator_state:
            self.animator_state = _default_state_name(self.slug)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AnimationWish":
        return AnimationWish(
            id=str(d.get("id") or wish_id(str(d.get("slug", "")))),
            slug=str(d.get("slug", "")),
            category=str(d.get("category", "special")),
            title_ru=str(d.get("title_ru", "")),
            when_used=str(d.get("when_used", "")),
            looks_like=str(d.get("looks_like", "")),
            purpose=str(d.get("purpose", "")),
            mixamo_hints=list(d.get("mixamo_hints") or []),
            animator_state=str(d.get("animator_state") or ""),
            wave=int(d.get("wave") or 1),
            status=str(d.get("status") or STATUS_WISHED),
            clip_file=str(d.get("clip_file") or ""),
            notes=str(d.get("notes") or ""),
            scope=normalize_scope(str(d.get("scope") or DEFAULT_SCOPE)),
            reviewed=bool(d.get("reviewed", False)),
            enters_from=list(d.get("enters_from") or []),
            exits_to=list(d.get("exits_to") or []),
            ref_video=str(d.get("ref_video") or ""),
            seed_frame=str(d.get("seed_frame") or ""),
            comfy_score=int(d.get("comfy_score") or 0),
        )

    def render_block(self) -> str:
        lines = [
            f"### {self.title_ru} (`{self.slug}`)",
            f"**Категория:** {self.category}",
            f"**Scope:** {normalize_scope(self.scope)}",
            f"**Когда:** {self.when_used}",
            f"**Как выглядит:** {self.looks_like}",
            f"**Зачем:** {self.purpose}",
        ]
        if self.enters_from or self.exits_to:
            lines.append(
                f"**Граф:** {self.enters_from or '—'} → `{self.slug}` → {self.exits_to or '—'}"
            )
        if self.ref_video:
            lines.append(f"**Comfy ref:** {self.ref_video} (score {self.comfy_score}/5)")
        if self.seed_frame:
            lines.append(f"**Seed (last frame):** {self.seed_frame}")
        if self.mixamo_hints:
            lines.append(f"**Mixamo:** {', '.join(self.mixamo_hints)}")
        if self.clip_file:
            lines.append(f"**Файл:** {self.clip_file} ({self.status})")
        elif self.status == STATUS_WISHED:
            lines.append("**Статус:** ещё не импортировано")
        return "\n".join(lines)


@dataclass
class AnimationImportReview:
    """Один FBX из Inbox — ждёт описания от Дена."""

    original_name: str
    clip_file: str
    suggested_slug: str = ""
    suggested_title: str = ""
    category: str = "locomotion"
    when_used: str = ""
    looks_like: str = ""
    purpose: str = ""
    scope: str = DEFAULT_SCOPE
    animator_state: str = ""
    notes: str = ""
    reviewed: bool = False
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = import_review_id(self.original_name)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AnimationImportReview":
        return AnimationImportReview(
            id=str(d.get("id") or import_review_id(str(d.get("original_name", "")))),
            original_name=str(d.get("original_name", "")),
            clip_file=str(d.get("clip_file", "")),
            suggested_slug=str(d.get("suggested_slug") or ""),
            suggested_title=str(d.get("suggested_title") or ""),
            category=str(d.get("category") or "locomotion"),
            when_used=str(d.get("when_used") or ""),
            looks_like=str(d.get("looks_like") or ""),
            purpose=str(d.get("purpose") or ""),
            scope=normalize_scope(str(d.get("scope") or DEFAULT_SCOPE)),
            animator_state=str(d.get("animator_state") or ""),
            notes=str(d.get("notes") or ""),
            reviewed=bool(d.get("reviewed", False)),
        )


def _default_state_name(slug: str) -> str:
    parts = re.split(r"[_\-\s]+", slug.strip())
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _w(
    slug: str,
    category: str,
    title_ru: str,
    when_used: str,
    looks_like: str,
    purpose: str,
    mixamo_hints: List[str],
    wave: int = 1,
    animator_state: str = "",
) -> AnimationWish:
    return AnimationWish(
        slug=slug,
        category=category,
        title_ru=title_ru,
        when_used=when_used,
        looks_like=looks_like,
        purpose=purpose,
        mixamo_hints=mixamo_hints,
        wave=wave,
        animator_state=animator_state,
    )


# Стартовый каталог — Viu матчит FBX по slug/hints и знает «зачем» клип.
DEFAULT_WISHES: List[AnimationWish] = [
    # --- locomotion ---
    _w(
        "idle",
        "locomotion",
        "Стоит на месте",
        "Шаня ничего не делает: дом у таскбара, ждёт, смотрит в сторону камеры.",
        "Ровная стойка, лёгкое дыхание, вес на обе ноги, хвост/волосы чуть живут.",
        "Базовое состояние Animator, переход из любого действия.",
        ["Idle", "Breathing Idle", "Idle Swaying"],
        wave=1,
        animator_state="Idle",
    ),
    _w(
        "walk",
        "locomotion",
        "Идёт шагом",
        "A/D по лучу карты или вдоль полосы оверлея; модель развёрнута в профиль кодом.",
        "Ровная ходьба «вперёд» по клипу; направление задаёт поворот модели, не root motion.",
        "Параметр Speed > 0, основная локомоция.",
        ["Walking", "Walk Forward", "Female Walk", "Standard Walk"],
        wave=1,
        animator_state="Walk",
    ),
    _w(
        "walk_back",
        "locomotion",
        "Идёт спиной / отступает",
        "S к камере в оверлее; отступление от NPC; выход из сарая лицом к зрителю.",
        "Шаги назад, корпус чуть наклонён, взгляд вперёд (к камере).",
        "Отдельный клип лучше, чем проигрывать Walk задом (ноги).",
        ["Walking Backward", "Female Walk Backward", "Backwards Walk"],
        wave=1,
        animator_state="WalkBack",
    ),
    _w(
        "run",
        "locomotion",
        "Бежит",
        "Длинный луч снежинки, спешит домой, погоня, дождь — быстрее Walk.",
        "Бег на месте или с лёгким смещением; ноги чаще, корпус наклонён.",
        "Speed высокий или отдельное состояние Run.",
        ["Running", "Jog Forward"],
        wave=1,
        animator_state="Run",
    ),
    _w(
        "sneak",
        "locomotion",
        "Крадётся",
        "Подкрасться к NPC, пройти мимо спящего, «охота» в adventure.",
        "Пригнулась, шаги короткие и осторожные, взгляд вперёд.",
        "Adventure + позже stealth на карте.",
        ["Sneaking", "Crouched Walk"],
        wave=2,
    ),
    _w(
        "walk_proud",
        "locomotion",
        "Идёт гордо",
        "После покупки, победы, с добычей — характер «кошка-доминанта».",
        "Подбородок выше, грудь вперёд, медленный уверенный шаг.",
        "Эмоциональная альтернатива Walk по триггеру настроения.",
        ["Confident Walk", "Strut Walk"],
        wave=3,
    ),
    # --- transition ---
    _w(
        "sit_down",
        "transition",
        "Садится",
        "Перед тем как сидеть на стуле, коврике, краю сарая — один раз проиграть вход.",
        "Опускается: согнула колени, перенос веса, ягодицы вниз, руки для баланса.",
        "Переход Standing → Sit; без этого crossfade из Idle выглядит телепортом.",
        ["Sitting Down", "Sit Down"],
        wave=1,
        animator_state="SitDown",
    ),
    _w(
        "stand_up",
        "transition",
        "Встаёт",
        "После Sit/Sleep/Lie — выход из позы.",
        "Опирается, разгибает ноги, выпрямляет спину, стабилизируется в стойке.",
        "Sit/Sleep → Idle.",
        ["Stand Up", "Getting Up"],
        wave=1,
        animator_state="StandUp",
    ),
    _w(
        "lie_down",
        "transition",
        "Ложится",
        "Перед сном на коврике, в сарае, на траве.",
        "Колени к полу, корпус опускается, может лечь на бок или на спину.",
        "Standing → Sleep loop.",
        ["Lying Down", "Lay Down"],
        wave=1,
        animator_state="LieDown",
    ),
    # --- rest ---
    _w(
        "sit_idle",
        "rest",
        "Сидит (цикл)",
        "Стул, ящик, край сарая, prop с affordance sit.",
        "Сидит неподвижно или чуть покачивается, руки на коленях или опирается.",
        "Loop после SitDown.",
        ["Sitting Idle", "Sitting"],
        wave=1,
        animator_state="Sit",
    ),
    _w(
        "sleep_idle",
        "rest",
        "Спит (цикл)",
        "Ночь у таскбара, нет кровати — Viu предложила коврик; внутри сарая.",
        "Лежит, грудь поднимается, может свернуться — loop.",
        "Loop после LieDown; affordance sleep.",
        ["Sleeping Idle", "Sleep"],
        wave=1,
        animator_state="Sleep",
    ),
    _w(
        "yawn",
        "rest",
        "Зевает",
        "Проснулась, скучно, долго Idle — кошачий быт.",
        "Рот широко, глаза прищурены, плечи вверх, медленно.",
        "Короткий one-shot или overlay на Idle.",
        ["Yawn", "Yawning"],
        wave=1,
    ),
    _w(
        "stretch",
        "rest",
        "Потягивается",
        "После сна, перед приключением, утро у дома.",
        "Руки вверх или в стороны, прогиб/spine, как кошка.",
        "One-shot из Idle; Viu может предложить после sleep.",
        ["Stretching", "Stretch"],
        wave=1,
    ),
    # --- routine ---
    _w(
        "groom",
        "routine",
        "Умывается",
        "Дома «балдеет», после еды, после дождя.",
        "Лизать/тереть ладонью «морду», кошачий жест (человекоидно).",
        "Idle-вариант домашней жизни.",
        ["Face Wash", "Cleaning Face"],
        wave=2,
    ),
    _w(
        "look_around",
        "routine",
        "Оглядывается",
        "Новый prop, звук, вход в сарай.",
        "Голова влево-вправо, корпус почти на месте.",
        "Перед interaction или adventure scout.",
        ["Looking Around", "Look Around"],
        wave=1,
    ),
    _w(
        "lean",
        "routine",
        "Облокачивается",
        "Стол, стена сарая, дверной косяк — affordance lean.",
        "Один локоть / плечо на опору, вес смещён, расслабленная стойка.",
        "Быт у сарая; связка с prop lean.",
        ["Idle Lean", "Standing Lean", "Leaning"],
        wave=2,
    ),
    _w(
        "knock",
        "routine",
        "Стучит в дверь",
        "Перед входом в сарай / Instance; зовёт кого-то.",
        "Подход к двери, рука стучит 2–3 раза, пауза.",
        "Триггер у Anchor_BarnEntrance.",
        ["Knocking", "Door Knock"],
        wave=2,
    ),
    _w(
        "look_window",
        "routine",
        "Смотрит в окно",
        "Внутри сарая у окна; снаружи — выглядывает.",
        "Поворот к окну, рука на раме опционально, пауза взгляда.",
        "Атмосфера Instance-режима.",
        ["Window Peek", "Looking Out Window", "Peek"],
        wave=2,
    ),
    # --- hygiene ---
    _w(
        "shower",
        "hygiene",
        "Принимает душ",
        "В доме есть душ; Viu предложила после «грязи» или сюжета.",
        "Стоит под струёй, руки на волосах, может потереть плечи.",
        "Сцена дома, позже NSFW-ветки отдельно.",
        ["Showering", "Taking Shower"],
        wave=3,
    ),
    _w(
        "bath",
        "hygiene",
        "В ванне",
        "Купание в доме/сарае с водой.",
        "Сидит в ванне, плечи в воде, движения медленные.",
        "Долгая сцена rest+hygiene.",
        ["Bath", "Sitting In Bath"],
        wave=3,
    ),
    # --- social ---
    _w(
        "greeting",
        "social",
        "Приветствует",
        "Игрок вернулся, новый NPC, начало чата.",
        "Махнул рукой, кивок, лёгкий наклон — дружелюбно.",
        "Триггер от диалога или клика по Шане.",
        ["Waving", "Greeting", "Hello"],
        wave=2,
    ),
    # --- interaction ---
    _w(
        "take",
        "interaction",
        "Поднимает предмет",
        "Prop affordance take/grab: свеча, тарелка, монетка.",
        "Наклон, рука к полу/столу, объект в руке (позже attach point).",
        "Связь с prop_catalog.",
        ["Picking Up", "Pick Up"],
        wave=1,
    ),
    _w(
        "throw",
        "interaction",
        "Бросает",
        "После take; игривый бой; кинуть мяч.",
        "Замах, бросок вперёд, follow-through.",
        "Affordance throw.",
        ["Throw", "Throw Object"],
        wave=1,
    ),
    # --- food ---
    _w(
        "eat",
        "food",
        "Ест",
        "Prop food, стол в сарае.",
        "Рука ко рту, жует, может держать яблоко.",
        "Affordance eat.",
        ["Eating", "Standing Eating"],
        wave=2,
    ),
    _w(
        "drink",
        "food",
        "Пьёт",
        "Кружка, ручей, prop drink.",
        "Подносит чашку/бутылку ко рту, наклон головы.",
        "Affordance drink (добавим в interactions).",
        ["Drinking"],
        wave=2,
    ),
    _w(
        "cook",
        "food",
        "Готовит",
        "Костёр, печь в сарае — позже props.",
        "Перемешивает, наклон над котлом, стоит у плиты.",
        "Сцена с kitchen props.",
        ["Cooking", "Stirring Pot"],
        wave=3,
    ),
    # --- fight ---
    _w(
        "attack_claws",
        "fight",
        "Атака когтями",
        "Игривая драка, охота, защита — не обязательно gore.",
        "Прыжок или выпад, руки как когти, быстрый swipe.",
        "Combat; позже свой Cascadeur-вариант «кошачий».",
        ["Standing Melee Attack", "Cat stance", "Scratch"],
        wave=1,
    ),
    _w(
        "hit_react",
        "fight",
        "Получила удар",
        "Промах врага, шутка, stumble.",
        "Отшатнулась, руки к корпусу, короткая grimace.",
        "Переход в Idle/Stagger.",
        ["Hit Reaction", "Recoil"],
        wave=2,
    ),
    # --- adventure ---
    _w(
        "climb_up",
        "adventure",
        "Взбирается (полный цикл)",
        "Дерево, забор, сарай — когда affordance climb и нет клипа «только руки».",
        "Подтягивается: хват, нога на уступ, подтягивание, второй шаг, выпрямление в стойку наверху.",
        "Главный climb; Viu предлагает, если «не лезет на дерево».",
        ["Climbing", "Climb Up Wall", "Free Hang Climb"],
        wave=1,
    ),
    _w(
        "jump",
        "adventure",
        "Прыжок",
        "С земли вверх: перепрыгнуть низкое, игривость. Не путать со спрыгиванием с крыши (fall / позже jump_off).",
        "Присед → отрыв → полёт → приземление. Клип In Place; смещение по миру — код или отдельный fall с высоты.",
        "In Place Jump с Mixamo; спрыгнуть с уступа = jump с края + fall, или Comfy/Cascadeur позже.",
        ["Jump", "Jumping"],
        wave=1,
    ),
    _w(
        "fall",
        "adventure",
        "Падение / приземление",
        "Сорвалась с ветки, прыжок с высоты сарая, failed land.",
        "Потеря баланса или падение вниз, затем squat absorb при касании земли.",
        "После jump с высоты или триггер падения; не заменяет jump с места.",
        ["Falling Idle", "Hard Landing", "Fall"],
        wave=1,
    ),
    _w(
        "hide_peek",
        "adventure",
        "Прячется и выглядывает",
        "За деревом, угол сарая, stealth adventure.",
        "Прижалась к cover, голова выглядывает в сторону.",
        "Adventure stealth; «за деревом» из твоего списка.",
        ["Peek", "Hide", "Cover Idle"],
        wave=2,
    ),
    _w(
        "scout",
        "adventure",
        "Осматривает местность",
        "Новая ветка снежинки, перед входом в barn.",
        "Рука над глазами или руки на бёдрах, поворот корпуса, осторожность.",
        "Перед transition в локацию.",
        ["Looking Around", "Inspect", "Scout"],
        wave=2,
    ),
    # --- dance ---
    _w(
        "dance",
        "dance",
        "Танцует",
        "Награда, хорошее настроение, деньги потратила на «радость».",
        "Ритмичные шаги, может притопывать — loop или one-shot.",
        "Эмоция + dance category.",
        ["Dancing", "Dance"],
        wave=3,
    ),
    # --- special ---
    _w(
        "stumble",
        "special",
        "Споткнулась",
        "Комедия, усталость, низкая ловкость.",
        "Краткий loss of balance, не полный fall.",
        "Между Walk и Fall.",
        ["Stumble", "Trip"],
        wave=3,
    ),
]


def validate_category(category: str) -> bool:
    return category in ANIMATION_CATEGORIES
