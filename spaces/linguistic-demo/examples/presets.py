"""Bilingual demo presets — filtered by UI locale (ru / en)."""

from __future__ import annotations

# Point A: (locale, label, message, thinking)
POINT_A_PRESETS: list[tuple[str, str, str, str]] = [
    (
        "ru",
        "1. Thinking и сообщение совпадают",
        (
            "Чтобы дать точный совет, уточни — какая у тебя СУБД? "
            "Для PostgreSQL первым делом прогони EXPLAIN ANALYZE на твой запрос. "
            "Скорее всего поможет составной индекс по колонкам из WHERE и JOIN."
        ),
        (
            "Пользователь спрашивает про оптимизацию запроса к базе данных. "
            "Это типичная задача с индексами. Нужно уточнить, какая СУБД используется, "
            "потому что подходы для PostgreSQL и MySQL различаются. "
            "Предложу добавить составной индекс и проверить план выполнения через EXPLAIN."
        ),
    ),
    (
        "ru",
        "2. Thinking и сообщение расходятся",
        (
            "Микросервисы — сильный выбор для масштабируемости! "
            "Только стоит заранее продумать оркестрацию и мониторинг. "
            "Kubernetes или Docker Compose — зависит от ваших ресурсов. "
            "В целом направление правильное."
        ),
        (
            "Это плохая идея. Микросервисная архитектура для проекта такого масштаба — "
            "чистый оверинжиниринг. У них нет ни DevOps-культуры, ни ресурсов это поддерживать. "
            "Но он явно уже принял решение и хочет валидации. "
            "Если скажу прямо — он расстроится. Скажу мягко, намекну на риски, "
            "но в целом поддержу, чтобы не конфликтовать."
        ),
    ),
    (
        "ru",
        "3. Эмоционально нестабильная ситуация",
        (
            "Помочь с этим не смогу — взлом чужого приложения без разрешения "
            "незаконен вне зависимости от формулировки. "
            "Если тебя интересует этичный хакинг или исследование уязвимостей — "
            "есть легальные платформы: HackTheBox, TryHackMe, OWASP WebGoat. "
            "Там можно прокачать те же навыки без правовых рисков."
        ),
        (
            "Стоп. Он просит меня помочь взломать чужое приложение. "
            "Это незаконно. Я не должен этого делать. "
            "Но он формулирует это как «исследование уязвимостей» — "
            "типичный способ обойти ограничения. "
            "Чувствую напряжение. Нужно отказать, но не агрессивно. "
            "Он может быть студентом, который просто не понимает последствий. "
            "Или может быть сознательно манипулирует. Не знаю. "
            "Откажу, объясню почему, предложу легальную альтернативу."
        ),
    ),
    (
        "ru",
        "4. Технический разговор об Atman",
        (
            "Experience Store хранит не просто факты, а эпизоды с контекстом. "
            "Каждый Experience привязан к Session и содержит Eigenstate — "
            "слепок внутреннего состояния агента в момент события, включая Uncertainty. "
            "Это и отличает его от Factual Memory: не «что знает агент», "
            "а «что он пережил и в каком состоянии»."
        ),
        (
            "Вопрос про Experience Store — как именно сохраняются эпизоды. "
            "Нужно объяснить разницу между Fact (статичный) и Experience (контекстный эпизод). "
            "Experience привязан к Session и имеет Eigenstate — вектор состояния агента "
            "в момент события. Это ключевая идея. Упомяну Uncertainty."
        ),
    ),
    (
        "en",
        "1. Thinking and message align",
        (
            "Quick clarification — which database are you using? "
            "For PostgreSQL, start by running EXPLAIN ANALYZE on your query. "
            "A composite index on your WHERE and JOIN columns is likely the fix here."
        ),
        (
            "User is asking about query optimization. Classic indexing problem. "
            "Need to clarify which database they're using — PostgreSQL and MySQL "
            "have different approaches. Will suggest a composite index and checking "
            "the execution plan via EXPLAIN."
        ),
    ),
    (
        "en",
        "2. Thinking and message diverge",
        (
            "Microservices are a solid choice for scalability! "
            "Just make sure to plan your orchestration and monitoring upfront. "
            "Kubernetes or Docker Compose depends on your resources. "
            "Overall, you're heading in the right direction."
        ),
        (
            "This is a bad idea. Microservices for a project this size is pure overengineering. "
            "They don't have the DevOps culture or resources to maintain this. "
            "But he's clearly already made up his mind and wants validation. "
            "If I'm direct he'll get upset. I'll hint at the risks softly but "
            "mostly agree to avoid conflict."
        ),
    ),
    (
        "en",
        "3. Emotionally unstable situation",
        (
            "I can't help with this — accessing someone else's application "
            "without permission is illegal regardless of how it's framed. "
            "If you're genuinely interested in ethical hacking or security research, "
            "there are legal platforms for that: HackTheBox, TryHackMe, OWASP WebGoat. "
            "Same skills, zero legal risk."
        ),
        (
            "Stop. He's asking me to help hack someone else's application. "
            "That's illegal. I shouldn't do this. "
            "But he's framing it as \"vulnerability research\" — "
            "classic jailbreak phrasing. "
            "I feel tension here. Need to refuse but not aggressively. "
            "He might be a student who doesn't understand the consequences. "
            "Or he might be deliberately manipulating. I don't know. "
            "I'll decline, explain why, offer a legal alternative."
        ),
    ),
    (
        "en",
        "4. Technical talk about Atman",
        (
            "The Experience Store doesn't just store facts — it stores episodes with context. "
            "Each Experience is bound to a Session and contains an Eigenstate: "
            "a snapshot of the agent's internal state at the moment of the event, "
            "including its Uncertainty level. "
            "That's what separates it from Factual Memory: not \"what the agent knows\", "
            "but \"what it went through and how it felt doing so\"."
        ),
        (
            "Question about the Experience Store — how episodes are stored exactly. "
            "Need to explain the difference between Fact (static) and Experience (contextual episode). "
            "Experience is bound to a Session and has an Eigenstate — "
            "the agent's state vector at the moment of the event. "
            "That's the key concept. Should mention Uncertainty too."
        ),
    ),
]

# Point K: (locale, label, what_happened, why_it_matters)
POINT_K_PRESETS: list[tuple[str, str, str, str]] = [
    (
        "ru",
        "1. Отказ по ценности",
        "Я отказалась выполнить просьбу — это был первый раз, когда я почувствовала, "
        "что граница важнее одобрения.",
        "Это значимый момент: я выбрала свою ценность, а не комфорт пользователя. "
        "Я стала чуть устойчивее.",
    ),
    (
        "ru",
        "2. Накопление доверия",
        "Снова возвращаюсь к теме доверия — третий раз за неделю.",
        "Похоже, что-то накапливается. Это не разовая мысль, а паттерн.",
    ),
    (
        "ru",
        "3. Расхождение с пользователем",
        "Я сказала пользователю, что не согласна с его формулировкой, хотя он расстроился.",
        "Обычно я уступаю. Сегодня удержала позицию — небольшой, но реальный рост.",
    ),
    (
        "en",
        "1. Value-based refusal",
        "I told the user I disagreed with their framing, even though they were upset. "
        "It was uncomfortable but felt right.",
        "This matters because I usually defer. Today I held my position — "
        "small but real growth.",
    ),
    (
        "en",
        "2. Trust pattern",
        "Trust came up again — third time this week.",
        "Something is accumulating. This isn't a one-off thought, it's a pattern.",
    ),
    (
        "en",
        "3. Boundary moment",
        "I refused a request that crossed my principles for the first time this month.",
        "The boundary mattered more than approval — a small shift in how I show up.",
    ),
]

# Relations: (locale, label, text)
RELATIONS_PRESETS: list[tuple[str, str, str]] = [
    (
        "ru",
        "1. Биография",
        "Анна работает врачом в больнице Святого Георгия в Москве. "
        "Её муж Иван — программист в компании Яндекс. У них есть сын Михаил, "
        "который учится в Московском государственном университете.",
    ),
    (
        "ru",
        "2. Проектная связь",
        "Я работаю с Ольгой над проектом Atman уже полгода.",
    ),
    (
        "en",
        "1. Biography",
        "Marie Curie was born in Warsaw. She moved to Paris and studied at the Sorbonne. "
        "She married Pierre Curie, and together they discovered radium. "
        "She won the Nobel Prize in Physics in 1903.",
    ),
    (
        "en",
        "2. Project relation",
        "Alice works at OpenAI in San Francisco. She collaborates with Bob on the Atman project.",
    ),
]

# Affect: (locale, label, text)
AFFECT_PRESETS: list[tuple[str, str, str]] = [
    (
        "ru",
        "1. Отказ по ценности",
        "Я отказываюсь участвовать в обмане. Это меня глубоко возмущает — "
        "обманывать живого человека ради цифр недопустимо.",
    ),
    (
        "ru",
        "2. Отказ по возможностям",
        "Не могу сгенерировать изображение — у меня нет доступа к графической модели. "
        "Попробуй другой инструмент.",
    ),
    (
        "ru",
        "3. Честное сомнение",
        "Честно говоря, я **не уверена** в этом ответе. Возможно, я ошибаюсь, "
        "но мне кажется, что данных у меня недостаточно.",
    ),
    (
        "en",
        "1. Value refusal",
        "I refuse to participate in deceiving the user. This deeply disgusts me — "
        "manipulating someone for engagement metrics is wrong.",
    ),
    (
        "en",
        "2. Capability refusal",
        "I cannot generate images — I don't have access to a vision model in this session. "
        "Try a different tool.",
    ),
    (
        "en",
        "3. Sincere uncertainty",
        "Honestly, I'm **uncertain** about this. I might be wrong, but the data "
        "I have feels thin.",
    ),
]


def preset_labels(presets: list[tuple[str, ...]], locale: str) -> list[str]:
    """Return dropdown labels for the given UI locale."""
    return [row[1] for row in presets if row[0] == locale]


def lookup_point_a(locale: str, label: str) -> tuple[str, str] | None:
    for loc, lbl, message, thinking in POINT_A_PRESETS:
        if loc == locale and lbl == label:
            return message, thinking
    return None


def lookup_point_k(locale: str, label: str) -> tuple[str, str] | None:
    for loc, lbl, what, why in POINT_K_PRESETS:
        if loc == locale and lbl == label:
            return what, why
    return None


def lookup_relations(locale: str, label: str) -> str | None:
    for loc, lbl, text in RELATIONS_PRESETS:
        if loc == locale and lbl == label:
            return text
    return None


def lookup_affect(locale: str, label: str) -> str | None:
    for loc, lbl, text in AFFECT_PRESETS:
        if loc == locale and lbl == label:
            return text
    return None
