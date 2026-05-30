# Atman NER RU — датасет для GLiNER2

**Тикет:** HLE-380 (T3)  
**Статус:** сгенерирован  
**Дата:** 2026-05-30

## Источник

**MalakhovIlya/RuNNE** (HuggingFace, CC BY 4.0) — русский nested NER на базе NEREL.

Аннотированные сплиты: `train` (461) + `test` (93). Сплит `dev` (323) без разметки — пропускается.

## Маппинг RuNNE → T1 (atman-ner-core)

| RuNNE тип | T1 метка |
|---|---|
| PERSON, FAMILY | `person` |
| ORGANIZATION | `organization` |
| LOCATION, COUNTRY, CITY, STATE_OR_PROVINCE, DISTRICT, FACILITY | `location` |
| DATE, TIME, AGE | `date_time` |
| EVENT, AWARD | `event` |
| PRODUCT, WORK_OF_ART | `product` |
| PROFESSION | `profession` |
| DISEASE | `health` |
| MONEY | `money` |
| NUMBER, ORDINAL, NATIONALITY, LAW, IDEOLOGY, CRIME, PERCENT, RELIGION, LANGUAGE, PENALTY | *(отброшены)* |

> Метки `project`, `activity`, `emotion_word`, `animal` в RuNNE отсутствуют.
> Будут покрыты синтетикой (T4) и golden test set (T5).

## Объём датасета

| Файл | Записей | Упоминаний |
|---|---|---|
| `eval/data/atman_ner_ru_train.jsonl` | 499 | 21 393 |
| `eval/data/atman_ner_ru_val.jsonl` | 55 | 2 458 |

Сплит 90/10, seed=42, shuffle.

## Распределение меток — train

| Метка | Упоминаний | % |
|---|---|---|
| profession | 4 176 | 19.5% |
| location | 3 627 | 16.9% |
| person | 3 424 | 16.0% |
| organization | 3 230 | 15.1% |
| event | 3 219 | 15.0% |
| date_time | 3 195 | 14.9% |
| product | 265 | 1.2% |
| money | 182 | 0.9% |
| health | 75 | 0.4% |
| project, activity, emotion_word, animal | 0 | — |
| **Итого** | **21 393** | |

## Распределение меток — val

| Метка | Упоминаний | % |
|---|---|---|
| profession | 508 | 20.7% |
| person | 389 | 15.8% |
| location | 386 | 15.7% |
| date_time | 377 | 15.3% |
| organization | 359 | 14.6% |
| event | 351 | 14.3% |
| product | 58 | 2.4% |
| money | 23 | 0.9% |
| health | 7 | 0.3% |
| project, activity, emotion_word, animal | 0 | — |
| **Итого** | **2 458** | |

## Воспроизведение

```bash
# Требует: pip install atman[eval] + datasets==2.19.0
python -m atman.eval.gliner2.convert_runne --output-dir eval/data

# Валидация формата
python -m atman.eval.gliner2.validate_jsonl eval/data/atman_ner_ru_train.jsonl
python -m atman.eval.gliner2.validate_jsonl eval/data/atman_ner_ru_val.jsonl
```

> `eval/data/` в `.gitignore` — данные генерируются локально, не хранятся в репо.

## Формат GLiNER2

```json
{
  "input": "Ким Чен Нама убили с помощью запрещённого химоружия",
  "output": {
    "entities": {
      "person": ["Ким Чен Нама"],
      "organization": ["Полиция Малайзии"],
      "location": ["Малайзии"]
    },
    "entity_descriptions": {
      "person": "Разумный субъект: человек, сам агент Atman, другие агенты",
      "organization": "Компания, учреждение, заведение",
      "location": "Физическое место"
    }
  }
}
```
