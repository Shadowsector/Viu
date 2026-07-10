"""Каталог «желаемых» анимаций — как prop_catalog, но для движений Шани."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .categories import ANIMATION_CATEGORIES

STATUS_WISHED = "wished"
STATUS_IMPORTED = "imported"
STATUS_LINKED = "linked"  # в Animator


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
    id: str = ""

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
        )

    def render_block(self) -> str:
        lines = [
            f"### {self.title_ru} (`{self.slug}`)",
            f"**Категория:** {self.category}",
            f"**Когда:** {self.when_used}",
            f"**Как выглядит:** {self.looks_like}",
            f"**Зачем:** {self.purpose}",
        ]
        if self.mixamo_hints:
            lines.append(f"**Mixamo:** {', '.join(self.mixamo_hints)}")
        if self.clip_file:
            lines.append(f"**Файл:** {self.clip_file} ({self.status})")
        elif self.status == STATUS_WISHED:
            lines.append("**Статус:** ещё не импортировано")
        return "\n".join(lines)


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
        ["Walking", "Walk Forward"],
        wave=1,
        animator_state="Walk",
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
        "Преграда на лучу, игривость, спрыгнуть с уступа.",
        "Присед-разгон, полёт, landing (можно отдельно fall).",
        "In Place; root motion выключен.",
        ["Jump", "Jumping"],
        wave=1,
    ),
    _w(
        "fall",
        "adventure",
        "Падение / приземление",
        "Сорвалась с ветки, failed jump, комедия.",
        "Потеря баланса или падение вниз, затем squat absorb.",
        "После jump fail или триггер с высоты.",
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
