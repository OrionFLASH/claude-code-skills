#!/usr/bin/env python3
"""Банки вопросов режима идеи 1.5 (дополняют intake.CONCEPT_BANK из 40 вопросов) и разбор текста запроса.

Что здесь (references/intake.md, раздел «Режим идеи: опрос 1.5»):
  INTRO            карточка «Начало» (до банка): для кого приложение (личный режим), режим опроса (по темам / быстро /
                   глубоко), политика моделей и effort субагентов (tools.agents)
  PERSONAL         замены вопросов банка для личного режима (project.audience = personal | circle | personal_then_public):
                   вместо сегмента, доступа, цены, «кто платит» и т. п. — задача владельца, частота, точность, хранение,
                   стоимость владения, поддержка, срок жизни, личный успех, выпуск наружу
  BLOCKS           условные блоки: ИИ в продукте, администрирование, данные и интеграции, внешняя платформа (FB-056),
                   предметная область и право (динамически по областям), интерфейс, прототип, контекст владельца, оплата
  prefill_from_text  эвристический разбор свободного текста идеи/запроса → предзаполнение ответов с цитатой и уверенностью
  request_questions  вопросы запроса → idea.request_questions[] {id: RQ01…, text, kind: research|deliverable|format} (FB-001)
  classify_urls      ссылки из запроса → материалы владельца {url, kind, role, status, tool, note} (FB-002)
  parse_forms        свободный ответ «Форма» → основная форма, все формы, формы «на потом» (FB-024)

Модуль не импортирует intake (во избежание круговых импортов): банк передаётся аргументом. Формат вопроса — как у
CONCEPT_BANK: (id, тема, приоритет, header ≤ 12, вопрос, мультивыбор, [(label, description, {путь: значение})]); первый
вариант — по умолчанию «(Recommended)». Только стандартная библиотека.
"""
import re

CONFIDENT = 0.8                        # уверенность, с которой ответ из текста выносится на подтверждение, а не спрашивается
MIN_LIVE = 15                          # минимум «живых» вопросов об идее (как CONCEPT_MIN_QUESTIONS)

# ---------------------------------------------------------------- карточка «Начало»
AUDIENCE = ("personal", "circle", "personal_then_public", "public")
PERSONAL_AUDIENCES = ("personal", "circle", "personal_then_public")
INTRO = [
    ("i01", "intro", 1, "Для кого", "Для кого приложение?", False, [
        ("Публичный продукт (Recommended)", "Аудитория и, возможно, деньги — полный разбор рынка, каналов и модели дохода",
         {"project.audience": "public"}),
        ("Только для меня", "Личный инструмент: без аудитории, маркетинга и монетизации",
         {"project.audience": "personal", "project.release_outward": False, "project.goal": "personal"}),
        ("Для меня и узкого круга", "Семья, команда, друзья — без маркетинга и продаж",
         {"project.audience": "circle", "project.release_outward": False, "project.goal": "personal"}),
        ("Сначала для себя, потом публично", "Личный режим и раздел «Если захочется выпустить наружу»",
         {"project.audience": "personal_then_public", "project.release_outward": True, "project.goal": "personal"})]),
    ("i02", "intro", 2, "Опрос", "Как задавать вопросы об идее?", False, [
        ("По темам, с вариантами (Recommended)", "Пачки по 4 вопроса; блоки ИИ, админки, данных — по ответам",
         {"idea.interview_mode": "standard"}),
        ("Быстро: подтвердить таблицу", "Значения по умолчанию и из запроса — таблицей на тему; правите только несогласное",
         {"idea.interview_mode": "fast"}),
        ("Глубоко: все блоки целиком", "Все вопросы дополнительных блоков: ИИ, админка, данные, интерфейс, прототип",
         {"idea.interview_mode": "deep"})]),
    ("i03", "intro", 3, "Модели", "Как выбирать модели для субагентов?", False, [
        ("Триаж TypeSafe, если есть (Recommended)", "typesafe-triage подбирает модель на задачу; нет его — правила скилла",
         {"tools.agents.model_policy": "triage"}),
        ("По умолчанию скилла", "Сбор данных — sonnet; синтез, оценка и дизайн — opus", {"tools.agents.model_policy": "default"}),
        ("Свои правила", "Опишите в «Other», например «всё на opus»", {"tools.agents.model_policy": "custom"})]),
    ("i04", "intro", 4, "Effort", "Регулировать effort (глубину рассуждений) субагентов?", False, [
        ("Нет, по умолчанию (Recommended)", "Effort не задаётся: агенты работают со своей глубиной",
         {"tools.agents.effort_policy": "none"}),
        ("Да, явно по задаче", "Effort задаётся каждому агенту (по триажу или правилам) и пишется в журнал агентов",
         {"tools.agents.effort_policy": "explicit"})]),
]

# ---------------------------------------------------------------- личный режим: замены вопросов банка
# заменяемый id банка → вопрос личного режима (та же тема и приоритет — покрытие тем и порядок сохраняются)
PERSONAL = {
    "c06": ("p01", "audience", 2, "Моя задача", "Какую вашу задачу решает приложение?", False, [
        ("Экономит моё время (Recommended)", "Рутина, которую сейчас делаю руками", {"idea.facets.personal_job": "time", "idea.facets.segment": "self"}),
        ("Помогает принимать решения", "Расчёты, сравнения, подсказки перед действием", {"idea.facets.personal_job": "decisions", "idea.facets.segment": "self"}),
        ("Хранит и упорядочивает данные", "Свои записи, файлы, история в одном месте", {"idea.facets.personal_job": "organize", "idea.facets.segment": "self"}),
        ("Учусь и экспериментирую", "Проект ради навыков и интереса", {"idea.facets.personal_job": "learning", "idea.facets.segment": "self"})]),
    "c08": ("p02", "audience", 20, "Как часто я", "Как часто вы лично будете пользоваться приложением?", False, [
        ("Каждый день (Recommended)", "Повседневный инструмент", {"idea.facets.personal_frequency": "daily"}),
        ("Несколько раз в неделю", "Регулярно, но не ежедневно", {"idea.facets.personal_frequency": "weekly"}),
        ("Раз в месяц и реже", "По расписанию: отчёты, сверки", {"idea.facets.personal_frequency": "monthly"}),
        ("Эпизодически, по событию", "Когда случается повод", {"idea.facets.personal_frequency": "episodic"})]),
    "c09": ("p03", "audience", 29, "Точность", "Насколько критичны точность и надёжность?", False, [
        ("Важны, ошибку замечу сам (Recommended)", "Перепроверю важное вручную", {"idea.facets.reliability_need": "medium"}),
        ("Критичны: деньги или здоровье", "Ошибка стоит дорого — нужны проверки и журнал", {"idea.facets.reliability_need": "high"}),
        ("Не критичны: черновые подсказки", "Достаточно «примерно верно»", {"idea.facets.reliability_need": "low"})]),
    "c10": ("p04", "audience", 30, "Хранение", "Где хранить данные приложения?", False, [
        ("На моём устройстве (Recommended)", "Локально, без облака — приватно и бесплатно", {"idea.facets.data_location": "local"}),
        ("На своём сервере", "VPS или домашний сервер", {"idea.facets.data_location": "own_server"}),
        ("В облаке", "Облачная база или сервис", {"idea.facets.data_location": "cloud"}),
        ("Локально и копия в облаке", "Основное — на устройстве, резервная копия — в облаке", {"idea.facets.data_location": "hybrid"})]),
    "c26": ("p05", "money", 6, "Владение", "Сколько готовы тратить на владение в месяц?", False, [
        ("Ноль: только бесплатное (Recommended)", "Хостинг и API — только бесплатные уровни",
         {"idea.facets.ownership_budget": "zero", "strategy.monetization": "none", "strategy.paid_tier": "no"}),
        ("До 500 ₽ / $5", "Недорогой хостинг или API", {"idea.facets.ownership_budget": "low", "strategy.monetization": "none", "strategy.paid_tier": "no"}),
        ("До 3000 ₽ / $30", "Платные API, сервер с GPU по часам", {"idea.facets.ownership_budget": "mid", "strategy.monetization": "none", "strategy.paid_tier": "no"}),
        ("Сколько потребуется", "Готов платить за надёжность и скорость", {"idea.facets.ownership_budget": "any", "strategy.monetization": "none", "strategy.paid_tier": "no"})]),
    "c27": ("p06", "money", 17, "Моя польза", "Что будет пользой для вас?", False, [
        ("Экономия времени (Recommended)", "Часы в месяц, которые освободятся", {"idea.facets.personal_value": "time"}),
        ("Деньги: экономия или доход", "Посчитаю в рублях", {"idea.facets.personal_value": "money"}),
        ("Меньше ошибок и потерь", "Надёжнее, чем прежний способ", {"idea.facets.personal_value": "errors"}),
        ("Спокойствие и обучение", "Контроль, понимание, новые навыки", {"idea.facets.personal_value": "calm"})]),
    "c28": ("p07", "money", 25, "Поддержка", "Сколько часов в месяц готовы тратить на поддержку?", False, [
        ("До 2 часов (Recommended)", "Обновления и мелкие правки", {"idea.facets.support_hours_month": 2}),
        ("2–8 часов", "Регулярное развитие", {"idea.facets.support_hours_month": 5}),
        ("Больше 8 часов", "Активная доработка", {"idea.facets.support_hours_month": 12}),
        ("Не готов поддерживать", "Нужен вариант «поставил и забыл»", {"idea.facets.support_hours_month": 0})]),
    "c29": ("p08", "money", 37, "Срок жизни", "Сколько планируете пользоваться приложением?", False, [
        ("Годы, это надолго (Recommended)", "Важны обновления, бэкапы, миграции", {"idea.facets.project_lifetime": "years"}),
        ("Год-два", "Средний срок", {"idea.facets.project_lifetime": "1-2y"}),
        ("Под конкретную задачу", "Потом можно выбросить", {"idea.facets.project_lifetime": "task"})]),
    "c39": ("p09", "risks", 14, "Мой успех", "Что будет успехом через 6 месяцев?", False, [
        ("Пользуюсь каждую неделю (Recommended)", "Приложение прижилось",
         {"strategy.success_criteria": "пользуюсь приложением каждую неделю через 6 месяцев"}),
        ("Экономлю часы каждый месяц", "Измеримая экономия времени",
         {"strategy.success_criteria": "экономлю не меньше 4 часов в месяц через 6 месяцев"}),
        ("Меньше ошибок и потерь", "Надёжнее прежнего способа",
         {"strategy.success_criteria": "меньше ошибок и потерь, чем при прежнем способе, через 6 месяцев"}),
        ("Заменил старый инструмент", "Таблица или чужой сервис больше не нужны",
         {"strategy.success_criteria": "прежний способ (таблица, заметки, чужой сервис) полностью заменён через 6 месяцев"})]),
    "c15": ("p10", "value", 32, "Выпуск", "Допускаете ли когда-нибудь выпуск наружу?", False, [
        ("Возможно, если приживётся (Recommended)", "Опишу условия выхода к аудитории", {"project.release_outward": True}),
        ("Нет, только для себя", "Раздел о выпуске не нужен", {"project.release_outward": False}),
        ("Да, это цель", "Сначала для себя, затем публично", {"project.release_outward": True, "project.audience": "personal_then_public"})]),
}
PERSONAL_SCOPE_OFF = ("keywords", "events")   # личный режим: поисковый спрос и календарь событий не нужны (SM, разд. 4.3)

# ---------------------------------------------------------------- условные блоки
# ключ → (название, когда показывается, вопросы)
BLOCKS = {
    "ai": ("ИИ в продукте", "ответ «ИИ» не «Без ИИ» или ИИ в тексте идеи", [
        ("ai01", "ai", 1, "ИИ: роль", "Что делает ИИ в продукте? (можно несколько)", True, [
            ("Объясняет готовые данные (Recommended)", "Числа считает код, модель объясняет и подсказывает", {"idea.facets.ai_role": ["explain"]}),
            ("Извлекает и классифицирует", "Разбор текстов, документов, новостей", {"idea.facets.ai_role": ["extract"]}),
            ("Генерирует тексты или код", "Черновики, описания, код", {"idea.facets.ai_role": ["generate"]}),
            ("Рекомендует или действует сам", "Советы пользователю или агент с инструментами", {"idea.facets.ai_role": ["recommend"]})]),
        ("ai02", "ai", 2, "ИИ: где", "Где работает модель?", False, [
            ("Локально, облако позже (Recommended)", "Ollama, LM Studio, llama.cpp на устройстве", {"idea.facets.ai_where": "local_then_cloud"}),
            ("Только локально", "Без облака: приватность и офлайн", {"idea.facets.ai_where": "local"}),
            ("Облачный API", "Внешний провайдер моделей", {"idea.facets.ai_where": "cloud"}),
            ("Свой сервер с GPU", "Модель на своём сервере", {"idea.facets.ai_where": "server"})]),
        ("ai03", "ai", 3, "ИИ: данные", "Что из данных пользователя уходит в модель?", False, [
            ("Только нужное, без хранения (Recommended)", "Промпты и ответы не храним", {"idea.facets.ai_data": "minimal_no_store"}),
            ("Храним историю локально", "История на устройстве пользователя", {"idea.facets.ai_data": "local_history"}),
            ("Храним на сервере с согласием", "Срок хранения и право на удаление", {"idea.facets.ai_data": "server_with_consent"}),
            ("Только обезличенные данные", "Перед отправкой убираем личное", {"idea.facets.ai_data": "anonymized"})]),
        ("ai04", "ai", 4, "ИИ: ошибки", "Во что обойдётся ошибка модели?", False, [
            ("Неприятно, но не страшно (Recommended)", "Пользователь легко заметит и исправит", {"idea.facets.ai_error_cost": "low"}),
            ("Потеря денег", "Неверный расчёт или совет ведёт к убытку", {"idea.facets.ai_error_cost": "money"}),
            ("Здоровье или безопасность", "Нужны строгие ограничения", {"idea.facets.ai_error_cost": "health"}),
            ("Правовые последствия", "Совет может нарушить закон", {"idea.facets.ai_error_cost": "law"})]),
        ("ai05", "ai", 5, "ИИ: защита", "Какие защиты нужны? (можно несколько)", True, [
            ("Числа считает код (Recommended)", "Модель не считает: числа проверяются кодом", {"idea.facets.ai_guardrails": ["code_numbers"]}),
            ("Запретные формулировки", "Фильтр советов и обещаний", {"idea.facets.ai_guardrails": ["forbidden_phrases"]}),
            ("Обязательные оговорки", "Дисклеймеры в ответах", {"idea.facets.ai_guardrails": ["disclaimers"]}),
            ("Откат на шаблон", "Если модель недоступна или ошиблась", {"idea.facets.ai_guardrails": ["fallback_template"]})]),
        ("ai06", "ai", 6, "ИИ: железо", "На каком железе запускается модель?", False, [
            ("Ноутбук 16–32 ГБ (Recommended)", "Модели до 8–14B без отдельной видеокарты", {"idea.facets.ai_hardware": "laptop_16_32"}),
            ("Мощный ПК или Mac 32+ ГБ", "Модели до 32B", {"idea.facets.ai_hardware": "workstation_32plus"}),
            ("Только браузер, без установки", "Модель в облаке или в браузере", {"idea.facets.ai_hardware": "browser_only"}),
            ("Сервер или облако", "Пользователю железо не нужно", {"idea.facets.ai_hardware": "server"})]),
        ("ai07", "ai", 7, "ИИ: эталоны", "Как проверять качество ответов модели?", False, [
            ("Набор эталонных сценариев (Recommended)", "10–30 сценариев с ожидаемым ответом и порог регрессии", {"idea.facets.ai_eval": "golden_set"}),
            ("Офлайн-бенчмарк моделей", "Сравнить модели до выбора", {"idea.facets.ai_eval": "benchmark"}),
            ("Оцениваю сам вручную", "Выборочная проверка", {"idea.facets.ai_eval": "manual"}),
            ("Пока не нужно", "Проверка позже", {"idea.facets.ai_eval": "none"})]),
        ("ai08", "ai", 8, "ИИ: вывод", "Как показывать ответ ИИ?", False, [
            ("Целиком после проверки (Recommended)", "Сначала проверка чисел и фильтров, затем показ", {"idea.facets.ai_output": "after_check"}),
            ("Потоком по мере генерации", "Быстрее, но без предварительной проверки", {"idea.facets.ai_output": "stream"}),
            ("С источниками чисел", "Пометки «посчитано кодом» и «сверено N из N»", {"idea.facets.ai_output": "with_sources"})]),
        ("ai09", "ai", 9, "ИИ: скорость", "Какое время ответа модели допустимо?", False, [
            ("До 10 секунд (Recommended)", "С прогрессом и кнопкой отмены", {"idea.facets.ai_latency": "10s"}),
            ("До 2 секунд", "Интерактивный режим", {"idea.facets.ai_latency": "2s"}),
            ("Минута, в фоне", "Пользователь вернётся к результату", {"idea.facets.ai_latency": "background"})]),
        ("ai10", "ai", 10, "ИИ: метрики", "Какую статистику работы ИИ видеть? (можно несколько)", True, [
            ("Время ответа и ошибки (Recommended)", "p50/p95, ошибки по классам, доля откатов", {"idea.facets.ai_observability": ["latency_errors"]}),
            ("Токены и стоимость", "Токены в секунду, цена запроса", {"idea.facets.ai_observability": ["tokens_cost"]}),
            ("Качество по эталонам", "Сверка чисел и регрессия", {"idea.facets.ai_observability": ["quality"]}),
            ("Нагрузка модели и памяти", "Память, загрузка, индикатор здоровья", {"idea.facets.ai_observability": ["resources"]})]),
        ("ai11", "ai", 11, "ИИ: безопасн", "От чего защищать ИИ-часть? (можно несколько)", True, [
            ("Инъекции из данных (Recommended)", "Новости, сообщения, страницы — данные, не инструкции", {"idea.facets.ai_security": ["prompt_injection"]}),
            ("Утечка секретов и ключей", "Ключи не попадают в промпты и журналы", {"idea.facets.ai_security": ["secrets"]}),
            ("Лишние права агента", "Ограничение инструментов", {"idea.facets.ai_security": ["tool_limits"]}),
            ("Выполнение кода", "Изоляция запуска кода", {"idea.facets.ai_security": ["code_sandbox"]})]),
        ("ai12", "ai", 12, "ИИ: модели", "Как выбирается модель?", False, [
            ("Подбор под железо (Recommended)", "Рекомендация по памяти; выбор — эталонным тестом до текста", {"idea.facets.ai_models": "auto_by_hardware"}),
            ("Фиксированная модель", "Одна модель для всех", {"idea.facets.ai_models": "fixed"}),
            ("Выбирает пользователь", "Список моделей в настройках", {"idea.facets.ai_models": "user_choice"})]),
        ("ai13", "ai", 13, "ИИ: версии", "Версионировать промпты, фильтры и схемы ответа?", False, [
            ("Да, с откатом (Recommended)", "Версия в журнале, откат одной кнопкой", {"idea.facets.ai_versioning": True}),
            ("Пока рано", "Без версий на старте", {"idea.facets.ai_versioning": False})]),
    ]),
    "admin": ("Администрирование и эксплуатация", "веб-продукт или сервис", [
        ("ad01", "admin", 1, "Адм: кто", "Кто администрирует продукт?", False, [
            ("Только я (Recommended)", "Владелец — единственный администратор", {"idea.facets.admin_who": "owner"}),
            ("Я и помощники", "Несколько человек без сложных ролей", {"idea.facets.admin_who": "owner_helpers"}),
            ("Команда с ролями", "Права по ролям", {"idea.facets.admin_who": "team"}),
            ("Пользователь сам себе админ", "Настройки у каждого пользователя", {"idea.facets.admin_who": "self"})]),
        ("ad02", "admin", 2, "Адм: настр.", "Что настраивать без правки кода? (можно несколько)", True, [
            ("Источники данных и ключи API (Recommended)", "Подключения, ключи, адреса", {"idea.facets.admin_settings": ["data_sources_keys"]}),
            ("Модели и промпты", "Выбор модели, тексты промптов", {"idea.facets.admin_settings": ["models_prompts"]}),
            ("Лимиты, флаги, тарифы", "Таймауты, флаги функций, справочники", {"idea.facets.admin_settings": ["limits_flags_tariffs"]}),
            ("Тексты и дисклеймеры", "Оговорки и подсказки", {"idea.facets.admin_settings": ["texts"]})]),
        ("ad03", "admin", 3, "Адм: бэкапы", "Как сохранять и восстанавливать данные?", False, [
            ("Автокопия раз в день (Recommended)", "Копия и проверка восстановления", {"idea.facets.admin_backup": "daily"}),
            ("Экспорт вручную", "Файл по кнопке", {"idea.facets.admin_backup": "manual_export"}),
            ("Синхронизация между устройствами", "Перенос и копия одновременно", {"idea.facets.admin_backup": "sync"}),
            ("Не нужно", "Данные не жалко потерять", {"idea.facets.admin_backup": "none"})]),
        ("ad04", "admin", 4, "Адм: журнал", "Какой журнал нужен?", False, [
            ("Изменения настроек (Recommended)", "Кто, что и когда поменял", {"idea.facets.admin_log": "settings"}),
            ("Настройки и все вызовы", "Плюс журнал запросов к источникам и модели", {"idea.facets.admin_log": "settings_calls"}),
            ("Не нужен", "Без журнала", {"idea.facets.admin_log": "none"})]),
        ("ad05", "admin", 5, "Адм: монитор", "Как узнавать о проблемах?", False, [
            ("Сигнал на экране (Recommended)", "Индикатор здоровья: задержки, ошибки источников, истёкшие ключи", {"idea.facets.admin_alerts": "screen"}),
            ("Сообщение в мессенджер или почту", "Оповещения наружу", {"idea.facets.admin_alerts": "messenger_email"}),
            ("Не нужно", "Проверю сам при случае", {"idea.facets.admin_alerts": "none"})]),
        ("ad06", "admin", 6, "Адм: обновл.", "Как обновлять данные, модели и схему базы?", False, [
            ("Миграции с откатом (Recommended)", "Версия схемы и откат", {"idea.facets.admin_updates": "migrations_rollback"}),
            ("Вручную по инструкции", "Шаги в README", {"idea.facets.admin_updates": "manual"}),
            ("Автоматически", "Обновление без участия", {"idea.facets.admin_updates": "auto"})]),
        ("ad07", "admin", 7, "Адм: роли", "Нужны ли вход и роли для нескольких людей?", False, [
            ("Нет, один пользователь (Recommended)", "Без входа и ролей", {"idea.facets.admin_roles": "none"}),
            ("Вход и роли", "Права, восстановление, журнал входов", {"idea.facets.admin_roles": "roles"}),
            ("Вход без ролей", "У всех одинаковые права", {"idea.facets.admin_roles": "login_only"})]),
        ("ad08", "admin", 8, "Адм: саппорт", "Кто поддерживает пользователей?", False, [
            ("Я сам, по почте (Recommended)", "Ответы по мере сил", {"idea.facets.admin_support": "owner_email"}),
            ("Чат или бот поддержки", "Канал в мессенджере", {"idea.facets.admin_support": "chat"}),
            ("Не нужно", "Пользователей кроме меня нет", {"idea.facets.admin_support": "none"})]),
        ("ad09", "admin", 9, "Адм: право", "Кто исполняет запросы на удаление и экспорт данных?", False, [
            ("Я вручную по запросу (Recommended)", "Процедура в README и политике", {"idea.facets.admin_legal": "manual"}),
            ("Кнопка в настройках", "Пользователь сам удаляет и выгружает", {"idea.facets.admin_legal": "self_service"}),
            ("Не нужно: данных нет", "Личных данных не храним", {"idea.facets.admin_legal": "none"})]),
    ]),
    "data": ("Данные и интеграции", "продукт зависит от внешних данных или API", [
        ("da01", "data", 1, "Дан: источн.", "Какие внешние источники данных нужны? (можно несколько)", True, [
            ("Найти в исследовании (Recommended)", "Источники, лимиты и инструкции подключения — в исследовании", {"idea.facets.data_sources_needed": ["research"]}),
            ("Официальные API сервисов", "Биржи, платформы, агрегаторы", {"idea.facets.data_sources_needed": ["official_api"]}),
            ("Открытые данные и файлы", "Открытые наборы, вики, выгрузки", {"idea.facets.data_sources_needed": ["open_data"]}),
            ("Ручной ввод и импорт", "Пользователь вносит или загружает сам", {"idea.facets.data_sources_needed": ["manual_import"]})]),
        ("da02", "data", 2, "Дан: лиценз.", "Что допустимо по лицензиям данных?", False, [
            ("Только явно разрешённое (Recommended)", "Показ и хранение — по условиям источника", {"idea.facets.data_license": "explicit_only"}),
            ("Показ с задержкой", "Бесплатные данные с задержкой", {"idea.facets.data_license": "delayed_display"}),
            ("Платная подписка на данные", "Есть бюджет на данные", {"idea.facets.data_license": "paid_feed"})]),
        ("da03", "data", 3, "Дан: ключи", "Чьи ключи API используются?", False, [
            ("Ключи пользователя с инструкцией (Recommended)", "Пошаговая инструкция получения ключа", {"idea.facets.data_keys": "user_keys"}),
            ("Ключи сервиса", "Ключи владельца на сервере", {"idea.facets.data_keys": "service_keys"}),
            ("Ключи не нужны", "Открытые источники без ключей", {"idea.facets.data_keys": "none"})]),
        ("da04", "data", 4, "Дан: сбои", "Что делать при недоступности источника?", False, [
            ("Кэш и пометка свежести (Recommended)", "Показ последних данных с датой", {"idea.facets.data_fallback": "cache_freshness"}),
            ("Запасной источник", "Слой адаптеров с подменой", {"idea.facets.data_fallback": "backup_source"}),
            ("Показать ошибку", "Без подмены", {"idea.facets.data_fallback": "error"})]),
        ("da05", "data", 5, "Дан: доступ", "Есть ли ограничения доступа к данным из вашей страны?", False, [
            ("Проверить в исследовании (Recommended)", "Санкции, блокировки, ключи по паспорту", {"idea.facets.data_jurisdiction": "research"}),
            ("Есть санкции или блокировки", "Нужны обходные законные варианты", {"idea.facets.data_jurisdiction": "restricted"}),
            ("Ограничений нет", "Доступ открыт", {"idea.facets.data_jurisdiction": "none"})]),
        ("da06", "data", 6, "Дан: достав.", "Кто запрашивает данные у источников?", False, [
            ("Сервер с кэшем (Recommended)", "Сервер забирает и кэширует", {"idea.facets.data_delivery": "server_cache"}),
            ("Браузер пользователя напрямую", "Без своего сервера", {"idea.facets.data_delivery": "client"}),
            ("Офлайн-файлы", "Данные загружаются файлами", {"idea.facets.data_delivery": "offline_files"})]),
        ("da07", "data", 7, "Дан: история", "Сколько хранить историю данных?", False, [
            ("Год, локальная база (Recommended)", "SQLite или файлы на устройстве", {"idea.facets.data_history": "1y_local"}),
            ("Несколько лет, серверная база", "PostgreSQL или аналог", {"idea.facets.data_history": "years_server"}),
            ("Только текущие значения", "История не нужна", {"idea.facets.data_history": "none"})]),
    ]),
    "platform": ("Внешняя платформа", "продукт зависит от игры, платформы, маркетплейса или чужого API", [
        ("pl01", "platform", 1, "Пл: какая", "От какой платформы, игры или API зависит продукт?", False, [
            ("Определить по идее (Recommended)", "Название платформы возьму из идеи и запроса; своё — в «Other»", {"idea.facets.platform_dependency": True}),
            ("Игра или игровой сервис", "Данные игры, аккаунт игрока", {"idea.facets.platform_dependency": True, "idea.facets.platform_kind": "game"}),
            ("Маркетплейс или соцсеть", "Каталоги, профили, публикации", {"idea.facets.platform_dependency": True, "idea.facets.platform_kind": "marketplace_social"}),
            ("Не зависит от платформы", "Своя система без чужих данных", {"idea.facets.platform_dependency": False})]),
        ("pl02", "platform", 2, "Пл: данные", "Какие данные платформы нужны? (можно несколько)", True, [
            ("О мире: справочники, каталоги (Recommended)", "Предметы, карты, события, цены", {"idea.facets.platform_data_needs": ["world"]}),
            ("О пользователе: профиль, прогресс", "Прогресс, история, инвентарь", {"idea.facets.platform_data_needs": ["user"]}),
            ("Вход через платформу", "Авторизация аккаунтом платформы", {"idea.facets.platform_data_needs": ["auth"]}),
            ("Действия от имени пользователя", "Покупки, публикации, отправка", {"idea.facets.platform_data_needs": ["actions"]})]),
        ("pl03", "platform", 3, "Пл: способ", "Как планируете получать данные платформы?", False, [
            ("Исследовать варианты (Recommended)", "Сравнить законные способы в исследовании", {"idea.facets.platform_access": "research"}),
            ("Официальный API", "Только документированный доступ", {"idea.facets.platform_access": "official"}),
            ("Открытые данные сообщества", "Вики, открытые наборы, датасеты", {"idea.facets.platform_access": "community"}),
            ("Ручной ввод пользователем", "Пользователь вносит сам", {"idea.facets.platform_access": "manual"})]),
        ("pl04", "platform", 4, "Пл: правила", "Что допустимо по правилам платформы?", False, [
            ("Только официальное (Recommended)", "Серые методы исключены: обход защиты, чтение памяти, скрейпинг против правил", {"idea.facets.platform_allowed": "official_only"}),
            ("Официальное и открытые данные", "Плюс данные сообщества с лицензией", {"idea.facets.platform_allowed": "official_and_open"}),
            ("Решить после исследования", "Сначала изучить правила", {"idea.facets.platform_allowed": "research"})]),
        ("pl05", "platform", 5, "Пл: закроют", "Что если платформа закроет доступ?", False, [
            ("Ручной ввод как запасной путь (Recommended)", "Продукт работает и без API", {"idea.facets.platform_fallback": "manual"}),
            ("Свои данные и сообщество", "Собственная база", {"idea.facets.platform_fallback": "own_data"}),
            ("Проект остановится", "Риск принимаю", {"idea.facets.platform_fallback": "stop"}),
            ("Оценить в исследовании", "Решить по итогам", {"idea.facets.platform_fallback": "research"})]),
    ]),
    "law": ("Предметная область и право", "чувствительная область (деньги, крипто, здоровье, дети, личные данные) или ИИ с личными данными", [
        ("lw01", "law", 1, "Право: юрист", "Нужна ли консультация юриста до публичного запуска?", False, [
            ("Да, до публичного запуска (Recommended)", "Разбор до выхода к людям", {"idea.facets.law_lawyer": "before_public"}),
            ("Сейчас, до разработки", "Ограничения могут менять продукт", {"idea.facets.law_lawyer": "now"}),
            ("Не нужна", "Риск принимаю", {"idea.facets.law_lawyer": "no"})]),
        ("lw02", "law", 2, "Право: ответ", "Кто отвечает за правовые вопросы?", False, [
            ("Я сам (Recommended)", "Владелец", {"idea.facets.law_owner": "owner"}),
            ("Юрист или партнёр", "Внешний специалист", {"idea.facets.law_owner": "lawyer"}),
            ("Компания", "Юрлицо владельца", {"idea.facets.law_owner": "company"})]),
        ("fn01", "law:finance", 3, "Фин: советы", "Будет ли продукт давать инвестиционные рекомендации?", False, [
            ("Нет: аналитика и обучение (Recommended)", "Информация без персональных советов", {"idea.facets.fin_advice": "no_info_only"}),
            ("Да, персональные рекомендации", "Нужны лицензия или статус", {"idea.facets.fin_advice": "personal_advice"}),
            ("Решить после разбора права", "Сначала границы допустимого", {"idea.facets.fin_advice": "research"})]),
        ("fn02", "law:finance", 4, "Фин: статус", "Как позиционировать финансовую часть?", False, [
            ("Информационно-аналитический сервис (Recommended)", "Данные и расчёты, решения — за пользователем", {"idea.facets.fin_status": "analytics"}),
            ("Обучающий сервис", "Объяснения и тренировка", {"idea.facets.fin_status": "education"}),
            ("Инструмент партнёра или брокера", "Работа под чужой лицензией", {"idea.facets.fin_status": "partner"})]),
        ("fn03", "law:finance", 5, "Фин: риски", "Как раскрывать риски пользователю?", False, [
            ("Оговорки у каждого расчёта (Recommended)", "Риски рядом с числом", {"idea.facets.fin_risk_disclosure": "per_calc"}),
            ("Общая страница рисков", "Один документ", {"idea.facets.fin_risk_disclosure": "page"}),
            ("Не нужно", "Только для себя", {"idea.facets.fin_risk_disclosure": "none"})]),
        ("cr01", "law:crypto", 6, "Кр: оборот", "Что продукт делает с криптовалютой?", False, [
            ("Только аналитика и данные (Recommended)", "Без операций со средствами", {"idea.facets.crypto_scope": "analytics"}),
            ("Кошельки и движение средств", "Анализ адресов и переводов", {"idea.facets.crypto_scope": "wallets"}),
            ("Обмен или платежи", "Операции со средствами — строгие правила", {"idea.facets.crypto_scope": "exchange"})]),
        ("cr02", "law:crypto", 7, "Кр: налоги", "Учитывать налоги и требования AML?", False, [
            ("Только предупреждение (Recommended)", "Напомнить пользователю", {"idea.facets.crypto_tax": "warning"}),
            ("Да, расчёт налогов", "Отдельная функция", {"idea.facets.crypto_tax": "calc"}),
            ("Не нужно", "Не касается продукта", {"idea.facets.crypto_tax": "none"})]),
        ("hl01", "law:health", 8, "Зд: советы", "Даёт ли продукт советы о здоровье?", False, [
            ("Нет, только учёт и напоминания (Recommended)", "Без медицинских советов", {"idea.facets.health_advice": "no"}),
            ("Общие рекомендации", "Без диагноза и лечения", {"idea.facets.health_advice": "general"}),
            ("Диагностика или лечение", "Медизделие — отдельные требования", {"idea.facets.health_advice": "medical"})]),
        ("hl02", "law:health", 9, "Зд: данные", "Хранит ли продукт медицинские данные?", False, [
            ("Нет (Recommended)", "Медицинских данных нет", {"idea.facets.health_data": "none"}),
            ("Да, на устройстве", "Локально у пользователя", {"idea.facets.health_data": "local"}),
            ("Да, на сервере", "Особые требования к хранению", {"idea.facets.health_data": "server"})]),
        ("ch01", "law:children", 10, "Дет: возраст", "Кто пользователи по возрасту?", False, [
            ("Родители, не дети (Recommended)", "Аккаунты взрослых", {"idea.facets.children_users": "parents"}),
            ("Подростки 14–17", "Нужны ограничения", {"idea.facets.children_users": "teens"}),
            ("Дети до 14", "Согласие родителей обязательно", {"idea.facets.children_users": "kids"})]),
        ("ch02", "law:children", 11, "Дет: согл.", "Как получать согласие родителей?", False, [
            ("Через аккаунт родителя (Recommended)", "Родитель управляет профилем ребёнка", {"idea.facets.children_consent": "parent_account"}),
            ("Подтверждение по почте", "Письмо родителю", {"idea.facets.children_consent": "email"}),
            ("Не нужно: данных детей нет", "Только взрослые", {"idea.facets.children_consent": "none"})]),
        ("pd01", "law:pd", 12, "ПД: состав", "Какие персональные данные обрабатываются? (можно несколько)", True, [
            ("Почта и настройки (Recommended)", "Минимум", {"idea.facets.pd_kinds": ["contacts"]}),
            ("Документы и файлы", "Загружаемые файлы", {"idea.facets.pd_kinds": ["documents"]}),
            ("Геолокация", "Местоположение", {"idea.facets.pd_kinds": ["geo"]}),
            ("Финансовые данные", "Счета, операции, портфель", {"idea.facets.pd_kinds": ["finance"]})]),
        ("pd02", "law:pd", 13, "ПД: хранение", "Где хранятся персональные данные?", False, [
            ("На устройстве пользователя (Recommended)", "Без передачи на сервер", {"idea.facets.pd_storage": "device"}),
            ("Сервер в России", "Локализация данных", {"idea.facets.pd_storage": "ru_server"}),
            ("Зарубежный облачный сервис", "Трансграничная передача", {"idea.facets.pd_storage": "foreign_cloud"})]),
    ]),
    "interface": ("Интерфейс и взаимодействие", "макеты включены", [
        ("ui01", "interface", 1, "Инт: ввод", "Основной способ взаимодействия?", False, [
            ("Мышь и тач, видимые кнопки (Recommended)", "Клавиши — только ускорение; цели нажатия ≥ 32/44 px", {"design.pointer_first": True, "idea.facets.ui_input": "pointer_touch"}),
            ("Клавиатура и команды", "Горячие клавиши и командная строка — основной путь", {"design.pointer_first": False, "idea.facets.ui_input": "keyboard"}),
            ("Голос", "Голосовые команды", {"design.pointer_first": False, "idea.facets.ui_input": "voice"}),
            ("API без интерфейса", "Интеграция вместо экранов", {"design.pointer_first": False, "idea.facets.ui_input": "api"})]),
        ("ui02", "interface", 2, "Инт: вариант", "Сколько вариантов интерфейса показать до выбора?", False, [
            ("Три направления (Recommended)", "Различаются компоновкой и метафорой, не цветом; своё число 1–7 — в «Other»", {"design.directions_count": 3}),
            ("Два", "Быстрый выбор", {"design.directions_count": 2}),
            ("Пять", "Широкий выбор", {"design.directions_count": 5}),
            ("Один, сразу делать", "Без выбора направления", {"design.directions_count": 1})]),
        ("ui03", "interface", 3, "Инт: платф.", "Какие платформы сейчас и позже?", False, [
            ("Веб сейчас, мобильное позже (Recommended)", "Адаптив и задел: API-first, PWA", {"idea.facets.ui_platforms": "web_now_mobile_later", "product.future_forms": ["mobile"]}),
            ("Только веб", "Без мобильной версии", {"idea.facets.ui_platforms": "web_only"}),
            ("Веб и мобильное сразу", "Две формы с первого выпуска", {"idea.facets.ui_platforms": "both_now"}),
            ("Мобильное первым", "Телефон — главный экран", {"idea.facets.ui_platforms": "mobile_first"})]),
        ("ui04", "interface", 4, "Инт: режимы", "Один интерфейс или несколько режимов?", False, [
            ("Один интерфейс (Recommended)", "Одна компоновка для всех", {"design.modes": []}),
            ("Режимы под разные навыки", "Новичок, опытный, визуальный — общая система и данные", {"design.modes": ["beginner", "pro"]}),
            ("Решить после показа вариантов", "Сначала посмотреть направления", {"design.modes_decide_later": True})]),
        ("ui05", "interface", 5, "Инт: плотн.", "Какая плотность интерфейса?", False, [
            ("Карточки и воздух (Recommended)", "Спокойная компоновка", {"idea.facets.ui_density": "cards"}),
            ("Плотные панели", "Много данных на экране", {"idea.facets.ui_density": "dense"}),
            ("Мастер по шагам", "Ведёт пользователя", {"idea.facets.ui_density": "wizard"}),
            ("Иммерсивная визуализация", "Графика в центре", {"idea.facets.ui_density": "immersive"})]),
        ("ui06", "interface", 6, "Инт: графики", "Что важно в визуализации? (можно несколько)", True, [
            ("Обычные графики (Recommended)", "Линии, столбцы, легенды", {"idea.facets.ui_viz": ["charts"]}),
            ("3D-визуализация", "Объёмные сцены", {"idea.facets.ui_viz": ["3d"]}),
            ("Таблицы и текстовые альтернативы", "Доступность графиков", {"idea.facets.ui_viz": ["tables"]}),
            ("Карты", "Геоданные или игровые карты", {"idea.facets.ui_viz": ["maps"]})]),
        ("ui07", "interface", 7, "Инт: подсказ", "Что нужно в странице концепции? (можно несколько)", True, [
            ("Подсказки у элементов макетов (Recommended)", "«Что это и для чего» по наведению", {"idea.facets.doc_features": ["hotspots"]}),
            ("Поиск по документу", "Часть слова, фраза, несколько слов", {"idea.facets.doc_features": ["search"]}),
            ("Увеличение графиков и макетов", "Просмотрщик с деталями", {"idea.facets.doc_features": ["zoom"]})]),
        ("ui08", "interface", 8, "Инт: доступн", "Какие требования доступности?", False, [
            ("Базовые: контраст, клавиатура (Recommended)", "Плюс уменьшение анимации", {"idea.facets.ui_a11y": "basic"}),
            ("Полные WCAG 2.2 AA", "Экранный диктор, цели 44 px", {"idea.facets.ui_a11y": "wcag_aa"}),
            ("Не важно", "Только для себя", {"idea.facets.ui_a11y": "none"})]),
        ("ui09", "interface", 9, "Инт: языки", "Какие языки интерфейса?", False, [
            ("Как рынки (Recommended)", "По ответу «Рынки»", {"idea.facets.ui_languages": "markets"}),
            ("Только русский", "Один язык", {"idea.facets.ui_languages": "ru"}),
            ("Русский и английский", "Два языка", {"idea.facets.ui_languages": "ru_en"})]),
    ]),
    "prototype": ("Прототип и передача в разработку", "всегда (объём — по режиму опроса)", [
        ("pr01", "prototype", 1, "Прот: нужен", "Нужен ли рабочий прототип, а не только макеты?", False, [
            ("Не нужен, только макеты (Recommended)", "Статичные макеты ключевых экранов", {"idea.facets.prototype_needed": False, "idea.facets.prototype_scope": "no"}),
            ("Ядро расчётов с тестами", "Логика и тесты воспроизведения чисел макетов", {"idea.facets.prototype_needed": True, "idea.facets.prototype_scope": "core"}),
            ("Ядро и один рабочий экран", "Проверить ага-момент вживую", {"idea.facets.prototype_needed": True, "idea.facets.prototype_scope": "one_screen"}),
            ("Ядро, оболочка, все режимы", "Полный кликабельный прототип", {"idea.facets.prototype_needed": True, "idea.facets.prototype_scope": "all_modes"})]),
        ("pr02", "prototype", 2, "Прот: стек", "Какой стек для прототипа и боевой версии?", False, [
            ("Подобрать в концепции (Recommended)", "Стек — в разделе «Технологическое решение»", {"idea.facets.stack": "auto"}),
            ("Статический HTML, CSS, JS", "Без сборки, офлайн по file://", {"idea.facets.stack": "static_html"}),
            ("TypeScript и Node", "Веб-стек", {"idea.facets.stack": "ts_node"}),
            ("Python", "Бэкенд и расчёты на Python", {"idea.facets.stack": "python"})]),
        ("pr03", "prototype", 3, "Прот: смотрю", "Как будете смотреть результат?", False, [
            ("Офлайн-файл в браузере (Recommended)", "Открыть index.html без сервера", {"idea.facets.view": "file"}),
            ("Локальный сервер", "Нужно для локальной модели и API", {"idea.facets.view": "local_server"}),
            ("Публикация по ссылке", "Хостинг или артефакт", {"idea.facets.view": "hosted"})]),
        ("pr04", "prototype", 4, "Прот: задачи", "Что добавить в файл задач? (можно несколько)", True, [
            ("Критерии приёмки и тесты (Recommended)", "К каждой задаче", {"idea.facets.handoff_extras": ["acceptance_tests"]}),
            ("Ссылки на прототип", "Код и тесты прототипа", {"idea.facets.handoff_extras": ["prototype_links"]}),
            ("Привязка к спецификациям", "Задача → спека", {"idea.facets.handoff_extras": ["spec_links"]})]),
    ]),
    "owner": ("Контекст владельца: что уже есть", "всегда (объём — по режиму опроса)", [
        ("ow01", "owner", 1, "Своё: репо", "Есть ли ваши проекты или репозитории как референс?", False, [
            ("Нет (Recommended)", "Референсов нет", {"idea.facets.owner_repos_known": False}),
            ("Есть, укажу пути", "Пути или ссылки — в «Other»", {"idea.facets.owner_repos_known": True}),
            ("Есть похожий прошлый проект", "Опишите в «Other»", {"idea.facets.owner_repos_known": True})]),
        ("ow02", "owner", 2, "Своё: данные", "Есть ли свои данные или замеры для входа?", False, [
            ("Нет (Recommended)", "Начинаем с открытых данных", {"idea.facets.owner_data": False}),
            ("Есть таблицы или выгрузки", "Пути — в «Other»", {"idea.facets.owner_data": True}),
            ("Есть замеры или бенчмарки", "Пути — в «Other»", {"idea.facets.owner_data": True})]),
        ("ow03", "owner", 3, "Своё: инстр.", "Какие ограничения по инструментам? (можно несколько)", True, [
            ("Нет ограничений (Recommended)", "Любые инструменты", {"idea.facets.tool_limits": []}),
            ("Только стандартная библиотека", "Без pip и npm install", {"idea.facets.tool_limits": ["stdlib_only"]}),
            ("Только бесплатные сервисы", "Без платных подписок", {"idea.facets.tool_limits": ["free_only"]}),
            ("Работа офлайн", "Без сети", {"idea.facets.tool_limits": ["offline"]})]),
    ]),
    "payments": ("Оплата", "публичный продукт с платной моделью", [
        ("pay01", "payments", 1, "Оплата", "Как будете принимать оплату?", False, [
            ("Платёжный сервис на сайте (Recommended)", "Прямые платежи: эквайринг, самозанятость", {"strategy.payment_channel": "direct"}),
            ("Магазин приложений", "Комиссия магазина 15–30 %", {"strategy.payment_channel": "store"}),
            ("Донаты и подписки поддержки", "Добровольные платежи", {"strategy.payment_channel": "donations"}),
            ("Пока не принимаю", "Оплата позже", {"strategy.payment_channel": "none"})]),
    ]),
}
BLOCK_ORDER = ["platform", "data", "ai", "law", "admin", "interface", "prototype", "owner", "payments"]
EXCLUSIVE = {"c38": 0, "c09": 0, "ow03": 0}   # мультивыбор: вариант с этим индексом исключает остальные (SM 3.4)

# сколько вопросов блока задаётся: режим опроса → число (или функция от конфигурации)
BLOCK_SIZE = {
    "fast": {"platform": 3, "data": 2, "admin": 2, "interface": 2, "prototype": 1, "owner": 1, "payments": 1},
    "standard": {"platform": 5, "data": 4, "admin": 6, "interface": 4, "prototype": 2, "owner": 2, "payments": 1},
    "deep": {"platform": 5, "data": 7, "admin": 9, "interface": 9, "prototype": 4, "owner": 3, "payments": 1},
}
AI_SIZE = {"fast": {"helper": 2, "core": 4}, "standard": {"helper": 3, "core": 8}, "deep": {"helper": 13, "core": 13}}

# быстрый режим: подтверждение таблицы по теме (header ≤ 12, уникален)
THEME_CONFIRM = {"problem": "Т1·Проблема", "audience": "Т2·Аудитория", "value": "Т3·Ценность", "product": "Т4·Продукт",
                 "market": "Т5·Рынок", "money": "Т6·Деньги", "team": "Т7·Команда", "design": "Т8·Дизайн", "risks": "Т9·Риски"}
CONFIRM_HEADER = "Из запроса"
CARD_DEFAULT_RE = re.compile(r"^\s*(?:по\s+умолчанию|как\s+рекомендовано|рекомендуем\w*|default)\b.*(?:карточ|пачк|вс[еёя]\w*|card|all)",
                             re.I | re.U)
ONE_DEFAULT_RE = re.compile(r"^\s*(?:по\s+умолчанию|как\s+рекомендовано|default)\s*[.!]?\s*$", re.I | re.U)


def all_block_questions():
    for key in BLOCK_ORDER:
        for q in BLOCKS[key][2]:
            yield q


def lookup(bank):
    """Все вопросы режима идеи по ключу (id, header, текст вопроса) → (вопрос, источник: bank|personal|intro|block)."""
    out = {}
    for src, qs in (("bank", bank), ("personal", PERSONAL.values()), ("intro", INTRO), ("block", list(all_block_questions()))):
        for q in qs:
            for k in (q[0], q[3], q[4]):
                out.setdefault(k, (q, src))
    return out


def audience_of(value):
    v = str(value or "public").strip().lower()
    return v if v in AUDIENCE else "public"


def adapted_bank(bank, audience):
    """Банк для аудитории: в личном режиме вопросы про рынок, каналы и деньги заменены вопросами о себе (PERSONAL)."""
    if audience_of(audience) not in PERSONAL_AUDIENCES:
        return list(bank)
    return [PERSONAL.get(q[0], q) for q in bank]


def replaced_ids(audience):
    return set(PERSONAL) if audience_of(audience) in PERSONAL_AUDIENCES else set()


# ---------------------------------------------------------------- маскировка
SECRET_RES = [re.compile(p) for p in (r"\bsk-[A-Za-z0-9_-]{16,}", r"\bgh[pousr]_[A-Za-z0-9]{20,}", r"\bAKIA[0-9A-Z]{16}\b",
                                     r"\bxox[abpr]-[A-Za-z0-9-]{10,}", r"\b[A-Za-z0-9_-]{40,}\b")]
HOME_RE = re.compile(r"(?:/Users|/home)/[^/\s]+")


def mask(text):
    """Секреты → «[скрыто]», домашняя папка → «~» (в run-config не должно быть ключей и абсолютных путей машины)."""
    s = str(text or "")
    for rx in SECRET_RES:
        s = rx.sub("[скрыто]", s)
    return HOME_RE.sub("~", s)


# ---------------------------------------------------------------- формы продукта (FB-024)
FORM_RULES = [  # (регэксп, форма) — порядок не важен: собираются все совпадения
    (r"мобильн\w*\s+верси\w*\s+(?:сайта|веба|веб\b|web)|верси\w*\s+(?:сайта|веба)\s+для\s+(?:телефон|мобильн)|адаптив\w*|\bpwa\b|"
     r"удобн\w*\s+мобильн\w*\s+верси", "mobile_web"),
    (r"мобильн\w*\s+(?:верси\w*\s*/\s*)?приложени|\bios\b|android|андроид|айфон|iphone|смартфон\w*\s+приложени|"
     r"нативн\w*\s+приложени|приложени\w*\s+(?:для|под)\s+(?:телефон|смартфон|ios|android)", "mobile"),
    (r"мобильн\w*\s+верси\w*(?!\s*/\s*приложени)(?!\s+(?:сайта|веба|веб\b|web))", "mobile_web"),
    (r"\bбот\w*|telegram|телеграм|мессенджер|whatsapp|mini ?app|мини-приложен|\bvk\b|вконтакте", "bot"),
    (r"расширени\w*\s+(?:для\s+)?браузер|browser extension|\bрасширени", "extension"),
    (r"десктоп|desktop|программ\w*\s+для\s+компьютер|windows|macos|linux", "desktop"),
    (r"\bapi\b|\bcli\b|\bsdk\b|библиотек\w*\s+для|плагин\w*\s+для\s+(?:ide|разработ)", "devtool"),
    (r"веб-?приложени|веб-?сервис|\bсайт\w*|\bвеб\b|\bweb\b|браузер|\bsaas\b|онлайн-?сервис", "web"),
]
FUTURE_RE = re.compile(r"(?:в\s+будущем|позже|потом|задел\w*|на\s+будущее|later|future|со\s+временем|возможн\w*\s+(?:позже|в\s+будущем))", re.I)
FORM_TYPE = {"web": "saas", "mobile_web": "saas", "mobile": "mobile", "bot": "bot", "desktop": "desktop", "extension": "desktop",
             "devtool": "devtool"}
FORM_LABELS = {"web": "веб-приложение", "mobile_web": "мобильная версия веба (адаптив, PWA)", "mobile": "мобильное приложение",
               "bot": "бот в мессенджере", "desktop": "программа для компьютера", "extension": "расширение браузера",
               "devtool": "API, CLI или SDK"}


def parse_forms(text):
    """Свободный ответ о форме → {"forms": [...], "future": [...], "main": форма|None, "type": product.type|None,
    "ambiguous": bool, "alternatives": bool}. «Мобильная версия веба», «адаптив», «PWA» — это веб (mobile_web);
    формы рядом со словами «позже», «задел», «в будущем» — future; «A или B» — выбирается более дешёвая форма (веб)."""
    low = str(text or "").lower().replace("ё", "е")
    found, future = [], []
    for part in re.split(r"[;,.]|\s+(?:а\s+также|плюс|\+)\s+", low):
        is_future = bool(FUTURE_RE.search(part))
        for rx, form in FORM_RULES:
            for m in re.finditer(rx, part):
                if form == "web" and re.search(r"мобильн\w*\s+верси\w*\s+(?:сайта|веба|веб\b)|версии\s+веба", part[max(0, m.start() - 25):m.end() + 5]):
                    continue                                   # «мобильная версия веба» — это mobile_web, а не отдельный web
                tgt = future if is_future and not re.search(r"сейчас|сразу|now", part) else found
                if form not in tgt:
                    tgt.append(form)
    if "mobile_web" in found and "web" not in found and "mobile" not in found:
        found.insert(0, "web")
    alt = bool(re.search(r"мобильн\w*\s+приложени\w*\s+или\s+(?:\w+\s+){0,2}(?:мобильн\w*\s+)?верси|приложени\w*\s+или\s+(?:\w+\s+){0,2}адаптив", low))
    if alt and "mobile" in found and "mobile_web" in found:
        found.remove("mobile")                                 # «мобильное приложение или мобильная версия веба» → веб-путь
        if "mobile" not in future:
            future.append("mobile")
    future = [f for f in future if f not in found]
    order = ["web", "mobile_web", "mobile", "bot", "desktop", "extension", "devtool"]
    found.sort(key=order.index)
    future.sort(key=order.index)
    main = None
    for f in ("web", "mobile", "bot", "desktop", "extension", "devtool", "mobile_web"):
        if f in found:
            main = f
            break
    kinds = {FORM_TYPE.get(f) for f in found}
    ambiguous = len(kinds - {None}) >= 2
    return {"forms": found, "future": future, "main": main, "type": FORM_TYPE.get(main) if main else None,
            "ambiguous": ambiguous, "alternatives": alt}


# ---------------------------------------------------------------- ссылки и материалы владельца (FB-002)
URL_RE = re.compile(r"https?://[^\s,;«»<>\"'()]+", re.I)
BARE_DOMAIN_RE = re.compile(r"(?<![@/\w.-])((?:[a-z0-9-]+\.)+(?:app|com|net|org|io|gg|ru|рф|dev|ai|co|me|info|pro|wiki|tv|xyz|games?))\b(?!\.\w)", re.I)
PATH_RE = re.compile(r"(?<![\w/])(?:~|/Users/[^/\s]+|/home/[^/\s]+)(?:/[\w.\-]+)+")
COMPETITOR_CTX = re.compile(r"конкурент|аналог|ориентир|эталон|лучш\w+\s+трекер|лучш\w+|как\s+у\b|пример|референс|похож|vs\b|альтернатив", re.I)
PLATFORM_CTX = re.compile(r"официальн\w*|сайт\s+игры|сайт\s+платформ|разработчик\w*\s+игры|издател|документаци\w*\s+api|developer", re.I)
BASE_CTX = re.compile(r"основ\w*\s+(?:для\s+)?вопрос|как\s+основ|в\s+качестве\s+основ|за\s+основу\s+вопрос|основа\s+вопрос", re.I)
FOLLOW_CTX = re.compile(r"(?<!не\s)следуй|(?<!не\s)следовать|взять\s+целиком|по\s+этому\s+(?:плану|исследованию)|за\s+основу(?!\s+вопрос)", re.I)
NOT_FOLLOW_CTX = re.compile(r"не\s+следуй|не\s+следовать|целиком\s+не|не\s+целиком", re.I)


def _url_kind(url, left, right=""):
    low = url.lower()
    if re.search(r"claude\.ai/.*artifact|claude\.site", low):
        return "artifact", "artifact-read"
    if re.search(r"github\.com|gitlab\.com|bitbucket\.org", low):
        return "repo", "web-fetch"
    if re.search(r"docs\.google|drive\.google|notion\.(?:so|site)|dropbox|\.pdf\b|\.docx?\b|\.md\b|\.xlsx?\b|figma\.com", low):
        return "document", "web-fetch"
    for ctx in (left, right):                                   # сначала текст ПЕРЕД ссылкой, потом после неё
        if PLATFORM_CTX.search(ctx) and not COMPETITOR_CTX.search(ctx):
            return "platform_site", "web-fetch"
        if COMPETITOR_CTX.search(ctx):
            return "competitor", "web-fetch"
        if PLATFORM_CTX.search(ctx):
            return "platform_site", "web-fetch"
    return "other", "web-fetch"


def _ctx_parts(text, start, end, before=90, after=60):
    left = text[max(0, start - before):start]
    left = re.split(r"(?:https?://\S+|(?:[a-z0-9-]+\.)+[a-z]{2,}\b)", left)[-1]
    if re.search(r"[.!?\n]\s", left[-60:]):
        left = re.split(r"[.!?\n]\s", left)[-1]
    right = text[end:end + after]
    right = re.split(r"https?://|[;,\n]|\.\s", right)[0]
    return left.strip(), right.strip()


def _ctx(text, start, end, before=90, after=60):
    left, right = _ctx_parts(text, start, end, before, after)
    return (left + " … " + right).strip()


def classify_urls(text):
    """Ссылки и локальные пути из текста запроса → [{url|path, kind, role, status, tool, note, domain}].
    kind: platform_site | competitor | document | artifact | repo | other; role: base | follow | ref; status: not_attempted
    (шаг C0.6 — прочитать каждую и сменить на read | blocked). Домены без схемы («metaforge.app») — тоже ссылки."""
    text = str(text or "")
    out, seen = [], set()
    spans = [(m.start(), m.end(), m.group(0).rstrip(".)")) for m in URL_RE.finditer(text)]
    covered = [(s, e) for s, e, _ in spans]
    for m in BARE_DOMAIN_RE.finditer(text):
        if any(s <= m.start() < e for s, e in covered):
            continue
        spans.append((m.start(), m.end(), "https://" + m.group(1).lower()))
    for s, e, url in sorted(spans):
        key = url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        ctx = _ctx(text, s, e)
        kind, tool = _url_kind(url, *_ctx_parts(text, s, e))
        role = "base" if BASE_CTX.search(ctx) else "follow" if (FOLLOW_CTX.search(ctx) and not NOT_FOLLOW_CTX.search(ctx)) else "ref"
        dom = re.sub(r"^https?://(?:www\.)?", "", url).split("/")[0].lower()
        out.append({"url": url, "kind": kind, "role": role, "status": "not_attempted", "tool": tool,
                    "note": mask(re.sub(r"\s+", " ", ctx))[:160], "domain": dom, "source": "request"})
    for m in PATH_RE.finditer(text):
        p = mask(m.group(0))
        if p.lower() in seen:
            continue
        seen.add(p.lower())
        ctx = _ctx(text, m.start(), m.end())
        role = "base" if BASE_CTX.search(ctx) else "ref"
        out.append({"path": p, "kind": "repo" if not re.search(r"\.\w{2,4}$", p) else "document", "role": role, "status": "not_attempted",
                    "tool": "read", "note": mask(re.sub(r"\s+", " ", ctx))[:160], "source": "request"})
    return out


# ---------------------------------------------------------------- вопросы запроса (FB-001)
RQ_RESEARCH = re.compile(r"\?|^\s*(?:как|можно\s+ли|откуда|сколько|какие|какой|какая|каким|есть\s+ли|нужно\s+ли|насколько|почему|"
                         r"зачем|кто|где|чем)\b|изуч|исследу|найд|провер|сравн|оцен|выясн|узна|проанализ|разбер|посмотри|"
                         r"конкурент|аналог|выгодн|окуп|спрос|право|закон|лиценз|api\b|интеграц|подключ|синхрониз|источник",
                         re.I | re.U)
RQ_FORMAT = re.compile(r"схем|график|диаграм|кликабельн|интерактивн\w*\s+(?:схем|график|диаграм|страниц|отчёт|отчет)|\bpdf\b|xlsx|"
                       r"pptx|презентац|страниц\w*\s+(?:концепц|стратег)|формат\w*\s+(?:результат|отчёт|отчет)|"
                       r"визуализац\w*\s+(?:концепц|стратег|данных\s+отчёт)", re.I | re.U)
RQ_DELIVERABLE = re.compile(r"стратеги|архитектур|бэк|бек-?энд|backend|план\b|дорожн|макет|дизайн|интерфейс|прототип|\bmvp\b|"
                            r"спецификац|предлож|продума|разработа|спроектир|составь|опиши|подготов|нарисуй|"
                            r"функци|трекер|карт[аы]\b|статистик|прогресс", re.I | re.U)
RQ_LEAD = re.compile(r"^\s*(?:а\s+также|также|и\s+ещё|ещё|плюс|нужно|надо|хочу|интересует|важно|прошу|пожалуйста|давай|"
                     r"а\s+ещё|кроме\s+того)\s*[:,—-]?\s*", re.I | re.U)


def _rq_kind(t):
    if RQ_FORMAT.search(t) and not re.search(r"конкурент|можно\s+ли|откуда", t, re.I):
        return "format"
    if re.search(r"\?", t) or re.search(r"^\s*(?:как|можно\s+ли|откуда|сколько|есть\s+ли|насколько)\b", t, re.I):
        return "research"
    if RQ_DELIVERABLE.search(t) and not re.search(r"конкурент|изуч|исследу|выгодн|сравн|оцен", t, re.I):
        return "deliverable"
    return "research"


def request_questions(text, pitch="", limit=20):
    """Текст запроса → [{id, text, kind, source}] (FB-001). Предложения-вопросы, поручения («изучи…», «как…»,
    «можно ли…») и перечисления после двоеточия становятся отдельными пунктами; первая фраза, совпадающая с идеей, —
    не вопрос. kind: research (исследовать), deliverable (что сделать в концепции), format (как оформить)."""
    raw = URL_RE.sub(" ", str(text or ""))
    raw = BARE_DOMAIN_RE.sub(lambda m: m.group(0), raw)
    raw = re.sub(r"^\s*(?:!concept\b|concept\s*:|!идея\b|идея\s*:)\s*", "", raw, flags=re.I)
    pitch_low = re.sub(r"\W+", " ", str(pitch or "").lower()).strip()
    items = []
    for sent in re.split(r"(?<=[.!?])\s+|\n+|;\s*", raw):
        s = sent.strip(" .;—-–")
        if len(s) < 6:
            continue
        low = re.sub(r"\W+", " ", s.lower()).strip()
        if pitch_low and (low in pitch_low or pitch_low.startswith(low[:60])) and "?" not in s:
            continue
        m = re.match(r"^([^:]{3,80}):\s*(.+)$", s)
        if m and not re.search(r"https?$", m.group(1)):
            head, rest = m.group(1).strip(), m.group(2).strip()
            if re.search(r"^(?:ссылк|материал|источник)", head, re.I):
                continue
            if RQ_LEAD.fullmatch(head + ":") or re.fullmatch(r"(?:нужно|надо|хочу|важно|интересует|задача|цель)", head, re.I):
                head = "Что сделать"
            parts = [p.strip(" .") for p in re.split(r",\s*|\s+и\s+(?=(?:как|можно|откуда|где|сколько)\b)", rest) if p.strip(" .")]
            if len(parts) >= 3 and all(len(p.split()) <= 8 for p in parts):
                items.append("%s: %s" % (head, ", ".join(parts)))
                continue
        s = RQ_LEAD.sub("", s)
        for part in re.split(r"\s*(?<=\?)\s*|\s+(?:а\s+также|и\s+ещё)\s+", s):
            p = part.strip(" .;,")
            if len(p.split()) >= 2 and (RQ_RESEARCH.search(p) or RQ_DELIVERABLE.search(p) or RQ_FORMAT.search(p)):
                items.append(p)
    out, seen = [], set()
    for t in items:
        key = re.sub(r"\W+", " ", t.lower()).strip()[:80]
        if key in seen:
            continue
        seen.add(key)
        t = mask(t[:1].upper() + t[1:])
        out.append({"id": "RQ%02d" % (len(out) + 1), "text": t[:300], "kind": _rq_kind(t), "source": "request"})
        if len(out) >= limit:
            break
    return out


def normalize_request_questions(items):
    """Список от оркестратора (строки или {text, kind}) → [{id, text, kind, source: llm}]."""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            t = str(it.get("text") or it.get("question") or "").strip()
            k = it.get("kind") if it.get("kind") in ("research", "deliverable", "format") else _rq_kind(t)
        else:
            t, k = str(it).strip(), None
            k = _rq_kind(t)
        if t:
            out.append({"id": "RQ%02d" % (len(out) + 1), "text": mask(t)[:300], "kind": k, "source": "llm"})
    return out


# ---------------------------------------------------------------- предзаполнение из текста (FB-055, SM 3.1)
PLATFORM_WORDS = re.compile(r"\bигр[аыуеой]\w*|\bgame\b|steam|epic\s+games|playstation|xbox|nintendo|roblox|minecraft|dota|"
                            r"counter-?strike|\bcs2\b|valorant|fortnite|\bapi\s+(?:игры|платформ|сервиса)|маркетплейс|ozon|wildberries|"
                            r"авито|avito|amazon|ebay|youtube|twitch|discord|tiktok|instagram|shopify|notion\s+api|jira|github\s+api|"
                            r"telegram\s+api|vk\s+api", re.I | re.U)
DATA_WORDS = re.compile(r"\bapi\b|данн\w+\s+(?:бирж|рынк|игр|платформ)|бирж\w*|котировк|источник\w*\s+данных|интеграц|парс\w*|"
                        r"импорт|синхрониз|on-?chain|блокчейн|новостн\w*\s+канал|выгрузк|steam", re.I | re.U)
AI_WORDS = re.compile(r"\bllm\b|\bии\b|\bai\b|нейросет|\bgpt\b|ollama|lm\s*studio|llama|искусственн\w+\s+интеллект|машинн\w+\s+обучен|"
                      r"\bml\b|языков\w+\s+модел|локальн\w+\s+модел|chatgpt|claude|gemini", re.I | re.U)
AI_CORE = re.compile(r"(?:с\s+помощью|на\s+основе|через|силами)\s+(?:\w+\s+){0,2}(?:llm|ии|ai|нейросет|модел|gpt|ollama)|"
                     r"ии[- ]анализ|ai[- ]анализ|ии\s*[—-]\s*ядро|анализ\w*\s+(?:\w+\s+){0,3}(?:llm|ии|нейросет)", re.I | re.U)
FIN_WORDS = re.compile(r"бирж|акци[ия]|фьючерс|облигац|инвест|трейд|брокер|котировк|портфел|криптов|крипто|биткоин|bitcoin|"
                       r"кошел[её]к|банк|кредит|платеж|платёж", re.I | re.U)
CRYPTO_WORDS = re.compile(r"крипт|биткоин|bitcoin|ethereum|on-?chain|блокчейн|кошел[её]к\w*\s+(?:крипт|адрес)|defi|nft|токен\w*\s+(?:сет|бирж)", re.I | re.U)
HEALTH_WORDS = re.compile(r"здоров|медиц|врач|лекарств|диагноз|симптом|психотерап|психолог|фитнес|пульс|давлени", re.I | re.U)
CHILD_WORDS = re.compile(r"\bдет(?:и|ей|ям|ский|ская|ское)\b|ребён|ребен|школьн|подрост|несовершеннолет", re.I | re.U)
PERSONAL_WORDS = re.compile(r"(?:для\s+себя|для\s+личного|личн\w+\s+(?:использ|инструмент|нужд)|только\s+для\s+меня|сам\s+буду\s+пользоваться)", re.I | re.U)
CIRCLE_WORDS = re.compile(r"для\s+(?:семьи|друзей|коллег|своей\s+команды|узкого\s+круга)", re.I | re.U)
THEN_PUBLIC = re.compile(r"сначала\s+для\s+себя.{0,60}(?:потом|позже|затем).{0,40}(?:публич|всем|наружу|людям|пользовател)", re.I | re.U)


def _quote(text, m, width=70):
    s = max(0, m.start() - 20)
    sp = text.rfind(" ", 0, m.start())
    s = sp + 1 if sp >= s else s
    e = min(len(text), m.end() + 30)
    sp = text.find(" ", m.end() + 15)
    e = sp if 0 < sp < e else e
    q = re.sub(r"\s+", " ", text[s:e]).strip(" ,;:—-")
    q = re.sub(r"^(?:!concept|concept:|!идея|идея:)\s*", "", q, flags=re.I)
    return mask(q[:width] + ("…" if len(q) > width else ""))


def _put(out, qid, answer, conf, text, m, why=""):
    if qid in out and out[qid]["confidence"] >= conf:
        return
    out[qid] = {"answer": answer, "confidence": round(conf, 2), "quote": _quote(text, m) if m is not None else "", "source": "request"}
    if why:
        out[qid]["why"] = why


def platform_name(text):
    """Название внешней платформы из текста: «для игры ARC Raiders» → «ARC Raiders»; Steam, маркетплейсы — по словарю."""
    t = str(text or "")
    m = re.search(r"(?:для|по|в|от)\s+игр\w*\s+«?([A-ZА-ЯЁ0-9][\w'’:-]*(?:\s+[A-ZА-ЯЁ0-9][\w'’-]*){0,3})", t)
    if m:
        return m.group(1).strip(" «»:")
    m = re.search(r"\b(Steam|Ozon|Wildberries|Avito|Авито|YouTube|Twitch|Discord|Roblox|Minecraft|Dota\s*2|Telegram|Shopify)\b", t)
    return m.group(1) if m else ""


def prefill_from_text(text, audience_known=False):
    """Эвристика: свободный текст идеи/запроса → {id вопроса: {answer, confidence 0..1, quote, source: request}}.
    answer — label варианта (с «(Recommended)» или без) или свой текст (для «Other»). id — вопросы банка (c..),
    карточки «Начало» (i01) и блоков (pl.., ai.., ui.., da..). Уверенность ≥ 0,8 — вынести на подтверждение одной
    карточкой (FB-055); ниже — только подсказка (вопрос остаётся)."""
    t_full = str(text or "")
    t = re.sub(r"^\s*(?:!concept\b|concept\s*:|!идея\b|идея\s*:)\s*", "", t_full, flags=re.I)
    t = URL_RE.sub(lambda m: " " * len(m.group(0)), t)          # ссылки (claude.ai, домены) — не сигналы ИИ, формы и т. п.
    low = t.lower().replace("ё", "е")
    out = {}
    # форма (c16) и устройства (c19)
    first = re.split(r"(?<=[.!?])\s+|\n", t.strip(), maxsplit=1)[0]
    fp = parse_forms(first)                                   # форма — по первой фразе: «API» в описании функций — не форма
    m = re.search(r"веб-?сервис|веб-?приложени|сайт\w*(?:/\w+)?|мобильн\w+\s+приложени|\bбот\w*|расширени\w+|десктоп\w*|\bpwa\b", low)
    if fp["main"]:
        if len(fp["forms"]) > 1 or fp["future"]:
            ans = ", ".join(FORM_LABELS[f] for f in fp["forms"]) + ("; позже: " + ", ".join(FORM_LABELS[f] for f in fp["future"]) if fp["future"] else "")
            _put(out, "c16", ans, 0.85 if not fp["ambiguous"] else 0.6, t, m)
        else:
            label = {"saas": "Веб-приложение (Recommended)", "mobile": "Мобильное приложение", "bot": "Бот в мессенджере",
                     "desktop": "Расширение или десктоп", "devtool": "Веб-приложение (Recommended)"}.get(fp["type"])
            if label:
                _put(out, "c16", label, 0.85 if fp["type"] != "devtool" else 0.5, t, m)
    m = re.search(r"адаптивн\w*", low)
    if m:
        _put(out, "c19", "Оба одинаково", 0.7, t, m)
    m = re.search(r"десктоп-?first|для\s+компьютер|на\s+компьютер|desktop-first", low)
    if m:
        _put(out, "c19", "Компьютер", 0.85, t, m)
    m = re.search(r"mobile-first|в\s+первую\s+очередь\s+(?:на\s+)?телефон|с\s+телефона", low)
    if m:
        _put(out, "c19", "Телефон в первую очередь (Recommended)", 0.85, t, m)
    # рынки (c07)
    ru = re.search(r"российск\w*|по-?русски|на\s+русском|русскоязычн\w*|\bрф\b|россии|московск\w+\s+бирж|мосбирж|\bснг\b|рунет", low)
    en = re.search(r"зарубежн\w*|международн\w*|глобальн\w*|англоязычн\w*|на\s+английском|мировой|\bсша\b|европ\w*", low)
    if ru and en:
        _put(out, "c07", "RU + EN", 0.85, t, ru)
    elif ru:
        _put(out, "c07", "Русскоязычный рынок (Recommended)", 0.8, t, ru)
    elif en:
        _put(out, "c07", "Англоязычный, глобально", 0.8, t, en)
    # ИИ (c21) и блок ИИ
    m = re.search(r"без\s+(?:ии|ai|нейросет)", low)
    if m:
        _put(out, "c21", "Без ИИ", 0.9, t, m)
    else:
        mc = AI_CORE.search(low)
        ma = AI_WORDS.search(low)
        if mc:
            _put(out, "c21", "ИИ — ядро продукта", 0.85, t, mc)
        elif ma:
            _put(out, "c21", "Только если упростит (Recommended)", 0.6, t, ma)
        m = re.search(r"ollama|lm\s*studio|llama\.cpp|локальн\w+\s+(?:llm|модел|ии)", low)
        if m:
            _put(out, "ai02", "Локально, облако позже (Recommended)", 0.85, t, m)
        else:
            m = re.search(r"openai|chatgpt|claude|gemini|облачн\w+\s+(?:api|модел)", low)
            if m:
                _put(out, "ai02", "Облачный API", 0.8, t, m)
    # чувствительные области (c38) и данные (c20)
    areas = []
    for rx, label in ((FIN_WORDS, "Деньги и платежи"), (HEALTH_WORDS, "Здоровье или психика"), (CHILD_WORDS, "Дети или персональные данные")):
        mm = rx.search(low)
        if mm and not (label == "Деньги и платежи" and re.fullmatch(r"платн\w*", mm.group(0))):
            areas.append((label, mm))
    if areas:
        _put(out, "c38", [a for a, _ in areas], 0.85, t, areas[0][1])
    m = re.search(r"кошел[её]к|личн\w+\s+данн|паспорт|документ\w*\s+пользоват|переписк|портфел\w*\s+пользоват", low)
    if m:
        _put(out, "c20", "Личные данные и файлы", 0.75, t, m)
    # аудитория (c06), личный режим (i01)
    m = re.search(r"\bb2b\b|для\s+компаний|для\s+бизнеса|корпоратив", low)
    if m:
        _put(out, "c06", "Компании и команды (B2B)", 0.85, t, m)
    else:
        m = re.search(r"малого\s+бизнеса|самозанят|фрилансер|мастер\w*\s+(?:маникюр|ремонт)", low)
        if m:
            _put(out, "c06", "Малый бизнес и фрилансеры", 0.85, t, m)
        else:
            m = re.search(r"для\s+разработчик|для\s+программист|devops", low)
            if m:
                _put(out, "c06", "Разработчики", 0.85, t, m)
            else:
                m = re.search(r"игрок\w*|трейдер\w*|инвестор\w*|родител\w*|студент\w*|для\s+людей|покупател\w*|туристов|соседей", low)
                if m:
                    _put(out, "c06", "Частные лица (B2C) (Recommended)", 0.8, t, m)
    if not audience_known:
        m = THEN_PUBLIC.search(low)
        if m:
            _put(out, "i01", "Сначала для себя, потом публично", 0.85, t, m)
        else:
            m = PERSONAL_WORDS.search(low)
            if m:
                _put(out, "i01", "Только для меня", 0.85, t, m)
            else:
                m = CIRCLE_WORDS.search(low)
                if m:
                    _put(out, "i01", "Для меня и узкого круга", 0.8, t, m)
    # модель и доход (c26, c29), ценность (c11)
    m = re.search(r"подписк\w*", low)
    if m:
        _put(out, "c26", "Freemium + подписка (Recommended)", 0.85, t, m)
    else:
        m = re.search(r"разов\w+\s+покупк|купить\s+один\s+раз|навсегда", low)
        if m:
            _put(out, "c26", "Разовая покупка", 0.85, t, m)
        else:
            m = re.search(r"комисси\w*\s+(?:со|с)\s+сдел|процент\s+с\s+(?:продаж|сделок)", low)
            if m:
                _put(out, "c26", "Комиссия со сделок", 0.85, t, m)
            else:
                m = re.search(r"донат\w*|бесплатн\w+\s+(?:для\s+всех|навсегда)|open\s*source|опенсорс", low)
                if m:
                    _put(out, "c26", "Бесплатно: донаты, гранты", 0.8, t, m)
                else:
                    m = re.search(r"\bплатн\w+", low)
                    if m:
                        _put(out, "c26", "Freemium + подписка (Recommended)", 0.55, t, m, "«платный» без модели — уточнить")
    m = re.search(r"основн\w+\s+доход|жить\s+на|зарабатывать\s+на\s+жизнь", low)
    if m:
        _put(out, "c29", "Основной доход", 0.85, t, m)
    else:
        m = re.search(r"подработ\w*|доп\w*\s+доход", low)
        if m:
            _put(out, "c29", "Подработка", 0.85, t, m)
    m = re.search(r"сколько\s+(?:вложить|заработ)|заработ\w+|прибыл\w*|экономи\w+\s+(?:денег|деньги)", low)
    if m:
        _put(out, "c11", "Экономит или приносит деньги", 0.7, t, m)
    # ресурсы (c30, c31, c32), MVP (c17, c18)
    m = re.search(r"я\s+один|в\s+одиночку|делаю\s+сам|соло-?разработ", low)
    if m:
        _put(out, "c30", "Я один (Recommended)", 0.85, t, m)
    m = re.search(r"без\s+бюджет\w*|бюджет\w*\s+(?:нулев\w*|ноль|0\b)|нулев\w+\s+бюджет", low)
    if m:
        _put(out, "c31", "Нулевой (Recommended)", 0.9, t, m)
    m = re.search(r"(\d{1,2})\s*(?:[–-]\s*(\d{1,2}))?\s*час\w*\s*(?:в|/)\s*недел", low)
    if m:
        _put(out, "c32", "%s часов в неделю" % (m.group(2) or m.group(1)), 0.85, t, m)
    m = re.search(r"лендинг\w*|лист\s+ожидани", low)
    if m:
        _put(out, "c17", "Лендинг и лист ожидания", 0.7, t, m)
    m = re.search(r"через\s+(\d+)\s*(нед|мес)\w*", low)
    if m:
        _put(out, "c18", m.group(0), 0.8, t, m)
    # аналоги (c22), образцы (c23)
    comps = [u for u in classify_urls(t_full) if u.get("kind") == "competitor"]
    named = re.findall(r"(?:ориентир|эталон|как\s+у|аналог\w*|конкурент\w*)\s*[—:-]?\s*([A-Za-z][\w.-]{2,}(?:\s+[A-Z][\w.-]+)?)", t)
    names = []
    for c in comps:
        names.append(c["domain"])
    for n in named:
        n = n.strip(" .,")
        if n.lower() not in [x.lower() for x in names] and not re.match(r"https?$", n):
            names.append(n)
    if names:
        mm = re.search(re.escape(names[0].split(".")[0]), t_full, re.I) or COMPETITOR_CTX.search(t_full)
        _put(out, "c22", ", ".join(dict.fromkeys(names)), 0.85, t_full, mm)
    m = re.search(r"вдохновля\w*|нравится\s+как\s+у|в\s+стиле\s+([A-ZА-Я]\w+)", t)
    if m:
        _put(out, "c23", "Есть образцы, впишу", 0.6, t, m)
    # дизайн (c34, c36), название (c35)
    for rx, lab in ((r"строг\w*|делов\w*|терминал\w*", "Строгий деловой"), (r"ярк\w+|игров\w+\s+стил|аниме", "Яркий и игровой"),
                    (r"минималист\w*|спокойн\w+\s+(?:дизайн|стиль)|чист\w+\s+дизайн", "Спокойный и чистый (Recommended)"),
                    (r"дружелюб\w*|friendly|тёпл\w+\s+стил|тепл\w+\s+стил", "Тёплый и дружелюбный")):
        m = re.search(rx, low)
        if m:
            _put(out, "c34", lab, 0.65, t, m)
            break
    m = re.search(r"тёмн\w+\s+и\s+светл\w+|светл\w+\s+и\s+тёмн\w+|темн\w+\s+и\s+светл\w+|обе\s+темы", low)
    if m:
        _put(out, "c36", "Обе, по системе (Recommended)", 0.85, t, m)
    else:
        m = re.search(r"(?:тёмн|темн)\w+\s+тем\w+", low)
        if m:
            _put(out, "c36", "Тёмная", 0.8, t, m)
    m = re.search(r"(?:назов[уё]м?|название|имя\s+продукта)\s*[:—-]?\s*«([^»]{2,40})»", t, re.I)
    if m:
        _put(out, "c35", m.group(1).strip(), 0.9, t, m)
    # внешняя платформа (блок platform, FB-056)
    m = PLATFORM_WORDS.search(t)
    if m:
        name = platform_name(t)
        _put(out, "pl01", name or "Определить по идее (Recommended)", 0.9 if name else 0.7, t, m)
        needs = []
        for rx, lab in ((r"предмет|карт[аыу]\b|карты|спаун|справочник|каталог|цен[аы]\b|событи|лут|крафт", "О мире: справочники, каталоги (Recommended)"),
                        (r"прогресс|сохранени|профил|статистик\w*\s+игрок|инвентар|склад|истори\w+\s+(?:матч|игр)", "О пользователе: профиль, прогресс"),
                        (r"steam|oauth|openid|вход\s+через|авторизац|синхрониз", "Вход через платформу"),
                        (r"покупк\w+\s+от\s+имени|публикац\w+\s+от\s+имени|торгов\w+\s+от\s+имени|отправ\w+\s+от\s+имени", "Действия от имени пользователя")):
            if re.search(rx, low):
                needs.append(lab)
        if needs:
            _put(out, "pl02", needs, 0.8, t, m)
    # данные и интеграции, интерфейс, прототип, админка
    m = DATA_WORDS.search(low)
    if m:
        srcs = []
        if re.search(r"\bapi\b|бирж", low):
            srcs.append("Официальные API сервисов")
        if re.search(r"открыт\w+\s+данн|вики|wiki|датасет", low):
            srcs.append("Открытые данные и файлы")
        if re.search(r"ручн\w+\s+ввод|импорт|выгрузк", low):
            srcs.append("Ручной ввод и импорт")
        _put(out, "da01", srcs or ["Найти в исследовании (Recommended)"], 0.75 if srcs else 0.6, t, m)
    m = re.search(r"(\d)\s*(?:различн\w+\s+|разн\w+\s+)?вариант\w*\s+интерфейс|интерфейс\w*\s*[—:-]?\s*(\d)\s*вариант", low)
    if m:
        _put(out, "ui02", m.group(1) or m.group(2), 0.85, t, m)
    m = re.search(r"\b3d\b|трёхмерн|трехмерн", low)
    if m:
        _put(out, "ui06", ["Обычные графики (Recommended)", "3D-визуализация"] if re.search(r"график", low) else ["3D-визуализация"], 0.8, t, m)
    m = re.search(r"задел\w*\s+под\s+мобильн|мобильн\w+\s+(?:версия|приложение)\s+(?:позже|в\s+будущем|потом)", low)
    if m:
        _put(out, "ui03", "Веб сейчас, мобильное позже (Recommended)", 0.85, t, m)
    m = re.search(r"(?:рабоч\w+|интерактивн\w+|кликабельн\w+)\s+прототип|прототип\w*\s+с\s+(?:расч|логик)", low)
    if m:
        _put(out, "pr01", "Ядро и один рабочий экран", 0.75, t, m)
    m = re.search(r"админк\w*|панел\w+\s+администр|администрирован", low)
    if m:
        _put(out, "ad01", "Только я (Recommended)", 0.5, t, m)
    return out


def normalize_prefill(raw):
    """Предзаполнение от оркестратора: {ключ: ответ} или {ключ: {answer, confidence, quote}} (ключ — id, header или текст
    вопроса; confidence — число 0..1 или high|medium|low) → {ключ: {answer, confidence, quote, source: llm}}."""
    out = {}
    if isinstance(raw, list):
        raw = {str(x.get("id") or x.get("qid") or x.get("header")): x for x in raw if isinstance(x, dict)}
    for k, v in (raw or {}).items():
        if isinstance(v, dict):
            ans = v.get("answer", v.get("value"))
            c = v.get("confidence", 0.9)
            c = {"high": 0.9, "medium": 0.65, "low": 0.4}.get(str(c).lower(), c)
            try:
                c = float(c)
            except (TypeError, ValueError):
                c = 0.65
            out[str(k)] = {"answer": ans, "confidence": round(c if c <= 1 else c / 100.0, 2), "quote": mask(v.get("quote") or "")[:200],
                           "source": "llm"}
        elif v not in (None, "", []):
            out[str(k)] = {"answer": v, "confidence": 0.9, "quote": "", "source": "llm"}
    return out


def merged_prefill(bank, request="", raw=None, audience_known=False):
    """Эвристика по тексту + предзаполнение оркестратора (важнее) → {id: {...}} с ключами-id (header/текст → id)."""
    look = lookup(bank)
    res = {}
    for k, v in prefill_from_text(request, audience_known).items():
        res[k] = v
    for k, v in normalize_prefill(raw).items():
        hit = look.get(k)
        qid = hit[0][0] if hit else k
        res[qid] = v
    return {k: v for k, v in res.items() if k in look}


# ---------------------------------------------------------------- условные блоки: что показывать
def _facets(cfg):
    return ((cfg.get("idea") or {}).get("facets")) or {}


def blocks_for(cfg, text="", mode="standard"):
    """Какие блоки задать и сколько вопросов: [(ключ, название, причина, [вопросы])] по ответам (cfg после apply) и тексту."""
    f = _facets(cfg)
    mode = mode if mode in BLOCK_SIZE else "standard"
    low = str(text or "").lower()
    pr = cfg.get("product") or {}
    aud = audience_of((cfg.get("project") or {}).get("audience"))
    personal = aud in PERSONAL_AUDIENCES
    forms = set(pr.get("forms") or [])
    ptype = pr.get("type") or "saas"
    out = []

    def add(key, why, n):
        qs = sorted(BLOCKS[key][2], key=lambda q: q[2])
        if n > 0:
            out.append((key, BLOCKS[key][0], why, qs[:n]))

    if f.get("platform_dependency") or PLATFORM_WORDS.search(low):
        add("platform", "в идее есть внешняя платформа или игра" if PLATFORM_WORDS.search(low) else "ответ «Пл: какая»",
            BLOCK_SIZE[mode]["platform"])
    if f.get("platform_dependency") or DATA_WORDS.search(low) or f.get("data_sources_needed"):
        add("data", "продукт зависит от внешних данных или API", BLOCK_SIZE[mode]["data"])
    ai = f.get("ai") or "helper"
    if ai != "none":
        n = AI_SIZE[mode]["core" if ai == "core" else "helper"]
        add("ai", "ИИ — ядро продукта" if ai == "core" else "ИИ как помощник", n)
    sens = [x for x in f.get("sensitive") or [] if x]
    areas = []
    if "finance" in sens or (sens and FIN_WORDS.search(low)) or FIN_WORDS.search(low) and re.search(r"бирж|инвест|акци|фьючерс|трейд|брокер", low):
        areas.append("law:finance")
    if CRYPTO_WORDS.search(low):
        areas.append("law:crypto")
    if "health" in sens or HEALTH_WORDS.search(low):
        areas.append("law:health")
    if "children_pd" in sens and CHILD_WORDS.search(low):
        areas.append("law:children")
    if f.get("data") in ("personal", "sensitive") or "children_pd" in sens or (ai == "core" and f.get("data") == "personal"):
        areas.append("law:pd")
    if areas or "custom" in sens:
        qs = [q for q in sorted(BLOCKS["law"][2], key=lambda q: q[2]) if q[1] == "law" or q[1] in areas]
        if mode == "fast":
            qs = [qs[0]] + [next(q for q in qs if q[1] == a) for a in areas if any(q[1] == a for q in qs)]
        why = "чувствительная область: %s" % ", ".join(a.split(":")[1] for a in areas) if areas else "свой ответ «Область»"
        if ai == "core" and f.get("data") in ("personal", "sensitive"):
            why += "; ИИ-ядро и личные данные"
        out.append(("law", BLOCKS["law"][0], why, qs))
    web_service = ptype in ("saas", "bot", "mobile", "game", "content", "consumer") or forms & {"web", "mobile_web", "bot"}
    if web_service:
        n = BLOCK_SIZE[mode]["admin"]
        if personal:
            n = min(n, 3 if mode != "deep" else 9)
        add("admin", "веб-продукт или сервис" + (" (личный режим — минимум эксплуатации)" if personal else ""), n)
    if (cfg.get("scope") or {}).get("design_mockups", True):
        add("interface", "макеты включены", BLOCK_SIZE[mode]["interface"])
    add("prototype", "проверить, нужен ли рабочий прототип", BLOCK_SIZE[mode]["prototype"])
    add("owner", "что у владельца уже есть (референсы, данные, ограничения)", BLOCK_SIZE[mode]["owner"])
    st = cfg.get("strategy") or {}
    if not personal and st.get("paid_tier") != "no" and st.get("monetization") not in ("donations", "none"):
        add("payments", "платная модель: выбор канала оплаты влияет на модель дохода", BLOCK_SIZE[mode]["payments"])
    order = {k: i for i, k in enumerate(BLOCK_ORDER)}
    out.sort(key=lambda x: order.get(x[0], 99))
    return out


def text_blocks(text, mode="standard"):
    """Блоки, которые видны по одному тексту (до ответов): платформа, данные, ИИ (если ИИ в тексте), право по областям,
    интерфейс (если в тексте варианты интерфейса или 3D). → [(ключ, вопросы)] — кандидаты на освободившиеся места."""
    low = str(text or "").lower()
    pseudo = {"idea": {"facets": {}}, "product": {"type": "", "forms": []}, "project": {}, "scope": {"design_mockups": False},
              "strategy": {"paid_tier": "no"}}
    if AI_WORDS.search(low):
        pseudo["idea"]["facets"]["ai"] = "core" if AI_CORE.search(low) else "helper"
    else:
        pseudo["idea"]["facets"]["ai"] = "none"
    res = []
    for key, _t, _w, qs in blocks_for(pseudo, text, mode):
        if key in ("prototype", "owner"):
            continue
        res.append((key, qs))
    if re.search(r"вариант\w*\s+интерфейс|интерфейс\w*.{0,20}вариант|\b3d\b", low):
        res.append(("interface", sorted(BLOCKS["interface"][2], key=lambda q: q[2])[:BLOCK_SIZE.get(mode, BLOCK_SIZE["standard"])["interface"]]))
    return res
