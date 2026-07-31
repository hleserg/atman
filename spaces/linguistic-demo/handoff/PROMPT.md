# PROMPT — что вставить в Claude Code первым сообщением

Скопируй и вставь блок ниже в Claude Code как первое сообщение проекта. Прикрепи к нему файлы из этого `handoff/` и сам `Atman Demo Visual Upgrade.html` из корня репо.

---

```
Привет. Прикладываю визуальный апгрейд для нашего демо.

ПРОЧИТАЙ ФАЙЛЫ В ТАКОМ ПОРЯДКЕ:

1. handoff/SPEC.md            — короткий бриф: архитектура страницы,
                                 что копировать 1:1, контракт API, темизация
2. Atman Demo Visual Upgrade.html  — это эталонный hi-fi мок целиком.
                                 Внутри секции <style> лежит вся типографика,
                                 палитра и layout. Секция .patches содержит
                                 готовые Python-патчи (Gradio) — посмотри как
                                 справочный материал, даже если применять их
                                 ты не будешь.
3. handoff/tokens.css         — те же CSS-переменные, выдранные отдельно.
                                 Положи в static/css/tokens.css.
4. handoff/screenshots/       — 12 PNG'ов (6 dark + 6 light).
                                 Это то, что должно получиться визуально.

СТЕК НАШЕГО ПРОЕКТА:
- Статический HTML + Python-backend, отдающий данные по API
- Frontend: ванильный HTML/CSS/JS (без React/Vue)
- Шаблонизатор: <ВПИШИ — Jinja / FastAPI templates / просто .html>

ЗАДАЧА:

A. Перенеси визуал из мока в наш проект как набор HTML-шаблонов и
   статических ассетов. Конкретно:

   1. Подключи Inter + JetBrains Mono с Google Fonts ровно теми же
      preconnect+link, что в моке.
   2. Скопируй tokens.css в static/css/tokens.css и подключи в base-шаблоне.
   3. Скопируй ВСЁ содержимое <style> из мока в static/css/atman.css
      (КРОМЕ блоков, обслуживающих docs-обёртку: .doc, .doc-header,
      .changelog, .patches, .pill-tag, .section-eyebrow, .section-title,
      .browser-bar, .mock — это leftovers вокруг мока, в проде не нужны).
   4. Свёрстай страницу из секций в порядке:
        hero  →  warmup row  →  tabs bar  →  active tab content  →  footer
      Внутри tab content: about-accordion (с pair-diagram) → 2-колоночная
      сетка (.row): слева inputs (.col), справа outputs + report-group.
   5. Точно повтори tabs (Point A, Point K, Relations, Affect). Контент
      каждой вкладки имеет ТУ ЖЕ структуру что Point A в моке, но свои
      labels / pair-diagram / report-секции. Используй мок как форму;
      где конкретного текста для других вкладок нет — оставь TODO-плейсхолдер
      и сразу подсвети это в конце ответа.
   6. Скопируй <script> переключения темы из самого низа мока as-is.
      Поведение: на первой загрузке читаем localStorage, иначе системную
      prefers-color-scheme (fallback на dark). Toggle сохраняет выбор и
      перестаёт следить за системой.

B. Подключи к backend'у:
   - При нажатии "▶️ Analyze" слать на сервер { tab, message, thinking,
     preset_id?, lang }, ждать JSON ровно той формы, что описана в SPEC §4.
   - Рендерить результат в три блока (highlight / json-output / report-group)
     БЕЗ перезагрузки страницы.
   - При смене языка (en/ru) свапать все локализуемые строки. Список
     узлов и обоих языков — см. UI_STRINGS из патча 03 в Atman Demo Visual
     Upgrade.html (можно скопировать ровно ту структуру в Python или
     перенести в .json и грузить статикой).
   - Pair-diagram для каждой вкладки описан в .apd-* в моке; одна функция
     pair_diagram(left_name, left_tag, left_sub, right_name, right_tag,
     right_sub) генерирует разметку — лежит в патче 02.

ЧТО ВАЖНО НЕ СЛОМАТЬ:
- Тема (light/dark) переключается через data-mode на <body>. Никаких
  data-theme или .dark классов — все стили в tokens.css завязаны на это
  именно так.
- JSON-output должен быть плоским <pre> с подсветкой классов .key / .str /
  .num / .punct. НИКАКОГО react-json-tree с разворачивающимися ветками.
- Detailed Analysis Report — это ОДНА карточка (.report-group) с тремя
  секциями (.report-section), а не три отдельных Markdown-блока.
- Эмодзи (🔥 ▶️ 🚧 🔍 📊 📑 🌐 ⚡ 🧠 📥 ℹ️ ✅ ⚠️) — это якоря, не декорация.
  Не выпиливай и не заменяй на иконки.

КОГДА ЗАКОНЧИШЬ:
- Покажи мне tree проекта (новые/изменённые файлы) и diff base-шаблона
- Скажи, какие куски остались как TODO (тексты вкладок K/Relations/Affect,
  preset-списки, URL-ы footer-а)
- Запусти dev-сервер и дай команду, чтобы я мог открыть и сравнить со
  скриншотами в handoff/screenshots/
```

---

## Бонус-промпты, если что-то пошло не так

**Если визуал «почти, но не совсем»:**

```
Открой handoff/screenshots/03-dark.png и сравни попиксельно с тем, что
рендерит наш dev-сервер на /demo. Найди 5 расхождений (отступы, шрифт,
цвет, состояние) и исправь.
```

**Если перепутана структура отчёта:**

```
В моке Detailed Analysis Report — это .report-group (одна карточка)
с тремя .report-section внутри, разделёнными пунктирным бордером сверху.
Загляни в Atman Demo Visual Upgrade.html, поищи селекторы .report-group
и .report-section, и приведи нашу разметку к ровно такой же.
```

**Если ломается light/dark:**

```
Проверь, что:
1. <body data-mode="dark"> ставится скриптом ДО первого пейнта
   (атрибут пишется в <head> или сразу в начале <body>, не в конце)
2. Все CSS-переменные определены в обоих :root и [data-mode="dark"]
3. Скрипт из конца Atman Demo Visual Upgrade.html скопирован без правок
4. localStorage key называется ровно "atman-demo-theme"
```
