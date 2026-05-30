"""T1 NER label schema for the atman-ner-core GLiNER2 adapter.

Source of truth: docs/eval/gliner2_label_schema.md (HLE-378 final).
"""

# Closed label set — 13 labels, lower_snake_case.
NER_LABELS: dict[str, str] = {
    "person": "Разумный субъект: человек, сам агент Atman, другие агенты",
    "organization": "Компания, учреждение, заведение",
    "location": "Физическое место",
    "date_time": "Время: дата, период, момент",
    "event": "Событие в жизни",
    "project": "Проект, начинание",
    "product": "Вещь, продукт, инструмент",
    "activity": "Занятие, хобби, действие",
    "profession": "Профессия, роль",
    "health": "Здоровье: состояние, симптом, лекарство",
    "emotion_word": "Прямо названная эмоция",
    "money": "Деньги, суммы",
    "animal": "Питомцы, животные",
}

# RuNNE (MalakhovIlya/RuNNE) entity type → T1 label.
# None = discard (no T1 counterpart).
# Types verified against the full dataset (see eval/data/README.md for counts).
NEREL_TO_T1: dict[str, str | None] = {
    "PERSON": "person",
    "ORGANIZATION": "organization",
    "LOCATION": "location",
    "COUNTRY": "location",       # country is a physical place
    "CITY": "location",
    "STATE_OR_PROVINCE": "location",
    "DISTRICT": "location",
    "FACILITY": "location",
    "DATE": "date_time",
    "TIME": "date_time",
    "AGE": "date_time",
    "EVENT": "event",
    "AWARD": "event",
    "PRODUCT": "product",
    "WORK_OF_ART": "product",
    "PROFESSION": "profession",
    "DISEASE": "health",
    "MONEY": "money",
    "FAMILY": "person",          # family member role → still a person
    # Discarded — no T1 counterpart
    "NUMBER": None,
    "ORDINAL": None,
    "NATIONALITY": None,
    "LAW": None,
    "IDEOLOGY": None,
    "CRIME": None,
    "PERCENT": None,
    "RELIGION": None,
    "LANGUAGE": None,
    "PENALTY": None,
    # Legacy BIO abbreviations kept for forward-compatibility
    "PER": "person",
    "ORG": "organization",
    "LOC": "location",
    "GPE": "location",
    "CARDINAL": None,
    "NORP": None,
}
