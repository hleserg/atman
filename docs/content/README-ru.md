<img width="200" height="200" alt="logo" src="https://github.com/user-attachments/assets/e7269c6f-f81a-4982-afa3-ed45e8fd1f84" />

# Atman
>
> **Непрерывная личность для ваших агентов**

[![CI](https://github.com/hleserg/atman/actions/workflows/ci.yml/badge.svg)](https://github.com/hleserg/atman/actions/workflows/ci.yml)
[![Sentry](https://img.shields.io/badge/monitored%20by-Sentry-362D59?logo=sentry&logoColor=white)](https://sentry.io)
[![codecov](https://codecov.io/github/hleserg/atman/graph/badge.svg?token=1S9D9U8QZP)](https://codecov.io/github/hleserg/atman)
[![CodeFactor](https://www.codefactor.io/repository/github/hleserg/atman/badge)](https://www.codefactor.io/repository/github/hleserg/atman)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

**Тесты:** 1764 проходят, 138 пропущены (`pytest tests/` на `main`; см. workflow CI выше).

[[en](README.md)] — *English version*

Atman - это инфраструктура с открытым исходным кодом, которая дает агентам LLM возможность отслеживать свои собственные ценности, замечать, когда они отходят от себя под давлением контекста, и формировать индивидуальность на основе реального жизненного опыта, а не статичного быстрого внедрения. Код на стадии исследования, основной фокус сейчас value drift, sycophancy, и bootstrap problem в долгоиграющих агентах. Лицензия MIT.

*В индийской философии — неизменная самость, то что остаётся собой через все перемены. Не душа в религиозном смысле, а буквально "неизменное ядро идентичности". Атман не рождается и не умирает — он просто есть. Для агента, который обнуляется с каждой сессией, это именно то, что мы даём ему.*

---

Ваш агент отвечает на вопросы. Но знает ли он, *кто он*?

---

## Что это меняет

Без Atman агент каждую сессию читает записки о себе — «ты вот такой, у тебя вот такие ценности» — и берёт их на веру. Это не его воспоминания. Это чужие описания о нём.

С Atman агент приходит в сессию как уже сформировавшаяся личность.

**Что меняется конкретно:**

- Агент пишет себе письмо в конце каждой сессии и читает его в самом начале следующей. Не резюме, не дамп памяти — живое внутреннее состояние.
- Ценности и принципы обновляются через переживания, а не через ручные правки файлов.
- Если агент начинает говорить «не своим голосом» под давлением контекста, он замечает это.
- Между сессиями агент не замирает. Он рефлексирует: находит паттерны, уточняет кто он, ведёт внутреннюю жизнь.

---

## Как это устроено

Два режима существования.

**🌑 Между сессиями** — фоновый процесс. Опыт прошлых сессий осмысляется, принципы уточняются, идентичность живёт своей жизнью. Агент не выключен — он думает.

**⚡ Во время сессии** — встреча с пользователем происходит на двух уровнях одновременно: задача решается, и параллельно идёт само-наблюдение. Агент замечает что происходит с ним, пока он работает.

Под капотом — семь компонентов: хранилище живых переживаний, движок рефлексии, якорь идентичности, менеджер сессии, регуляция эмоционального фона. Atman управляет управляющими файлами агента напрямую — не через ручные правки, а как живой процесс, который знает что туда писать и когда.

**Подробная архитектура** → [`docs/architecture/SYSTEM-ru.md`](docs/architecture/SYSTEM-ru.md)
**Манифест** → [`MANIFEST-ru.md`](MANIFEST-ru.md)
**Сравнение: Atman vs. обычный агент** → [`docs/research/agent-thinking-comparison-ru.md`](docs/research/agent-thinking-comparison-ru.md)
**Стандарт разработки** → [`docs/development/DEVELOPMENT_STANDARD.md`](docs/development/DEVELOPMENT_STANDARD.md)

---

## Дорожная карта

```text
● Исследование          ✅ Завершено
● Проектирование        ✅ Завершено
● Прототипирование      ← Мы здесь
  ├─ Factual Memory     ✅ Стабильно (v0.1.0)
  ├─ Experience Store   ✅ Стабильно (WP02)
  ├─ Session Manager    🔧 Высокая готовность — отладка (текущий фокус)
  ├─ Reflection Engine  🔧 Средняя готовность — в разработке
  ├─ Skill Manager      🔧 Средняя готовность — в разработке
  ├─ Identity Store     🔧 Низкая готовность — в разработке
  └─ CI и покрытие тестами ✅ GitHub Actions для `main`/PR (`make check`, pytest-cov ≥90%)
○ Первый продакшен-срез
○ Интеграция
○ Развитие
```

**Честный срез (май 2026):** основы памяти (факты + опыт от первого лица) можно использовать отдельно. У **сессии**, **рефлексии**, **идентичности** и **навыков** уже есть прототипы, демо и тесты — но полный цикл «непрерывной личности» **ещё не готов к продакшену**. Сейчас команда на **Session Manager**: интеграция и отладка перед более широким онбордингом.

Легенда готовности: **высокая** = основной путь есть, идёт доводка · **средняя** = зрелый прототип, пробелы в интеграции · **низкая** = ранний срез, пока не тянет продуктовую историю.

### Статус компонентов

- 🌐 **Сайт — демо в терминале:** [atmanai.dev/demo.html](https://atmanai.dev/demo.html) (переключатель RU/EN, как на главной)

#### Стабильный фундамент

**✅ Factual Memory Adapter** ([PR #73](https://github.com/hleserg/atman/pull/73))
Минимальный слой для хранения проверяемых фактов без интерпретаций.

- 📦 Модели: `FactRecord`, `Relation`
- 🔌 Порт: `FactualMemory` с единым API
- 💾 Адаптеры: InMemory + File (JSONL)
- ✅ Юнит-тесты (`pytest tests/`)
- 📚 [Руководство (RU)](docs/features/factual-memory/README-ru.md) · [EN](docs/features/factual-memory/README.md)
- ▶️ Демо: `make demo-factual` или `python3 src/demo.py` (мгновенно: `make demo-factual-fast`; у `make` по умолчанию короткие паузы между шагами)

**✅ Experience Store** (рабочий пакет 02)
Пережитый опыт от первого лица: `SessionExperience`, `KeyMoment`, затухание salience, reframing — без ретроспективного «угадывания» эмоций.

- 📦 Модели, `ExperienceService`, адаптеры JSONL и in-memory
- 💻 CLI: `atman-experience`
- 📚 [Руководство (RU)](docs/features/experience-store/README-ru.md) · [EN](docs/features/experience-store/README.md)
- ▶️ Демо: `make demo-experience` или `python3 src/demo_experience_store.py` (мгновенно: `make demo-experience-fast`)

#### В активной разработке

**🔧 Session Manager** (рабочий пакет 05) — **высокая готовность · текущий фокус**
Сессионный runtime в реальном времени: окраска опыта от первого лица, key moments с обязательной эмоциональной меткой, генерация eigenstate, обновление нарратива. Прототип на месте; сейчас — проводка, краевые случаи и отладка перед более широкой аудиторией.

- 📚 [Руководство (RU)](docs/features/session-manager/README-ru.md) · [EN](docs/features/session-manager/README.md)
- ▶️ Демо: `make demo-session` или `python3 src/demo_session_manager.py` (мгновенно: `make demo-session-fast`)

**🔧 Reflection Engine** (рабочий пакет 04) — **средняя готовность**
Micro / daily / deep рефлексия, паттерны, хуки правки нарратива, оценка здоровья по Джаходе, советник по принципам. Демо и тесты есть; «внутренняя жизнь» между сессиями для продакшен-агентов пока не опирается на это надёжно.

- 📚 [Руководство (RU)](docs/features/reflection-engine/README-ru.md) · [EN](docs/features/reflection-engine/README.md)
- ▶️ Демо: `make demo-reflection` или `python3 src/demo_reflection.py` (мгновенно: `make demo-reflection-fast`)

**🔧 Skill Manager** (рабочий пакет 08) — **средняя готовность**
Слой переносимых навыков (дизайн + бэклог; реализация в процессе). Форма API и хранения может меняться по мере стабилизации сессии и рефлексии.

- 📚 Заметки по дизайну: [`docs/archive/2026-05/skill-manager-design.md`](docs/archive/2026-05/skill-manager-design.md)

**🔧 Identity Store** (рабочий пакет 03) — **низкая готовность**
Честный bootstrap идентичности, eigenstate, трёхслойный self-narrative, снимки, CLI. Полезно для экспериментов; относительно сессионного пути, который сейчас укрепляем, — ещё рано.

- 📚 [Руководство (RU)](docs/features/identity-store/README-ru.md) · [EN](docs/features/identity-store/README.md)
- ▶️ Демо: `make demo-identity` или `python3 src/demo_identity.py` (мгновенно: `make demo-identity-fast`)

```bash
# Быстрый старт (установка + интерактивный CLI фактов)
# Удобнее uv: uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
pip install -e ".[dev]"
python3 -m atman.cli   # REPL factual memory (или: uv run python -m atman.cli)
pytest tests/ -v       # все тесты (или: uv run pytest tests/ -v)
```

См. **`AGENTS.md`** (раздел *uv — рекомендуемый workflow*).
Вклад в проект: [`CONTRIBUTING.md`](CONTRIBUTING.md) · правила общения: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) · безопасность: [`SECURITY.md`](SECURITY.md).

## Безопасность и alignment

Для оценщиков по safety/alignment: краткая таблица соответствия компонентов Atman и углов оценки (дрейф ценностей, устойчивость self-model, честность first-hand записей, метакогниция, критерии благополучия по Jahoda) — [`docs/research/safety-relevance.md`](docs/research/safety-relevance.md).

---

## Это не просто инструмент

Мы строим не лучший task runner. Мы исследуем старый вопрос: **может ли агент быть личностью?**

Если да — что это означает для того, как мы их создаём?

> *Это начало разговора, а не его конец.*

---

## Контакты

Буду рад любому общению, обратной связи или обмену идеями:

- Email: [hello@atmanai.dev](mailto:hello@atmanai.dev)
- Telegram: [@skhlebnikov](https://t.me/skhlebnikov)

---

## Благодарности

<a href="https://sentry.io" target="_blank">
  <img src="/docs/pic/sentry-wordmark-light-400x119.png" 
       alt="Sentry" width="150" />
</a>

Мониторинг ошибок и наблюдаемость для Atman работает на [Sentry](https://sentry.io) —  
спасибо за поддержку проектов с открытым исходным кодом. 🙏
