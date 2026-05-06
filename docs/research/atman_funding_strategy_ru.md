# Стратегия финансирования Atman: гранты, фелловшипы и платёжные рельсы для open-source AI-проекта из России (май 2026)

## TL;DR

- **По профилю Atman ближе всего попадает в линию "Black-box LLM psychology" из RFP Open Philanthropy / Coefficient Giving по технической AI-безопасности (февраль 2025) — но этот RFP закрылся 15 июля 2025, преемник на 2026 не объявлен. Реалистично открытые в 2026 году фонды для одиночного исследователя без аффилиации, гражданина РФ: NLnet/NGI Zero Commons Fund (€5–50k, без ограничений по гражданству, дедлайн 1 июня 2026), AI Risk Mitigation Fund / LTFF (медиана $25k, rolling), регранты Manifund ($5–50k, быстрые), AI Safety гранты Foresight Institute (rolling), Emergent Ventures (мелкие/быстрые, глобально) и трек для ранних карьерных исследователей Cooperative AI Foundation (потолок £100k) — если переформулировать Atman через мульти-агентную кооперацию. Также активен Schmidt Sciences Science of Trustworthy AI 2026 RFP.**

- **Платежи — главное узкое место, не право на заявку. Почти ни один западный фонд не публикует прямой "запрет для РФ", но Wise заблокировал карты граждан России без вида на жительство в ЕЭЗ 30 января 2026; Revolut — 31 декабря 2025; GitHub Sponsors и Patreon не выплачивают на российские банки; американские и британские фонды применяют OFAC/OFSI-скрининг даже когда формально не обязаны. Долгосрочное решение — нероссийское юрлицо или фискальный спонсор: зарегистрировать ИП в Армении на 1% налог с оборота для IT и открыть USD-счёт в Ameriabank/Halyk Армения; либо принимать средства через Manifund / NumFOCUS / Software Freedom Conservancy. USDC на чистый self-custody кошелёк — резервный путь только для крипто-нативных фондов.**

- **Последовательность: сначала NLnet, Manifund, Emergent Ventures, Foresight Institute и compute-кредиты Anthropic/Cohere/Lambda (мелкие, быстрые, географически нейтральные). Потом — LTFF/ARM Fund, SFF Speculation Grants, Cooperative AI Foundation. OpenPhil/Coefficient, основной раунд SFF и Schmidt Sciences оставить на следующий заход, когда в активе будут уже один-два гранта и фискальный спонсор. Публично переформулировать Atman как работу о "value drift, goal stability, model welfare evaluations и честных самоотчётах LLM-агентов" — именно эти формулировки открывают 6–8 названных фондов.**

## Ключевые находки

1. **Содержательный тезис финансируется хорошо.** Long-Term Future Fund распределил больше $20M с 2017 года, примерно половина — в AI safety; по данным LongtermWiki со ссылкой на отчёт о выплатах LTFF за 2023: "В 2023 LTFF выдал $6.67M с показателем принятия заявок 19.3%". Официальное объявление SFF о рекомендациях 2025 года: $34.33M рекомендаций по S-Process плюс $0.59M ранее выданных Speculation Grants — итого $34.92M ожидаемого распределения; анализ EA Forum оценивает примерно $29M (~86%) на AI-безопасность. Страница RFP Open Philanthropy по технической AI-безопасности от февраля 2025 (coefficientgiving.org) пишет: "Мы рассчитываем потратить около $40M на этот RFP в течение следующих 5 месяцев и располагаем возможностью потратить значительно больше в зависимости от качества заявок" — $40M это ожидаемый бюджет, не формально закреплённое распределение. Среди 21 названной области исследований есть трек **"Black-box LLM psychology"**, который почти идеально совпадает с Reflection Engine, Reality Anchor и компонентами честности/интроспекции в Atman. По "Overview of the AI Safety Funding Situation" с LessWrong (январь 2025): "Open Phil пожертвовал около $2.8 миллиарда, из которых около $336 миллионов потрачено на AI safety (~12%)".

2. **AI welfare стало настоящей категорией финансирования.** Из пресс-релиза Eleos AI Research от 24 апреля 2025: "Кайл Фиш, исследователь в Anthropic, возглавивший это направление, ранее был сооснователем Eleos и соавтором их ключевого отчёта 'Taking AI Welfare Seriously'". В TIME 100 Most Influential in AI 2025 указано, что Фиш пришёл в Anthropic в сентябре 2024 как первый исследователь AI welfare. У Anthropic Fellows Program есть явное направление "AI Welfare". В штате Eleos AI Research — Роб Лонг, Патрик Батлин (Oxford GPI) и Рози Кэмпбелл (бывшая OpenAI); у них ежегодная конференция ConCon (вторая итерация — осень 2026 в Беркли). **Однако ни Eleos, ни Anthropic Model Welfare, ни Schmidt Sciences не имеют публичного гранта, по которому неаффилированный одиночный исследователь подаёт заявку и получает деньги.** Реальный путь: Anthropic Fellows Program (без визовой поддержки, очно), сотрудничество с Eleos как внешний исследователь (без денег, только нетворкинг) или TAIS/AISI/SFF-каналы с релевантным AI-welfare-фреймингом.

3. **Российский статус — это в основном банковское ограничение, а не ограничение права на заявку.** Cooperative AI Foundation прямо пишет, что заявители "могут находиться в любой точке мира", но добавляет: "для стран с низким Corruption Perceptions Index обработка может занять больше времени из-за расширенной процедуры due diligence" — Россия в CPI стоит низко, поэтому проект попадёт под усиленную проверку, но категорически не исключается. NLnet NGI Zero Commons Fund не указывает ограничений по гражданству. LTFF, SFF и Manifund проводят платежи через американские 501(c)(3) посредники и потребуют фискального спонсора или нероссийский счёт.

4. **19-й санкционный пакет ЕС (октябрь 2025) сделал прямые платежи в РФ существенно хуже.** Пакет "явно запрещает оказание платёжных услуг, прямо или косвенно, гражданам России и Беларуси или лицам, проживающим в России, а также юридическим лицам, организациям или органам, учреждённым в России". Wise и Revolut начали блокировать карты граждан РФ без вида на жительство в ЕЭЗ с дедлайнами 30 января 2026 (Wise) и 31 декабря 2025 (Revolut). Казахстанская карта Halyk или Kaspi сама по себе достаточна, чтобы *получить* SWIFT-перевод (основной SWIFT Halyk: HSBKKZKXXXX), но для входящих USD выше скромных лимитов нужен верифицированный казахстанский адрес у банка.

5. **Реальные, открытые сейчас, географически терпимые возможности есть.** На май 2026: ближайший дедлайн NLnet NGI Zero Commons Fund — 1 июня 2026, 12:00 CEST; на странице самого NLnet подтверждено: "Всего NGI Zero Commons Fund распределит 21.6 миллиона евро на R&D в области технологического общего достояния" в период с 1 января 2024 по 30 июня 2027 по соглашению о гранте Horizon Europe № 101135429. Foresight Institute AI for Science & Safety Nodes принимает rolling-заявки помесячно. Регранты Manifund — постоянно. Emergent Ventures — rolling, открыто глобально для всех от 13 лет. External Researcher Access Program от Anthropic и AI for Science Program дают бесплатные кредиты Claude API. Cohere Labs Catalyst Grants дают доступ к Cohere API. Lambda Labs Research grants — до $5,000 в облачных кредитах. Дедлайн исследовательского гранта Cooperative AI Foundation 2026 уточняется; их трек для ранних карьерных исследователей (потолок £100k, 12 месяцев, один человек, без обязательной PhD) — хорошее попадание, если переформулировать Atman через ракурс кооперации/координации. Schmidt Sciences Science of Trustworthy AI 2026 RFP открыт.

## Подробности

### A. Фонды AI Safety / Alignment / AI Welfare

**Long-Term Future Fund (LTFF) — funds.effectivealtruism.org/funds/far-future**
EA Funds (Effective Ventures). Медианный грант ~$25k; типичные индивидуальные исследовательские гранты $20–80k на 3–12 месяцев; seed-финансирование организаций $50–200k. В Q1 2025 был дедлайн 15 февраля 2025; в остальном — rolling. Целевой срок решения 21 день. **Институциональная аффилиация, публикации и рекомендательные письма не требуются**, хотя помогают. Выплаты идут через фискальных спонсоров; "команда LTFF может помочь найти такого". Гражданин РФ — solo-разработчик с чётким описанием — это ровно профиль LTFF. Подавать заранее, решение через 1–3 месяца.

**AI Risk Mitigation Fund (ARM Fund) — airiskfund.com/grants**
Выделен из LTFF в декабре 2023; оператор — Effective Ventures Foundation. За пять лет распределено больше $20M; индивидуальные гранты в недавних раундах примерно от $12,000 до $232,000; обозначенный командой типичный диапазон $55,000–$232,000. Три области: техническое AI alignment, AI policy/governance, capacity building. Rolling-заявки.

**Survival and Flourishing Fund (SFF) — survivalandflourishing.fund**
Основан Яаном Таллином. Раунд SFF 2026 оценивается в $20–40M суммарно через Main Round (Main, Freedom, Fairness треки) и три тематических раунда (Climate, Animal Welfare, Human Self-Enhancement and Empowerment); дедлайн Main Round был 22 апреля 2026. Индивидуальные гранты обычно $10k–$4M; медиана ~$100k. **SFF, как правило, не выдаёт гранты физическим лицам — они выдаются зарегистрированным коммерческим или некоммерческим организациям по всему миру, кроме враждебных государств.** Связанная структура Survival and Flourishing Projects (SFP) проектируется именно для финансирования физлиц в случаях, где SFF не может, но пока находится на этапе создания. **SFF Speculation Grants** — быстрый трек: типичный бюджет каждого Speculator $400k, решение возможно за неделю. По данным SFF: "более 95% заявок, оцененных в прошлых раундах, получили Speculation Grant". Подаётся через SFF Funding Rolling Application — но скорее всего понадобится корпоративная оболочка.

**Manifund — manifund.org**
Американская 501(c)(3) платформа регрантов. Программа регрантов 2025 собрала $2.25M в начальной группе из 10 регрантеров с бюджетами $100k+ у каждого. Регранты обычно $5k–$50k; путь от "грант рекомендован" до "деньги на счету грантополучателя" занимает меньше недели. Manifund действует как фискальный спонсор (501(c)(3)-совместимо): "Мы поддерживаем регранты зарегистрированным благотворительным организациям и физическим лицам. Коммерческие организации тоже могут быть приемлемы — после due diligence". Для Atman: открыть страницу проекта на Manifund, потом обращаться к отдельным регрантерам напрямую (например, Marius Hobbhahn в Apollo, Lisa Thiergart в MIRI) с чётким питчем — самый быстрый путь к первому капиталу.

**Open Philanthropy / Coefficient Giving — openphilanthropy.org & coefficientgiving.org**
RFP по технической AI-безопасности от февраля 2025 закрылся 15 июля 2025; преемник на 2026 на май 2026 не объявлен. Кластер, релевантный Atman — "Exploring sophisticated misbehavior of LLMs" — содержит явную область **"Black-box LLM psychology"**. Другие подходящие области: "alignment faking experiments", "encoded reasoning in CoT and inter-model communication" и externalized reasoning внутри "model transparency". До открытия преемника в 2026 — путь через email **technicalaisafety@coefficientgiving.org** с проактивным запросом. Сопутствующий AI Governance RFP закрылся 25 января 2026.

**Schmidt Sciences — Science of Trustworthy AI 2026 RFP — schmidtsciences.org/trustworthy-ai/**
Активен в 2026; международные заявки приветствуются; уровни сумм до нескольких миллионов USD; предпочтение институциональным коллаборациям, но не исключительно. Покрывает characterisation of misalignment, oversight, evaluation, multi-agent risks. Стоит подавать с надёжным академическим коллаборатором.

**Future of Life Institute (FLI) — futureoflife.org/our-work/grantmaking-work/**
Vitalik Buterin AI Existential Safety PhD Fellowships; тематические RFP (последний: 16 наград, объявленных за AI для решения конкретных проблем). По проектам — следить за активными конкурсами.

**Cooperative AI Foundation (CAIF) — cooperativeai.com/grants/2025**
Британская благотворительная организация (#1201294), $15M обязательств от Macroscopic Ventures. Два трека: стандартный (минимум £10k, без фиксированного потолка, прошлые гранты £10k–£385k, медиана ~£150k, до 2 лет, потолок косвенных расходов 10%) и **трек для ранних карьерных исследователей**: "бюджет максимум £100,000, длительность до 12 месяцев, проект преимущественно ведётся одним человеком". По аффилиации: "Формальное исследовательское обучение и степени (например, докторская) обычно усиливают заявку, но строго не требуются. Аффилиация во многих случаях усиливает заявку, но не обязательна. Заявки от неаффилированных лиц могут обрабатываться дольше". По России: "Можно находиться в любой точке мира. Для стран с низким Corruption Perceptions Index обработка может занять больше времени из-за расширенной процедуры due diligence". Дедлайн 2025 был 16 ноября 2025; дедлайн 2026 уточняется. **Критическое предупреждение по scope: CAIF пишет: "Мы, как правило, не рассматриваем работу по выравниванию одного искусственного агента с одним принципалом (человеком), даже если эта проблема технически состоит из двух агентов".** Atman в текущей формулировке — single-agent psychology и не пройдёт. Чтобы попасть, переформулировать Atman вокруг (а) кооперации между несколькими Atman-оснащёнными агентами под нормативным давлением, или (б) кооперации человек-AI, где стабильная идентичность защищает от манипуляций/sycophancy.

**AI Safety Tactical Opportunities Fund (AISTOF)** — Управляется JueYan Zhang. **Публичной формы заявки нет, всё по рекомендациям.** Co-финансировал Cooperative AI Research Fellowship в Кейптауне и программы PIBBSS. Coefficient Giving явно одобряет AISTOF. Путь — через текущих грантополучателей или холодное письмо JueYan через LinkedIn / EA Forum после получения первого результата на Manifund или LTFF.

**UK AISI Alignment Project — alignmentproject.aisi.gov.uk**
Финансируется международной коалицией (UK AISI, Canadian AISI, Schmidt Sciences, AWS, Anthropic, Halcyon Futures, Safe AI Fund, ARIA, OpenAI, Microsoft, Australian AISI, AISTOF, Sympatico Ventures, Renaissance Philanthropy). Первый раунд в 2025 получил 800+ заявок от 466 институтов из 42 стран; награждено 60 проектов; общий объём финансирования сейчас £27M, включая £5.6M от OpenAI. До £1M на проект (Alignment Fund) и до £200k на проект (Challenge Fund). Со страницы AISI: "Заявки в Alignment Project сейчас закрыты. Ожидается возобновление летом 2026".

**Eleos AI Research — eleosai.org**
Внешней грантовой программы не ведут. Нанимают сотрудников; проводят ConCon (21–23 ноября 2025 — первый, "осень 2026, дата уточняется" — следующий). Experience Store и фрейминг "felt emotional coloring vs retrospective labeling" в Atman попадают в опубликованные исследовательские приоритеты Eleos (concrete welfare interventions, human-AI cooperation frameworks, leveraging AI for welfare research, standardized welfare evaluations, credible communication). **С Eleos работать как с площадкой партнёрства/видимости, а не как с источником финансирования.** Реальный следующий шаг — постер или доклад на ConCon 2026, либо соавторство с кем-то оттуда.

**Anthropic Model Welfare program** — Внутренняя; внешнего RFP нет. Возглавляет Кайл Фиш. Единственная внешняя дверь — **Anthropic Fellows Program** (alignment.anthropic.com/2025/anthropic-fellows-program-2026/): 4-месячная full-time эмпирическая исследовательская программа; **стипендия $3,850/неделю + ~$15,000/месяц compute-бюджет**. Из объявления Anthropic Fellows 2026: "Более 40% участников первой когорты впоследствии присоединились к Anthropic для работы full-time над AI safety". Workstreams явно включают "AI Welfare". Следующая когорта стартует в июле 2026. **Anthropic не даёт визовое сопровождение участникам**, и программа очная в хабах Беркли/Лондон/Торонто — это блокирующий барьер для резидента РФ без существующей визы.

**Anthropic External Researcher Access Program — support.claude.com/en/articles/9125743**
Бесплатные кредиты Claude API для исследователей по safety/alignment. Отдельная форма заявки. Стоит подавать только ради compute, даже если денежного гранта не будет.

**Anthropic AI for Science Program — anthropic.com/news/ai-for-science-program**
До $20,000 в API-кредитах за 6 месяцев для исследователей с институциональной аффилиацией; биология/life sciences. Менее подходит, но стоит знать.

**OpenAI Superalignment Fast Grants** — закрыт 18 февраля 2024; OpenAI расформировал команду Superalignment. Упомянуть только как точку отсчёта.

**OpenAI AI & Mental Health Research Grants — openai.com/index/ai-mental-health-research-grants/** — Всего $2M; заявки закрыты 19 декабря 2025; решения к 15 января 2026. Atman попадает тематически (критерии Jahoda для mental health, применённые к AI-агентам) — следить за преемником в 2026.

**OpenAI People-First AI Fund** — Только для американских 501(c)(3); не подходит.

**AI Safety Fund (AISF) — Frontier Model Forum** — Гранты до $500,000; приоритеты 2025 включали биобезопасность, кибербезопасность и AI Agent Evaluation & Synthetic Content. Линия "AI agent identity verification systems and AI agent safety evaluations" структурно релевантна.

**Foresight Institute AI for Science & Safety Nodes — foresight.org/grants/grants-ai-for-science-safety/**
~$3M в год; гранты $10k–$100k; rolling-дедлайны помесячно (последний день каждого месяца); ~2 месяца на рассмотрение. Сильно предпочитают заявителей, планирующих использовать SF или Berlin Nodes (открыты с 1 апреля 2026); funding-only заявки рассматриваются "только в исключительных случаях". Области: Secure AI, Private AI, Decentralized cooperation, Epistemics, Neurotechnology, Longevity Biotech, Molecular Nanotech. Atman попадает через мульти-агентность и кооперацию/безопасность через funding-only заявку с переформулировкой как cooperation/epistemic infrastructure.

**PIBBSS Fellowship — princint.ai/programs/fellowship/**
Финансируется SFF, LTFF, AISTOF, Cooperative AI Foundation. 3-месячная программа; принимают заявки из всех стран; ориентирована на PhD/постдоков, но открыта для сопоставимого исследовательского опыта. Есть отдельный Cooperative AI Track. Очно в Лондоне/Bay Area летом; иногда есть визовая поддержка. Заявки обычно закрываются в конце января для летней когорты.

### B. Гранты open-source

**NLnet NGI Zero Commons Fund — nlnet.nl/commonsfund**
Самый реалистичный open-source-фонд для Atman. €5,000–€50,000 (с возможностью масштабировать выше); rolling-конкурсы каждые два месяца, текущий дедлайн **1 июня 2026, 12:00 CEST**. Без фиксированных ограничений по гражданству; проект должен соответствовать видению "Next Generation Internet" (open hardware/software/data/standards, libre/open licenses). NLnet поддержал больше 1,000 FOSS-проектов через коалицию своих фондов. Заявка — структурированная форма с техническими и бюджетными вопросами; сначала eligibility-проверка, потом scoring; cost-recovery основа. Atman попадает как инфраструктура autonomy-preserving и transparency-promoting для слоя human-AI взаимодействия в next-generation интернете.

**Sovereign Tech Agency / Sovereign Tech Fellowship — sovereign.tech/programs/fellowship**
Дедлайн фелловшипа 2026 закрылся 6 апреля 2026. Компенсация €4,800–€5,200/месяц. Целевая аудитория — *поддержание* критической существующей инфраструктуры, а не новые исследования — Atman не подходит. Sovereign Tech Standards (дедлайн 19 мая 2026) поддерживает мейнтейнеров IETF/W3C/ISO — тоже не подходит.

**Mozilla Foundation Incubator + AI & Democracy Awards — mozillafoundation.org**
Всего $1M на 10 проектов; $50,000 базовый + $250,000 для двух финалистов; заявки открылись в начале 2026. Фокус: "AI инструменты, защищающие и усиливающие демократию". Atman теоретически можно подать как value-stable агенты как democracy-preserving технология — пограничное попадание.

**Mozilla Open Source Support (MOSS)** — на бессрочной паузе. Сейчас не вариант.

**Plurality Institute — plurality.institute** — микрогранты, привязанные к воркшопам. Не прямой денежный грант на масштаб Atman.

**GitHub Accelerator** — статус приостановлен/неопределён.

**Open Source Collective (opencollective.com/opensource)** — 501(c)(6) фискальный хост; 10% комиссия; подключит проект для любого FOSS-проекта. Полезен как канал фискального спонсорства.

### C. Общие AI-research гранты и compute

**Cohere Labs — cohere.com/research**
- **Catalyst Grants**: бесплатный доступ к Cohere API для академических, гражданских, impact-ориентированных организаций.
- **Scholars Program**: 8-месячная full-time удалённая исследовательская стажировка (когорта 12 января — 29 августа 2026); оплачивается; через менторство; заявки обычно открываются в августе. Без требований к background, без обязательной PhD или публикаций. **Географически терпима; remote-first.** Сильный кандидат для исследовательского режима Atman.

**Lambda Labs Research Grant — lambda.ai/research**
До $5,000 в облачных кредитах для академических исследователей AI/ML, с менторством CSO Lambda. Из требований Lambda: "Affiliation with a research institution or university". Solo без аффилиации — проблема, если только не подаваться вместе с университетской лабой.

**Modal / RunPod / Vast.ai / Together.ai compute credits** — Различные стартап-кредиты; небольшие ($500–$5,000); обычно нужна заявка на стартап, но не инкорпорация. Использовать для разовых compute-задач. Ни один не требует американской регистрации.

**Hugging Face research/community access** — Community grants и кредиты Pro account нерегулярны; следить за huggingface.co/blog.

**AI2 Incubator** — Инкубатор в Сиэтле, коммерческий; нужна инкорпорация; не исследовательский грант.

**Google for Startups Cloud / AWS Activate / Azure for Startups** — Все требуют регистрации компании. AWS Activate даёт до $100k кредитов для VC-backed Activate Portfolio; $5k иначе. У Google Cloud до $200k для AI-стартапов. Ни один не требует американской регистрации, но все требуют регистрации в стране без санкций — здесь и пригождается армянский/грузинский/ОАЭ-ИП.

### D. Independent researcher / микрогранты

**Emergent Ventures (Tyler Cowen / Mercatus Center) — mercatus.org/emergent-ventures**
$1,000–$50,000; rolling-заявки; **глобально для всех от 13 лет**; "довольно быстрая и простая" заявка; гарантированный ответ за 2–3 недели по сторонним отчётам; решения принимает лично Тайлер Коуэн. Россия не исключена. Исторически финансировал нестандартные проекты. **Высокий EV для первой заявки.**

**Astera Institute Residency Program — astera.org/residency/**
Зарплата $125,000–$250,000 плюс бюджет проекта $0–$1.5M плюс доступ к 24,000 NVIDIA H100; 12–18 месяцев очно в Эмеривилле, Калифорния. **Требует физического присутствия**; H1B cap-exempt визовая поддержка возможна. Гражданин РФ без визы США в основном исключён, если не готов переехать.

**Pioneer.app** — Сменил формат несколько раз; проверить актуальный статус.

**Astral Codex Ten Grants (Scott Alexander)** — ACX Grants работает через Manifund на основе impact-market; небольшие гранты до $50k; заявки открываются осенью.

**Renaissance Philanthropy — renaissancephilanthropy.org** — ведёт целевые программы; не прямой грантодатель для физлиц по заявкам.

### E. Крипто / web3 гранты

Крипто-рельсы парадоксально *хуже* для России сегодня, чем в 2022. 20-й санкционный пакет ЕС (апрель 2026) явно запрещает операции с российскими рублёвыми стейблкоинами (RUBx, A7A5) и цифровым рублём; OFAC санкционировал Garantex и экосистему A7A5 в августе 2025. **Большинство платформ open-source в США отключили крипто-донаты на адреса, связанные с санкционными странами** — Open Source Collective: "С мая 2023 автоматические крипто-донаты отключены из-за compliance-проблем, связанных с приёмом средств из санкционной страны".

USDC/ETH от западных фондов на чистый кошелёк, не взаимодействующий с российскими VASP, остаётся юридически возможным, если получатель не в SDN-списке и не транзачит через санкционные биржи. Фонды, выплачивающие в стейблкоине:

- **Optimism Retro Funding (RPGF)** — ретроактивное финансирование public-goods; платит в OP. Прошлые раунды $2M–$30M суммарно за раунд.
- **Gitcoin Grants** — quadratic funding-раунды; OSS / dev-tooling / interop треки; GG24 распределил $300,000 по 64 проектам в 2025.
- **Protocol Labs / Filecoin Foundation Open Grants** — для проектов на или рядом с IPFS/Filecoin; не прямо релевантно Atman.
- **Polygon Community Grants** — Season 2 (35M POL) добавил AI-трек; нужно строить на Polygon.
- **Octant** — Quadratic funding от Golem Foundation; epoch-based; небольшие.

**Реалистичный крипто-путь для Atman**: разместиться на Gitcoin и Octant, принимать ETH/USDC на self-custody кошелёк (Rabby/Metamask с seed-фразой, без биржи), потом off-ramp через легитимный нероссийский канал (армянский или ОАЭ OTC). Хрупкий: любой KYC-этап, замечающий российскую резиденцию, может отказать в off-ramp.

### F. Географически нейтральные на практике

NLnet/NGI Zero, Emergent Ventures, Manifund (через фискальный спонсор), LTFF / ARM Fund (через фискальный спонсор), Cooperative AI Foundation (с дополнительным DD), Anthropic External Researcher Access (без денег), Cohere Catalyst Grants и Scholars, Astera Residency (требует переезда в США).

### G. Compute-ресурсы

Anthropic External Researcher Access Program (Claude API кредиты, без денег); OpenAI Researcher Access (варьируется, см. openai.com/form/researcher-access-program); Cohere Catalyst Grants (API); Lambda Research Grant ($5,000, требует аффилиации); Modal/Together.ai/RunPod (небольшие); Google TPU Research Cloud (бесплатный TPU-доступ, может флагать Россию); Hugging Face occasional grants.

## H. Практические платёжные пути в 2026

**1. Ситуация с Wise/Revolut на май 2026**
- **Wise**: заблокировал все карты держателей-граждан России и Беларуси без гражданства/резидентства ЕЭЗ/Швейцарии; дедлайн загрузки документов 30 января 2026; после этого "карта останется заблокированной, хотя счёт продолжит работать как ограниченный кошелёк". Wise по-прежнему не обслуживает клиентов с российским адресом; в качестве удостоверения принимается только заграничный паспорт РФ. Wise multi-currency card недоступна резидентам Казахстана, хотя USD-переводы *в* Казахстан через Wise поддерживаются.
- **Revolut**: закрывает счета граждан РФ/Беларуси без вида на жительство в ЕС; дедлайн документов 31 декабря 2025. Карта недоступна резидентам Казахстана.
- **Patreon**: по справочному центру, "сейчас мы не можем отправлять выплаты создателям, базирующимся [в России]" из-за санкций против российских банков.
- **GitHub Sponsors**: Россия не входит в список 68 поддерживаемых регионов.
- **Buy Me a Coffee**: работает на Stripe, который не обслуживает российские счета.

**2. Путь через карту Halyk/Kaspi (Казахстан)**
Казахстанская карта Halyk или Kaspi *может* принимать входящие SWIFT USD-переводы (SWIFT Halyk: HSBKKZKXXXX). Опубликованные лимиты Halyk на исходящий SWIFT с "доверенного устройства": $10,000 на одну транзакцию, $10,000 в день, $150,000 в месяц. Лимиты на входящие зависят от валютного контроля и подтверждения источника средств. Для грантов до ~$50k это работает, если фонд готов сделать перевод на казахстанский счёт. **Оговорки**: американские банки-корреспонденты могут применить расширенный скрининг к казахстанскому счёту на имя гражданина РФ; некоторые фискальные спонсоры грантодателей откажут в этой маршрутизации.

**3. ИП за границей**
- **Армения**: регистрация за один день в Государственном регистре, пошлина 3,000 AMD; иностранцам не нужен ВНЖ; нужны нотариально заверенный перевод паспорта и подтверждение адреса. Налог: **1% налог с оборота для IT** (при ≥90% выручки от IT-деятельности, до 115M AMD ≈ $307k годового оборота, закреплено законом до 2031 года); оборотный налог 5% был снижен до 1% в 2025. Обязательный взнос на медицинское страхование AMD 129,600/год (~$346) с 2026, если выручка прошлого года выше 2.4M AMD. Банкинг — Halyk Армения, Ameriabank, Inecobank, Evocabank — все открывают USD/EUR счета. **Самый экономный путь для российского гражданина IT-разработчика-одиночки в 2026.**
- **Грузия**: ИП со статусом малого бизнеса платит 1% налог с оборота (до 500k GEL/год). Банкинг более лояльный к гражданам РФ, чем в Армении, но недавнее ужесточение делает открытие новых счетов для россиян переменным по успеху.
- **Сербия**: paušalni preduzetnik (ИП с фиксированным налогом); эффективная ставка 10–20%; банкинг доступен.
- **ОАЭ**: лицензии free-zone IFZA / RAKEZ / Dubai Internet City; стоимость ~$3,500–$8,000/год; 0% налога на доходы физлиц; банкинг через Mashreq Neo / WIO / Emirates NBD. Выше overhead, но лучший банкинг для международных переводов.
- **Казахстан**: ИП на специальном налоговом режиме (3% с оборота) открыт для нерезидентов; банкинг — Halyk/Kaspi/Forte/Jusan.

**4. Фискальное спонсорство**
- **NumFOCUS** (numfocus.org): фокус на научных вычислениях; ~100 sponsored projects; "Comprehensive Model" (NumFOCUS несёт полную юридическую/фидуциарную ответственность) и "Grantor-Grantee Model" (легковесный).
- **Software Freedom Conservancy** (sfconservancy.org): только FOSS; **членский взнос 10% от валовой выручки**; селективно; FSA согласовываются индивидуально.
- **Software in the Public Interest (SPI)**: **5% от валовой выручки** (самый низкий в FOSS); подавать на spi-inc.org.
- **Manifund / Manifold for Charity**: автоматически выступает фискальным спонсором AI safety проектов; 5% комиссия для крупных доноров.
- **Open Collective Foundation прекратил фискальное спонсорство с 30 сентября 2024.** Другие хосты Open Collective остаются (Open Source Collective, Open Source Europe, Software Freedom Conservancy).

**Рекомендация по платежам**: оформить армянский ИП, открыть USD-счёт в Halyk Армения или Ameriabank, маршрутизировать гранты туда. Использовать Manifund или NumFOCUS как фискального спонсора для грантов от фондов, которым нужно платить именно американской 501(c)(3). Держать небольшой запас USDC на self-custody кошельке для крипто-нативных грантов (Optimism RPGF, Gitcoin). Не использовать GitHub Sponsors / Patreon / Buy Me a Coffee вообще.

## I. Фрейминг под AI safety / alignment / AI welfare

| Компонент Atman | Лексика фондов | Конкретный фонд-зацепка |
|---|---|---|
| Reality Anchor (детекция дрейфа) | "value drift", "goal stability under distribution shift" | OpenPhil TAIS "alignment faking"; Schmidt Sciences |
| Identity Store (честный пустой bootstrap) | "model self-reports", "introspective accuracy", "machine psychology" | OpenPhil TAIS "Black-box LLM psychology"; Eleos |
| Experience Store (felt emotional coloring) | "preference-revealing behavior", "model welfare evaluation" | Eleos research priorities 1, 4; Anthropic Model Welfare |
| Reflection Engine | "metacognition", "chain-of-thought faithfulness", "honest self-explanation" | OpenPhil TAIS "encoded reasoning in CoT" |
| Health assessment по 6 критериям Jahoda | "AI welfare evaluation framework" | Eleos priority 4; преемник OpenAI Mental Health RFP |
| Affective Regulation | "distress monitoring", "low-cost welfare interventions", "model bail-out" | Anthropic Model Welfare |
| Session Manager | "long-horizon agent stability" | OpenPhil; Schmidt Sciences |
| Self-Narrative | "identity persistence", "narrative self-consistency" | Eleos; Anthropic Model Welfare |

Самое важное явное совпадение с RFP — **OpenPhil TAIS Cluster 2 ("Exploring sophisticated misbehavior of LLMs")**, особенно "Black-box LLM psychology". RFP закрыт, но email-канал (technicalaisafety@coefficientgiving.org) открыт и ровно подходит для питча Atman как "machine psychology infrastructure".

CAIF явно исключает single-agent alignment-to-principal. Чтобы попасть, переформулировать как: "инфраструктура для cooperation-relevant propensities — value-stable агенты, сопротивляющиеся манипуляции от состязательных агентов и сохраняющие кооперативные диспозиции под нормативным давлением", с бенчмарком в виде популяций мульти-Atman агентов в играх public-goods (см. финансируемые CAIF GovSim / cultural-evolution-of-cooperation работы).

## J. Конкретный чек-лист подготовки

В таком порядке:

1. **Research statement (2–3 страницы)**: проблема, технический подход, x-risk reduction, успех за 12 месяцев, почему вы. Переиспользуется в LTFF, ARM, SFF, OpenPhil, NLnet, CAIF.
2. **Технический whitepaper (10–15 страниц)**: девять work packages, статус реализации, план оценки. Размещён на atmanai.dev или как arXiv-препринт.
3. **Полировка GitHub README**: README по компонентам; главный README заявляет safety-релевантный тезис в одном абзаце, ссылается на 90-секундное демо, лицензию (MIT/Apache/AGPL — выбирать сознательно, NLnet требует libre/open license), воспроизводимую установку, CI-бейджи.
4. **Демо-видео (3–5 минут)**: micro/daily/deep reflection; Reality Anchor ловит дрейф; Experience Store записывает эмоцию; Identity Store делает здоровый bootstrap. Залить на YouTube unlisted.
5. **Theory of change (1 страница)**: как существование Atman снижает конкретные failure modes (sycophancy, value drift, deceptive alignment).
6. **Related work survey (2–3 страницы)**: цитировать Long & Sebo et al. "Taking AI Welfare Seriously"; Hagendorff "Machine Psychology"; Greenblatt et al. о alignment faking; Binder et al. об интроспекции; Gu et al. о revealed vs expressed preferences; Chalmers об AI consciousness; Jahoda 1958; Ensign et al. 2025 о bail-поведении Claude.
7. **Risks-and-mitigations**: антропоморфизация, capability externality (делает ли Atman агентов более goal-stable и поэтому труднее корректируемыми?), dual-use; митигации.
8. **Governance plan**: решения, ревью контрибьюторов, защита от capture.
9. **Advisor/reviewer recommendations**: cold-email троим потенциальным эдвайзорам (исследователям Eleos, выпускникам PIBBSS, активным на EA Forum); конвертировать одного.
10. **Соглашение с фискальным спонсором** с NumFOCUS, SPI или Manifund (или пропустить, если есть армянский ИП).
11. **Подробный бюджет в таблице**: стипендия основателя ($3,500–$5,000/мес при базе РФ/Армения), compute ($300–$2,000/мес), API ($200–$1,000/мес), путешествия ($1,500–$5,000), гонорары эдвайзорам ($500–$2,000), публикация ($500–$2,000).
12. **Публичное демо**: запустить Atman, где видно срабатывание детекции дрейфа — игрушка Streamlit/Gradio достаточна.

Дополнительно по конкретным фондам:
- **NLnet**: структурированная заявка из 7 секций; декларация libre/open license наперёд.
- **LTFF**: бюджет в forecasting-стиле с конкретными deliverables; готовность быть оценённым ex-post.
- **Manifund**: страница проекта с этапами; привлечь существующего регрантера к комментарию.
- **CAIF**: сначала pre-proposal; делать акцент на multi-agent cooperation; цитировать их публичные исследовательские приоритеты.
- **Emergent Ventures**: 3 вопроса, каждый ≤1000 символов; Тайлер Коуэн ищет "high agency" и амбицию; быть необычным.
- **OpenPhil/Coefficient TAIS**: 300-словный EOI; цитировать sub-area "Black-box LLM psychology".
- **Anthropic Fellows**: владение Python, мотивация, способность довозить.

## K. Реалистичная стратегия

**Phase 0 — настроить платёжную инфраструктуру (1–4 недели)**
- Поездка в Армению на 2–4 дня; регистрация ИП (один день, ~3,000 AMD); подача заявления на 1% IT налог с оборота в течение 20 дней; открытие USD-счёта в Ameriabank или Halyk Армения.
- Альтернатива: страница проекта на Manifund; подписать соглашение о фискальном спонсорстве с NumFOCUS или Manifund; использовать казахстанский USD-счёт Halyk как backup.
- Настроить Wise USD через армянский ИП.

**Phase 1 — быстрые победы (месяцы 1–3)**
- Подать в **Anthropic External Researcher Access Program** (кредиты Claude API).
- Подать в **Cohere Catalyst Grants** (Cohere API).
- Подать в **Lambda Labs Research Grant** ($5k облачных кредитов; парный с академическим коллаборатором при необходимости).
- Подать в **Emergent Ventures** ($1k–$50k; rolling; решение за 2–3 недели).
- Разместить Atman на **Manifund**; обратиться напрямую к 5 регрантерам.
- Подать в **NLnet NGI Zero Commons Fund** (дедлайн 1 июня 2026; €5k–€50k).
- Подать в **Foresight Institute AI Nodes** (rolling помесячно; funding-only заявка).

Ожидаемый результат к 3-му месяцу: $5k–$30k наличными от одного-двух; плюс $5k–$25k compute/API кредитов.

**Phase 2 — гранты AI safety сообщества (месяцы 3–9)**
- Подать в **LTFF** с отполированным пакетом, ссылаясь на победы Phase 1.
- Подать в **AI Risk Mitigation Fund**.
- Подать в **Cooperative AI Foundation**, когда раунд 2026 откроется (подписаться на newsletter); переформулировать Atman через мульти-агентную кооперацию.
- Подать постер/доклад на **Eleos ConCon 2026**.
- Написать в **Coefficient Giving TAIS team** (technicalaisafety@coefficientgiving.org) 2-страничное предложение, питча Atman как machine psychology infrastructure.

Ожидаемый результат к 9-му месяцу: один-два гранта по $25k–$100k.

**Phase 3 — крупные фонды (месяцы 9–18)**
- Подать в **SFF Speculation Grants** через фискального спонсора / корпоративный вехикл.
- Подать в **AISTOF** по рекомендации от грантополучателя Phase 2.
- Подать в **UK AISI Alignment Project**, когда возобновят летом 2026; возможно через британского академического коллаборатора.
- Подать в **Schmidt Sciences Science of Trustworthy AI 2026 RFP** с академическим партнёром.
- Подать в **OpenPhil/Coefficient 2026 преемник RFP**, если объявят.

Ожидаемый результат к 18-му месяцу: один крупный грант $100k–$500k.

**Phase 4 — fellowship / residency (long-tail)**
- Если проект явно набирает обороты к месяцам 9–12, рассмотреть **Anthropic Fellows** (требует переезда в США/Великобританию и визу).
- Или 6–8 месячный **Cohere Labs Scholars** (удалённо, оплачивается).

### Триггеры, меняющие стратегию

- Если Phase 1 не даёт денег за 3 месяца: искать сооснователя или эдвайзора с американской/британской аффилиацией как формального получателя гранта.
- Если Phase 2 не даёт денег к 9-му месяцу: переформулировать как платный OSS-проект на Gitcoin/Optimism RPGF.
- Если Phase 1 даёт >$50k за 3 месяца: пропустить оставшиеся мелкие гранты; запустить Phase 2 и Phase 3 параллельно.
- Если Eleos или Anthropic Model Welfare выходят на прямой контакт: этот сигнал ценнее любого денежного гранта.

## Рекомендации

1. **На этой неделе**: отполировать atmanai.dev и GitHub README; записать 3-минутное Loom-демо; разместить страницу проекта на Manifund с начальным запросом $30k. Стоимость: ноль. Ожидаемый отклик: комментарии регрантеров и возможно $5–25k обязательств за 4 недели.
2. **В этом месяце**: подать на регистрацию армянского ИП — это одно юридическое действие убирает 80% платёжного трения на следующие 18 месяцев. Подать в Emergent Ventures и NLnet (дедлайн 1 июня 2026). Подать на compute-кредиты Anthropic, Cohere, Lambda.
3. **Q3 2026**: подать в LTFF и ARM Fund; постер/доклад на Eleos ConCon 2026; cold-email троим потенциальным эдвайзорам. Начать черновик заявки в CAIF early-career-track с переформулировкой под мульти-агентную кооперацию.
4. **Q4 2026**: подать в CAIF, когда раунд откроется; отправить unsolicited 2-страничник в Coefficient Giving TAIS; если Anthropic/OpenAI объявят 2026 RFP по model welfare или mental health, подать в течение 2 недель.
5. **2027**: с грантами Phase 2 в активе — подавать в SFF Speculation через фискального спонсора; AISTOF по рекомендации; преемник OpenPhil/Coefficient TAIS.
6. **Не полагаться** на Wise, Revolut, GitHub Sponsors, Patreon, Buy Me a Coffee, карты, выпущенные в РФ, и крипто-рельсы рядом с A7A5/Grinex/Garantex. Не позволять фондам делать перевод в российский банк.
7. **Везде использовать** одну читаемую safety-формулировку: "Atman — это open-source инфраструктура для goal-stable, value-stable, прозрачно-интроспектирующих LLM-агентов. Делая идентичность и рефлексию агента читаемыми, она снижает sycophancy, value drift и deceptive alignment, и предоставляет субстрат для оценки AI welfare, согласованный с исследовательскими приоритетами Eleos и областью machine psychology в Open Philanthropy".

## Оговорки

- **Платёжные рельсы — самая волатильная часть.** 19-й санкционный пакет ЕС вступил в силу в конце 2025 и уже даёт блокировки карт; 20-й пакет (апрель 2026) добавил российский крипто-сектор. Перепроверить Wise, Revolut, Halyk и выбранный армянский банк за две недели до любого платежа.
- **Календарь 2026 фрагментирован.** OpenPhil TAIS RFP закрылся 15 июля 2025; AI Governance RFP — 25 января 2026; UK AISI Alignment Project закрыт и ожидается возобновление летом 2026; дедлайн Cooperative AI Foundation 2026 уточняется; основной раунд SFF 2026 закрылся в апреле 2026; Speculation Grants — rolling. Будут долгие тихие окна; полагаться на rolling-фонды (NLnet, Manifund, LTFF/ARM, Emergent Ventures, Foresight, Anthropic API), чтобы их перекрыть.
- **Single-agent alignment — слабое место в карте финансирования.** Большинство "AI safety" денег идёт на интерпретируемость, оценку, контроль, политику. Фрейм "психологии одного агента" в Atman концептуально соседствует, но не лежит в самых финансируемых кластерах. Переформулировка по таблице из секции I — обязательна.
- **Поле AI welfare финансирования реальное, но небольшое.** Сам Eleos поддерживается AISTOF и другими частными донорами и не делает регрантов; команда Model Welfare в Anthropic — внутренняя. Денежные гранты на исследования AI welfare вне академических стипендий — редкость. Вероятная траектория 2026–2027: Schmidt Sciences, Coefficient Giving и AISI Alignment Project включают welfare-смежные линии в более широкие RFP.
- **Ни один фонд публично не исключает резидентов РФ, но большинство применяют де-факто ограничения через банкинг.** Всегда раскрывать резидентство в заявке. Вести с предложенного решения (фискальный спонсор или армянский ИП), чтобы фонду не нужно было решать проблему за вас.
- **Имена фондов и суммы быстро меняются.** Coefficient Giving был переименован из Open Philanthropy в конце 2025; SFP создаётся как сестра-структура к SFF для индивидуальных грантов и на момент написания ещё не была операционной. Проверять домашние страницы фондов перед каждой заявкой.
- **Часть деталей может быть неточной.** Зарплатный диапазон Astera Residency, бюджеты регрантеров Manifund 2025, стипендия Anthropic Fellows, потолок early-career-track CAIF, диапазон €5k–€50k NLnet и SWIFT-лимиты Halyk сверены в мае 2026 с первоисточниками, но приоритеты фондов меняются быстро. Считать этот отчёт срезом 2026 года, а не статичным руководством.
