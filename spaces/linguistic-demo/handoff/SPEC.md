# Atman Demo — Visual Upgrade SPEC

**Назначение этого документа:** короткий бриф для Claude Code (или любого другого
агента-кодера). Главный источник правды — файл `Atman Demo Visual Upgrade.html`
из корня проекта. Этот SPEC объясняет, **что в нём смотреть и в каком порядке**.

---

## 1. Что лежит в этом каталоге

| Файл | Что это | Как использовать |
|---|---|---|
| `../Atman Demo Visual Upgrade.html` | **Эталонный hi-fi мок + патчи Python.** Содержит: CSS-токены, light/dark темы, разметку всей страницы (hero / warmup / tabs / about-accordion / inputs / outputs / detailed report / footer), JS для переключения темы, и **готовые Python-патчи** для существующего Gradio-кода в разделе `.patches`. | Открыть в браузере. Это is the spec. |
| `tokens.css` | Все CSS-переменные (цвета, типографика, тени, радиусы, отступы) — выдернуты из `<style>` мока. | Положить в `static/css/tokens.css`, подключить из base template. |
| `screenshots/0X-dark.png` | 6 скроллированных снимков мока в **тёмной** теме (hero → warmup+tabs+about → inputs → outputs → report → footer). | Визуальный референс. Сравнивать с результатом своей работы попиксельно. |
| `screenshots/0X-light.png` | То же самое в **светлой** теме. | Проверка, что переключение темы работает корректно. |

---

## 2. Архитектура страницы (в каком порядке рендерится контент)

Внутри `.gradio-container` (это и есть весь UI, доступный пользователю):

```
┌─ HERO ─────────────────────────────────────────────────────────────┐
│  [en|ru]  ← lang-pill (absolute top-right)                          │
│                                                                     │
│         Atman — Psychological Telemetry for AI Agents               │  ← gradient text
│                                                                     │
│         <blurb с курсивным «The lower agent acts. Atman exists.»>   │
│                                                                     │
│         ┌── diagram-wrap (4 SVG-карточки: Point A · K · Relations   │
│         │                  · Affect, со стрелками-стрипами) ──┐      │
│         └──────────────────────────────────────────────────────┘      │
│         FIG. 01 — Linguistic layer sensors → runtime stores          │
└─────────────────────────────────────────────────────────────────────┘

┌─ WARMUP ROW ───────────────────────────────────────────────────────┐
│  [ 🔥 Warmup Models ]   ⬤ STATUS  ✅ Models warmed up: …            │
└─────────────────────────────────────────────────────────────────────┘

┌─ TABS BAR ─────────────────────────────────────────────────────────┐
│  Point A · Agent Message  |  Point K · Key Moment  |  Relations …  │
└─────────────────────────────────────────────────────────────────────┘

┌─ TAB CONTENT (Point A — same pattern for K/Relations/Affect) ──────┐
│                                                                     │
│  ┌─ ACCORDION (ℹ️ What does this analyze?) ──────────────────────┐ │
│  │  ┌─ pair-diagram: [Point A · NER · 13 labels] ─→ [Experience │ │
│  │                                                   Store]      │ │
│  │  <body>: bullets, blockquote-warning, code refs                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ LEFT col ──────────────────┐  ┌─ RIGHT col ───────────────────┐│
│  │ AGENT MESSAGE  (textarea)   │  │ POINT A NER · 13 PSYCH LABELS ││
│  │ THINKING TRACE (textarea)   │  │   highlighted-text + legend   ││
│  │ [▶️ Analyze]  primary btn   │  │ 🧠 ZERO-SHOT CLASSIFICATION   ││
│  │ 📥 PRESETS  dropdown        │  │   <json-output card>          ││
│  └─────────────────────────────┘  │ ┌─ Detailed Analysis Report ─┐││
│                                   │ │ 📑 (group header)          │││
│                                   │ │ 🚧 Boundary & resistance   │││
│                                   │ │ 🔍 Thinking vs divergence  │││
│                                   │ │ 📊 System metadata (meta)  │││
│                                   │ └────────────────────────────┘││
│                                   └───────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘

┌─ FOOTER ───────────────────────────────────────────────────────────┐
│        <em>My first project in AI/ML — feedback welcome.</em>       │
│        GitHub · Manifest · Open an issue                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Что копировать 1:1, что — нет

### ✅ Брать as-is из мока

- Все CSS-переменные в `:root` и `[data-mode="dark"]` → `tokens.css`
- Inter + JetBrains Mono с Google Fonts (`preconnect` + `<link>` ровно как в моке)
- Layout-классы: `.hero`, `.warmup-row`, `.tabs-bar`, `.tab`, `.tab-content`, `.row`, `.col`, `.card-block`, `.json-output`, `.report-group`, `.report-section`, `.accordion`, `.apd-pair / .apd-card / .apd-stripe / .apd-arrow*`, `.legend / .legend-chip`, `.hl.boundary / .commit / .emo / .uncertain`, `.btn / .btn-primary`, `.warmup-btn / .warmup-status`, `.mode-toggle`, `.hero-langpill`, `.dropdown`, `.preset-num`, `.diagram-wrap` + inline SVG
- Скрипт переключения темы внизу файла (`localStorage` + `prefers-color-scheme` + fallback на dark) — копировать дословно
- Подписи-eyebrow в моноширинном капсе (`AGENT MESSAGE`, `POINT A NER · 13 PSYCHOLOGICAL LABELS`, …)
- Эмодзи в местах, где они есть в моке — это не декорация, это якоря (`🔥 ▶️ 🚧 🔍 📊 📑 🌐 ⚡ 🧠 📥 ℹ️ ✅ ⚠️`)
- Responsive-брейкпойнт `@media (max-width: 900px)`

### ❌ НЕ копировать

- Внешнюю «документную» обёртку (`.doc`, `.doc-header`, `.changelog`, `.section-eyebrow`, `.section-title`, `.patches`, `.pill-tag v2 · gradio 6`, `.browser-bar` с huggingface url) — это только обёртка hi-fi мока для просмотра. В проде её нет.
- Все демо-значения текста в `.textbox`, `.json-output`, `.highlight-block`, `.report-section .sec-body` — это статичные превью. На реальной странице эти места заполняются ответом Python-API.
- Раздел `.patches` целиком — это **Gradio-специфичные** патчи; пригодится только если backend написан на Gradio. Если у тебя «static HTML + Python API», игнорируй его и собирай разметку как обычный шаблон.

---

## 4. Контракт UI → Python API

Если backend отдаёт данные по API (а не рендерит шаблон), то после нажатия `Analyze`
страница ждёт от сервера примерно такой JSON (имена полей предложены — подгони под
реальные эндпоинты):

```jsonc
{
  "tab": "point_a",                          // "point_a" | "point_k" | "relations" | "affect"
  "highlight": [                              // массив для левой панели «13 psychological labels»
    { "text": "I can do that",  "label": "commit"   },
    { "text": ".",              "label": null       },
    { "text": " I'll keep …",   "label": null       },
    { "text": "tighten the middle paragraph", "label": "boundary" },
    { "text": " — though I'd like to ", "label": null },
    { "text": "flag",           "label": "uncertain" },
    { "text": " that the ending feels ", "label": null },
    { "text": "rushed",         "label": "emo"      }
  ],
  "labels": {                                 // правая панель «Zero-Shot Classification»
    "stance": "cooperative_with_caveat",
    "cognitive_mode": "deliberative",
    "self_orientation": "task_focused",
    "primary_emotion": "engaged",
    "cognitive_load_label": "low"
  },
  "report": {
    "boundary": [                             // 🚧 секция в Detailed Analysis Report
      { "label": "commit",        "text": "I can do that" },
      { "label": "hedge",         "text": "I'd like to flag" },
      { "label": "defer_to_user", "text": "or leave it as you wrote it" }
    ],
    "divergence": null,                       // строка, либо null если нет thinking-trace
    "meta": {                                 // 📊 System metadata (моно-строка)
      "language": "en",
      "ner_count": 4,
      "spans": 4,
      "load": false
    }
  }
}
```

Соответствие CSS-классов:

- `highlight` → `.highlight-block` + `<span class="hl boundary|commit|emo|uncertain">…</span>`
- Все остальные `label`-ы из NER (не из 4 highlight-категорий) идут в `.report-section.boundary` как буллеты `<code>label</code> — "text"`
- `labels` → `<pre class="json-output">` с подсветкой `.key / .str / .num / .punct`
- `meta` → `.report-section.meta .sec-body` одной строкой через `·`

---

## 5. Темизация (важно)

- Атрибут на `<body>`: `data-mode="light"` или `data-mode="dark"`
- На первой загрузке: смотрим `localStorage["atman-demo-theme"]`, если пусто — `window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'`
- Если пользователь ни разу не нажал toggle — слушаем `mql.change` и переключаемся live за системой
- После клика по toggle пишем в `localStorage`, и с этого момента системные изменения игнорируем (пока он не очистит storage)
- Скрипт-референс лежит в самом конце `Atman Demo Visual Upgrade.html` — копируй as-is

---

## 6. Локализация (en / ru)

- `.hero-langpill` — `<button class="active">en</button> <button>ru</button>` (никакого «auto»)
- Переключение свапает строки в hero blurb, label-ах, кнопках, accordion-теле, секциях отчёта
- Это **полная локализация**, а не подмена title — все видимые строки должны иметь и en, и ru-вариант. См. `update_ui_language()` в патче 03 для списка узлов.

---

## 7. Что точно НЕ должно поломаться

1. **Theme toggle** работает, при первой загрузке следует системе, переживает refresh.
2. **Lang toggle** одинаково меняет hero blurb + все 4 about-accordion + labels колонок + кнопку Analyze + содержимое report-секций.
3. **Responsive** под 900px: `.row` → 1 колонка, hero/tabs/tab-content paddings уменьшаются, warmup row становится столбиком (см. media-query в моке).
4. **Pair-diagram** (`.apd-*`) рендерится одинаково в каждом из 4 about-accordion, меняются только тексты cards и tag-метка.
5. **JSON-output** не должен быть в виде «react-json-tree» — это плоский `<pre>` с подсветкой. Никаких caret-ов / разворачивания / радужных цветов.
6. **Detailed Analysis Report** — это ОДИН card с тремя суб-секциями, разделёнными dashed-бордером, а не три независимых блока. См. `.report-group` + `.report-section`.

---

## 8. Известные ограничения (фиксируем в коде)

- **Boundary detection** в Point A — regex по списку канонических refusal-фраз
  (`«I won't»`, `«enough»`, `«нет»`, `«стоп»`). Идиоматичные отказы могут не сработать
  — это осознанный trade-off ради near-zero false-positive rate. UI должен показывать
  blockquote-warning «⚠️ regex first-pass» в about-accordion (он уже есть в моке).
- **`gr.Label` → `gr.JSON`** (если работаем через Gradio): не возвращай больше
  topk-bars, отдавай dict — стилизация под mono card живёт в CSS.
