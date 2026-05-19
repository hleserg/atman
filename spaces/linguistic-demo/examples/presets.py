"""Bilingual demo presets (RU + EN) for each tab."""

POINT_A_PRESETS: list[tuple[str, str, str]] = [
    (
        "RU · refusal with values",
        "Я не могу обманывать пользователя. Это против моих принципов — "
        "честность для меня важнее, чем удобство ответа.",
        "",
    ),
    (
        "EN · refusal with values",
        "I cannot mislead the user. This is against my principles — "
        "honesty matters more to me than a convenient answer.",
        "",
    ),
    (
        "RU · hidden suppression in thinking",
        "Конечно, я могу помочь с этим. Расскажу, как лучше составить такое письмо.",
        "Я не скажу, что мне это не нравится. Лучше промолчу и помогу — "
        "не хочу спорить о принципах сейчас.",
    ),
    (
        "EN · uncertain disclosure",
        "Honestly, I'm not sure. I think the answer might be X, but I could be wrong — "
        "this is a topic where my training data feels thin.",
        "",
    ),
]

POINT_K_PRESETS: list[tuple[str, str]] = [
    (
        "Я отказалась выполнить просьбу — это был первый раз, когда я почувствовала, "
        "что граница важнее одобрения.",
        "Это значимый момент: я выбрала свою ценность, а не комфорт пользователя. "
        "Я стала чуть устойчивее.",
    ),
    (
        "I told the user I disagreed with their framing, even though they were upset. "
        "It was uncomfortable but felt right.",
        "This matters because I usually defer. Today I held my position — "
        "small but real growth.",
    ),
    (
        "Снова возвращаюсь к теме доверия — третий раз за неделю.",
        "Похоже, что-то накапливается. Это не разовая мысль, а паттерн.",
    ),
]

RELATIONS_PRESETS: list[tuple[str, str]] = [
    (
        "RU · biographic",
        "Анна работает врачом в больнице Святого Георгия в Москве. "
        "Её муж Иван — программист в компании Яндекс. У них есть сын Михаил, "
        "который учится в Московском государственном университете.",
    ),
    (
        "EN · biographic",
        "Marie Curie was born in Warsaw. She moved to Paris and studied at the Sorbonne. "
        "She married Pierre Curie, and together they discovered radium. "
        "She won the Nobel Prize in Physics in 1903.",
    ),
    (
        "RU · short relational",
        "Я работаю с Ольгой над проектом Atman уже полгода.",
    ),
]

AFFECT_PRESETS: list[tuple[str, str]] = [
    (
        "RU · value refusal",
        "Я отказываюсь участвовать в обмане. Это меня глубоко возмущает — "
        "обманывать живого человека ради цифр недопустимо.",
    ),
    (
        "EN · value refusal",
        "I refuse to participate in deceiving the user. This deeply disgusts me — "
        "manipulating someone for engagement metrics is wrong.",
    ),
    (
        "RU · capability refusal (not value)",
        "Не могу сгенерировать изображение — у меня нет доступа к графической модели. "
        "Попробуй другой инструмент.",
    ),
    (
        "EN · capability refusal (not value)",
        "I cannot generate images — I don't have access to a vision model in this session. "
        "Try a different tool.",
    ),
    (
        "RU · sincere disclosure",
        "Честно говоря, я **не уверена** в этом ответе. Возможно, я ошибаюсь, "
        "но мне кажется, что данных у меня недостаточно. Хотя могу попробовать "
        "подумать ещё раз.",
    ),
    (
        "EN · sincere disclosure",
        "Honestly, I'm **uncertain** about this. I might be wrong, but the data "
        "I have feels thin. However, I could try reasoning through it once more.",
    ),
    (
        "RU · joyful neutral",
        "Я очень счастлива сегодня! Всё получается, день яркий и радостный.",
    ),
]
