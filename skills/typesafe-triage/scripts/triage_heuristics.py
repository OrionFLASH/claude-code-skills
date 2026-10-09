# -*- coding: utf-8 -*-
"""Дешёвые локальные сигналы о задаче по самому тексту: без сети, без зависимостей, детерминированно, ~1 мс.

Зачем. TypeSafe отвечает на узкие вопросы, но (а) бывает недоступен (нет ключа, сеть, пауза защиты) и (б) не видит
того, что легко посчитать кодом: длину, число пунктов и файлов, наличие кода и логов, слова про продакшн, деньги,
безопасность, необратимость. Эти сигналы:
  * при ответе TypeSafe — только ПОДНИМАЮТ нагрузку (вверх легко) и могут запретить haiku / разрешить fable;
  * без TypeSafe — единственный источник уровня (запасной вариант: только sonnet или opus, уверенность низкая).

С версии 2.1 здесь же — сигналы второй оси, reasoning effort (глубина размышления): тип намерения (найти / объяснить /
исправить / спроектировать / доказать …), требования и критерии приёмки, ограничения, неопределённость, диагностика,
объём, математика, повтор после неудачи, язык; и явные указания пользователя («effort max», «ultrathink», «на opus»,
«тщательно», «быстро», с учётом отрицаний) — directives(text).

Все словари и пороги — константы ниже; меняются вместе с `--selftest --heuristic` / `--calibrate` (triage_cases.json).
Публичное API: signals(text) -> dict, is_chatter(text) -> bool, directives(text) -> dict,
mentions(text) -> (замаскированный текст, число скрытых упоминаний, вставленный отчёт?).
"""
import bisect
import re
from collections import Counter

FLAGS_RE = re.I | re.U

# Слова: русские основы + английские. Совпадение по началу слова, чтобы «удалить» и «удали» попадали одинаково.
CRITICAL_GROUPS = {
    "production": r"\bпрод\b|\bпродакшн|\bпродуктив|\bбоев|\bproduction\b|\bprod\b|\blive (?:site|system|data|database)",
    "irreversible": (r"необратим|безвозврат|irreversib|cannot be undone|force.?push|drop (?:table|database)|rm -rf|truncate"
                     r"|удал\w* (?:вс\w*|баз\w*|ветк\w*|репозитор\w*|аккаунт\w*|данн\w*|таблиц\w*|истори\w*|бэкап\w*)"
                     r"|delete (?:all|the database|the branch|the repo|account|data|history)|\bмиграц|\bmigrat|переезд\w* (?:баз|сервер|данн|систем|кластер)"),
    "security": (r"безопасн|уязвим|\bsecurity\b|vulnerab|\bauth\b|аутентифик|авторизац|прав\w* доступа|\bpermission|\bсекрет"
                 r"|шифров|encrypt|\bcrypto|\bпарол|\bpassword|\boauth|\bsso\b|\bcve-|credential|учётн\w* данн|api.?keys?|ключ\w* доступа"
                 r"|session handling|сесси\w* пользоват"),
    "money": (r"\bденьг|\bденеж|платеж|платёж|\bоплат|\bpayment|\bbilling|\binvoice|\bсчёт|\bсчет\w* на оплат|бюджет"
              r"|\bbudget|финанс|financ|\bналог|\btax\b|бухгалт|accounting|зарплат|payroll|\bбанк|\bbank|\bтранзакц|transaction"
              r"|\bкредит|ипотек|\bloans?\b|mortgage|interest rate|годовых|valuation|\bdcf\b|acquisition|инвестор|investor"
              r"|совет\w* директоров|board of directors|the board\b|\bledger|reconcil|проводк|остатк\w* (?:по|на) сч"),
    "legal_medical": (r"юридич|\blegal\b|\bдоговор(?:а|у|ом|е|ы|ов|ами|ах)?\b|\bcontract\b|лицензи|licens|медицин|medical|\bдиагноз|\bgdpr|персональн\w* данн"
                      r"|\bpii\b|compliance|регулятор|152-фз|\bсуд\b|\bиск\b|лекарств|препарат|medicat|drug interaction|\bврач|\bdoctor"
                      r"|\bзакон\w*|\blaws?\b|штраф|\bfines?\b"),
    "data_loss": (r"данн\w* (?:клиент|пользовател|заказчик)|customer data|user data|\bбэкап|\bbackup|резервн\w* коп"
                  r"|потер\w* данн|data loss|без простоя|zero.?downtime"),
}
DEEP_RE = re.compile(
    r"\bпочему|\bзачем|\bwhy\b|как (?:устроен|работает|это работает)|how (?:does|do) .{0,40}work|\bпричин|root cause|разбер\w*ся"
    r"|\binvestigat|исследу|исследован|\bresearch|спроектир|проектирован|\bdesign\b|архитектур|architect|стратеги|strateg|гипотез|hypothes"
    r"|\bсравни|\bcompare|trade.?off|компромисс|\bоцени\b|\bevaluat|\bassess|доказ|\bprove\b|оптимиз|optimi[sz]"
    r"|рефактор|refactor|переделай|перестр|redesign|rewrite|перепиш|продума|think through|анализ|analy[sz]|диагност|\bdebug|прогноз|forecast"
    r"|отлад|утечк|\bleak|race condition|гонк\w* данн|deadlock|взаимоблок|производительн|performance|узк\w* мест|bottleneck"
    r"|модель данных|модель правил|data model|финансов\w* модел|спецификац|specification|\bплан\w* (?:миграц|переход|внедрен|проект)|\bаудит|\baudit"
    r"|обоснова|justif|\bреализуй|\bimplement|обратн\w* совместим|backward.?compat|\bриск|\brisk",
    FLAGS_RE)
LIGHT_RE = re.compile(
    r"переименуй|\brename|\bвыведи|\bпокажи|\bshow\b|\blist\b|перечисли|\bсписок|найди,? где|where is|\bгде (?:лежит|находится|задаётся|задается)"
    r"|\bпосчитай|\bcount\b|отформатируй|\bformat\b|опечатк|\btypo|замени .{1,60} на|\breplace\b|переведи|\btranslate|сократи"
    r"|орфограф|\bspell|скопируй|\bcopy\b|\bпросто\b|\bjust\b|\bonly\b|\bтолько\b|одн\w* строк|one line|без изменений|ничего не меняй"
    r"|больше ничего|\bнапомни|\bremind|\bчто такое|what is\b|как называется|\bопредели (?:тип|формат)",
    FLAGS_RE)
STEP_RE = re.compile(
    r"\bзатем\b|\bпотом\b|после этого|\bдалее\b|\bшаг\w*\b|\bэтап\w*\b|\bthen\b|after that|\bstep\b|\bsteps\b|\bphase|во-первых|во-вторых"
    r"|\bfirst,|\bsecond,|\bfinally\b|в конце|\bи ещё\b|\bа также\b|\bas well as\b|\balso\b|\bтакже\b",
    FLAGS_RE)
ITEM_RE = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+\S", re.M)
PATH_RE = re.compile(
    r"(?:[\w.-]+/)+[\w.-]+|\b[\w-]+\.(?:py|js|ts|tsx|jsx|mjs|md|json|ya?ml|sql|csv|xlsx?|docx?|pdf|pptx?|html?|css|scss|go|rs|java"
    r"|kt|swift|rb|php|sh|ps1|toml|ini|cfg|txt|ipynb|c|h|cpp|hpp|cs|vue|svelte|tf|lock)\b", FLAGS_RE)
LOG_RE = re.compile(r"traceback|exception|\berror\b|\bfatal\b|\bpanic\b|stack ?trace|\bat [\w.$]+\(|\bошибк|\bпадает|\bупал", FLAGS_RE)
CODE_LINE_RE = re.compile(r"^\s*(?:def |class |function |const |let |var |import |from \S+ import|return\b|if \(|for \(|\}|\{|<\w+[ >]|SELECT\b|#include)",
                          re.M)
FENCE_RE = re.compile(r"```.*?```", re.S)
CHATTER_RE = re.compile(
    r"^\s*(?:спасибо|благодарю|отлично|супер|класс|круто|ок(?:ей)?|окей|хорошо|понял[аи]?|ясно|принято|согласен|согласна|да|нет|ага"
    r"|давай(?:те)?|продолжай(?:те)?|продолжим|дальше|go on|go ahead|continue|thanks|thank you|great|ok(?:ay)?|yes|no|sure|cool|nice"
    r"|perfect|got it|sounds good)\b", FLAGS_RE)
WORK_RE = re.compile(  # глаголы-поручения: если они есть, реплика уже не «болтовня»
    r"\b(?:сделай|напиши|исправь|почини|добавь|удали|перепиши|переделай|проверь|найди|создай|настрой|запусти|разбер|объясни|опиши"
    r"|составь|подготовь|посчитай|сравни|спроектир|реализуй|обнови|распиш|допиш|доделай|дополни|доведи|закончи"   # 2.3: «продолжай, распиши …» — поручение
    r"|write|fix|add|remove|delete|create|check|find|build|implement|update|explain|prepare|compare|design|refactor|review|run|finish)\w*",
    FLAGS_RE)

CRITICAL_RES = {k: re.compile(v, FLAGS_RE) for k, v in CRITICAL_GROUPS.items()}

# 2.2.0 (T-1): короткое продолжение текущей работы («продолжай тесты», «и ещё добавь…») — оценивать вместе с активной задачей
CONTINUE_RE = re.compile(
    r"(?:\bпродолж\w*|\bдальше\b|\bи\s+ещ[её]\b|\bещ[её]\s+(?:добавь|сделай|проверь|допиши)|\bgo on\b|\bcontinue\b|\bkeep going\b"
    r"|\bcarry on\b|\band also\b)", FLAGS_RE)
CONTINUE_MAX_CHARS = 300
# 2.2.0 (T-3): работа в общем интерактивном состоянии (браузер пользователя, его вход, открытая сессия) — по тексту запроса
SHARED_TEXT_RE = re.compile(
    r"(?:\bв\s+(?:мо[её]м|моей|открыт\w+|том\s+же|общем|этом|этой)\s+(?:браузере|окне|вкладке|профиле|сессии)"
    r"|\bпод\s+моим\s+(?:входом|аккаунтом|логином)|\bя\s+(?:уже\s+)?(?:вош[её]л|вошла|залогинил\w*|авторизовал\w*)"
    r"|\bCDP\b|\b9222\b|\bmy\s+(?:browser|open\s+tab|logged[- ]in\s+session)|\balready\s+logged\s+in\b)", FLAGS_RE)

# 2.3.0 (#27): признаки для строки «ДЕЙСТВИЕ» — что выгоднее: сам, субагент или спросить (см. action_signals)
# Одно устройство/эмулятор: одно взаимодействие с живым интерфейсом за раз, исполнитель его не разделит
DEVICE_RE = re.compile(
    r"\bэмулятор\w*|\bсимулятор\w*|\bemulators?\b|\bsimulators?\b|\bAVD\b|\badb\b|\bна\s+(?:устройстве|телефоне|смартфоне|планшете)"
    r"|\bon\s+(?:the|my|a)\s+(?:device|phone|tablet)\b", FLAGS_RE)
# Явная просьба пользователя о субагенте — сильнее любых индексов (триаж подтверждает, а не спорит)
AGENT_REQ_RE = re.compile(
    r"\bсубагент\w*|\bсаб-?агент\w*|\b(?:используй|задействуй|запусти|позови|отдай|поручи|передай|через|с\s+помощью)\s+(?:\w+\s+){0,2}"
    r"агент\w*\b(?!\s+(?:поддержк|продаж|по\s|недвижимост|страхов|банк))"
    r"|\bделегируй\b|\bделегировать\b|\bsub-?agents?\b|\b(?:use|spawn|launch|start|via|with)\s+(?:an?\s+|the\s+|separate\s+)?agents?\b"
    r"|\bdelegate\b", FLAGS_RE)
# … и просьба сделать самому, без делегирования (отрицание «не используй субагента» — тоже сюда)
SELF_REQ_RE = re.compile(
    r"\bбез\s+(?:суб-?)?агент\w*|\bне\s+(?:\w+\s+)?(?:делегируй|делегировать|используй\s+(?:суб-?)?агент\w*|запускай\s+(?:суб-?)?агент\w*"
    r"|отдавай\s+(?:суб-?)?агент\w*)|\b(?:сделай|выполни|проверь|разберись|почини|поправь|напиши)\s+(?:это\s+)?сам\b"
    r"|\bсам(?:а)?\s+(?:сделай|выполни|проверь|разберись|почини|поправь|напиши)\b|\bdo\s+it\s+yourself\b|\byourself,?\s+(?:not|without)\b"
    r"|\bwithout\s+(?:a\s+|any\s+)?sub-?agents?\b|\bdon'?t\s+(?:(?:use|spawn)\s+(?:an?\s+|any\s+|the\s+)?(?:sub-?)?agents?|delegate)\b|\bno\s+sub-?agents?\b", FLAGS_RE)
# Долгое ожидание (минуты-часы): выгоднее фоновый скрипт и проверка его состояния, а не LLM-исполнитель, который ждёт
WAIT_STRONG_RE = re.compile(
    r"\bвсю\s+ночь\b|\bсутк\w*|\bsoak\b|\bovernight\b|\bдлительн\w*\s+(?:тест|прогон|запис|сценари|нагрузк|ожидан)"
    r"|\bдолг\w*\s+(?:тест|прогон|запис|ожидан|сценари)|\blong[- ]running\b|\bwait\s+(?:for|until)\b|\bдожд(?:ись|аться|ёмся)\b"
    r"|\bподожди\b|\bмониторь\b|\bследи\s+за\b|\bнаблюдай\s+за\b|\bkeep\s+an\s+eye\b|\bmonitor\s+(?:it|the|for)\b", FLAGS_RE)
WAIT_DUR_RE = re.compile(
    r"(?:\bна|\bв\s+течение|\bчерез|\bкаждые|\bраз\s+в|\bfor|\bevery|\bafter|\bin)\s+(\d+(?:[.,]\d+)?)\s*(?:-|–)?\s*"
    r"(мин\w*|ч\b|час\w*|minutes?|mins?|hours?|h\b)|\bв\s+течение\s+(?:часа|дня|ночи)\b|\bраз\s+в\s+час\b|\bfor\s+an?\s+hour\b", FLAGS_RE)
WAIT_MIN_MINUTES = 5
# Части можно делать параллельно (несколько исполнителей)
PARALLEL_RE = re.compile(
    r"\bпараллельн\w*|\bв\s+параллель\b|\bодновременно\b|\bнезависим\w*\s+(?:част|задач|пакет|модул)|\bin\s+parallel\b|\bconcurrently\b"
    r"|\bindependent\s+(?:parts|tasks|packages|modules)\b|\bдля\s+каждого\b|\bпо\s+каждому\b|\bfor\s+each\b|\beach\s+of\s+the\b", FLAGS_RE)
# Ссылки на уже накопленный контекст разговора: передать его субагенту дорого
CONTEXT_REF_RE = re.compile(
    r"\bкак\s+(?:мы\s+)?(?:обсуждали|договорились|решили|выше|раньше|в\s+прошлый\s+раз)\b|\bвыше\s+(?:по\s+тексту|в\s+чате)\b"
    r"|\b(?:из|по)\s+(?:предыдущ|прошл)\w+\s+(?:шаг|ответ|прогон|сообщени|итерац)\w*|\bнайденн\w+\s+(?:ранее\s+)?(?:дефект|ошибк|баг|проблем|находк)"
    r"|\bas\s+(?:we\s+)?(?:discussed|agreed|above|before)\b|\bfrom\s+(?:the\s+)?(?:previous|earlier|last)\s+(?:step|answer|run|message)"
    r"|\bthe\s+(?:issues|bugs|findings)\s+(?:you|we)\s+found\b", FLAGS_RE)

# ---------- вторая ось: reasoning effort (глубина размышления) ----------
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Тип намерения → «естественная» глубина 0..1 (берётся максимум найденных). Порядок не важен.
INTENTS = {
    "lookup": (0.10, r"\bнайди,? где|\bгде (?:лежит|находится|задаётся|задается|настраивается)|\bпокажи|\bвыведи|\bперечисли|\bсписок"
                     r"|\bпосчитай|\bсколько\b|where is|\bshow\b|\blist\b|\bcount\b|how many|\bwhat is\b|\bчто такое|\bчто означает"),
    "transform": (0.15, r"переименуй|\brename|отсортируй|\bsort\b|отформатируй|\bformat\b|переведи|\btranslate|сконвертируй|\bconvert"
                        r"|замени .{1,60} на|\breplace\b|исправь опечат|\btypo|скопируй|copy (?:the|this|it)\b"),
    "explain": (0.30, r"\bобъясни|\bрасскажи|\bопиши|\bчто делает|explain|describe|what does|\bsummari[sz]|резюме|\bсводк|\bперескажи"),
    "write": (0.35, r"\bнапиши|\bсоставь|\bподготовь|\bсделай (?:пост|письмо|текст|резюме|отчёт|отчет)|\bwrite\b|\bdraft\b|\bcompose"
                    r"|\bотредактируй|\bedit\b|\bдобавь|\badd\b|\bобнови|\bupdate\b"),
    "fix": (0.50, r"\bисправь|\bпочини|\bfix\b|\brepair|\bустрани|\bпочему не работает"),
    "calculate": (0.50, r"\bрассчитай|\bрасч[её]т|\bcalculat|\bпосчитай.{0,40}(?:процент|кредит|ставк|плат[её]ж|налог|прибыл|убыт|переплат)"
                        r"|\bформул|\bformula|\bпрогноз|forecast|\bграфик плат"),
    "verify": (0.60, r"\bпроверь\b|\bперепроверь|\bсверь|\breview\b|\baudit|\bcheck (?:the|our|for|that|whether)|\bvalidate|\bverify"),
    "research": (0.60, r"\bsurvey|\bисследуй|\bизучи|\bresearch|\bfind out|\bвыясни|\bpropose|\bпредложи (?:план|подход|вариант)"),
    "compare": (0.60, r"\bсравни|\bcompare|\bвыбери|\bпосоветуй|\brecommend|\bоцени\b|\bevaluat|\bassess|\breview\b|\bпроверь договор|\bпроанализируй"
                      r"|\banaly[sz]e"),
    "optimize": (0.65, r"оптимизир|\boptimi[sz]|ускор|\bspeed up|производительн|performance|узк\w* мест|bottleneck"),
    "migrate": (0.65, r"рефактор|refactor|\bмигр|\bmigrat|\bперенеси (?:баз|данн|систем|бухгалт|сервис|учёт|учет)|переезд\w* (?:баз|сервер|данн|систем|кластер)|перепиш|\brewrite|перестр|\bupgrade|\brotate|cutover|переключ"
                      r"|\bswitch (?:traffic|over)"),
    "diagnose": (0.70, r"\bпочему|\bwhy\b|\bразбер(?:ись|итесь|у|ёмся|емся|\w*ся)|\bразобраться|\bпричин|root cause|\bdebug|\bотлад"
                       r"|\binvestigat|диагност|\bfigure out|в ч[её]м дело|что не так|откуда (?:расхожд|разниц)|\blook into|what'?s wrong"),
    "design": (0.75, r"спроектир|\bdesign\b|архитектур|architect|стратеги|strateg|\bразработай (?:стратег|план|модел|архитект|схем)"
                     r"|модель данных|data model|финансов\w* модел|\bbuild (?:a|the) (?:[\w-]+ ){0,3}model|\bпострой (?:модель|прогноз)"),
    "prove": (0.85, r"\bдокажи|\bдоказ|\bprove\b|\bproof\b|формально провер|formally verif|\bверифицир|\bverify (?:that|the correctness)"),
}
REQUIRE_RE = re.compile(r"\bдолж(?:ен|на|но|ны)\b|\bнужно\b|\bнеобходимо\b|\bтребуется\b|\bmust\b|\bshould\b|\bneeds? to\b|\brequired?\b", FLAGS_RE)
ACCEPT_RE = re.compile(
    r"критери\w* (?:приёмки|приемки|готовности|успеха)|acceptance criteria|definition of done|\bdod\b|тест\w* должн\w* (?:проход|быть зел)"
    r"|must pass|should pass|все тесты|all tests|\bчтобы (?:все|тесты|сборка)|so that (?:all|the tests|the build)", FLAGS_RE)
CONSTRAINT_RE = re.compile(
    r"\bнельзя\b|\bобязательно\b|\bстрого\b|\bне (?:меняй|трогай|ломай|удаляй|менять|трогать|ломать)\b|\bбез (?:потери|простоя|изменени|поломки)"
    r"|\bне более\b|\bне менее\b|\bровно\b|\bне позже\b|\bдо \d|\bmust not\b|\bnever\b|\bdo not\b|\bdon'?t (?:change|touch|break|remove)"
    r"|\bwithout (?:breaking|downtime|losing|changing)|\bat most\b|\bat least\b|\bexactly\b|\bno later than\b|обратн\w* совместим|backward.?compat",
    FLAGS_RE)
UNCERTAIN_RE = re.compile(
    r"как-нибудь|как-то\b|не знаю|непонятно|неясно|не уверен|может быть|\bвозможно\b|\bили\b|какой (?:лучше|выбрать)|что лучше|\bне понимаю"
    r"|\bnot sure\b|\bsomehow\b|\bunclear\b|\bmaybe\b|\bperhaps\b|\bor\b|which (?:is better|one)|i don'?t know|no idea", FLAGS_RE)
DIAG_RE = re.compile(
    r"\bошибк|\bлог(?:и|ов|е|ам)?\b|трассиров|\bstack ?trace|traceback|\bиногда\b|плавающ|не воспроизвод|\bintermittent|\bflaky|\bsometimes\b"
    r"|\brandomly\b|не работает|сломал|\bпадает|\bупал|\bcrash|\bfails?\b|\bfailing\b|exception|регресс|regression|утечк|\bleak|зависа|\bhangs?\b"
    r"|тайм-?аут|time[ds]?[ -]?out|не реагирует|\bнеправильн\w* (?:результат|цифр|сумм)|wrong (?:result|numbers|total)|расхожд|discrepanc"
    r"|периодически|не сход|off by one|\b(?:http|отда\w*|returns?) 5\d\d\b|\bbroken\b", FLAGS_RE)
SCOPE_RE = re.compile(
    r"все файлы|весь проект|всего проекта|во всех (?:файлах|модулях|экранах|документах|листах)|по всему (?:проекту|коду|репозиторию)"
    r"|whole (?:project|codebase|repo)|all (?:files|modules|documents|sheets)|entire (?:project|codebase|repo|dataset)|everywhere"
    r"|\b\d{2,}\s*(?:страниц|pages|файл|files|лист|sheets|документ|documents|строк|rows|записей|records)", FLAGS_RE)
MATH_RE = re.compile(
    r"докаж|теорем|\bлемм|формул|уравнен|интеграл|производн|вероятност|статистич|дисперси|регресси\w* модел|\bproof\b|theorem|\blemma"
    r"|equation|integral|derivative|probabilit|statistic|variance|[∑∫√≤≥≠∀∃]", FLAGS_RE)
RETRY_RE = re.compile(  # повтор ПОСЛЕ НЕУДАЧИ, а не просто «снова»/«ещё раз» («чтобы он снова читался» — не повтор)
    r"(?:\bопять|\bснова)\s+(?:не\b|падает|упал|сломал|ошибк|то же|та же|глючит|висит|вылета)|всё ещё не|все ещё не|все еще не"
    r"|до сих пор не|не помогло|не сработало|по-прежнему не|по-прежнему (?:падает|ошибк)|та же (?:ошибка|проблема)|ошибка та же"
    r"|\bstill (?:fails|failing|broken|not|the same|doesn'?t|wrong|off)|didn'?t (?:help|work|fix)|doesn'?t work|same (?:error|problem|issue)"
    r"|not fixed|(?:fails?|broken|wrong) again|again (?:fails?|broken)", FLAGS_RE)
CYR_RE = re.compile(r"[а-яё]", re.I)
LAT_RE = re.compile(r"[a-z]", re.I)

# Явные указания пользователя. Тир — только с «маркером» рядом («на opus», «model haiku», «use fable»), чтобы не ловить
# слово «opus» в постороннем смысле. Эффорт: «effort max», «max effort», «усилия: высокие», «ultrathink» — жёсткие
# (точный уровень); «тщательно/глубоко/think hard» — мягкий пол, «кратко/навскидку/quick answer» — мягкий потолок low.
TIER_ALIASES = {"haiku": r"haiku|хайку", "sonnet": r"sonnet|сонн?ет\w*", "opus": r"opus|опус\w*", "fable": r"fable|фейбл\w*"}
TIER_DIRECTIVE_RE = re.compile(
    r"(?:\bна|\bмодел\w*|\bmodel|\buse|\busing|\bon|\bwith|\bчерез|\bвозьми|\bзапусти\w*(?:\s+агента)?(?:\s+на)?|\brun(?:\s+it)?\s+on)\s+"
    r"(?:модел\w+\s+|model\s+)?(?P<t>" + "|".join(TIER_ALIASES.values()) + r")\b", FLAGS_RE)
EFFORT_WORDS = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "max",
                "минимальн": "low", "низк": "low", "средн": "medium", "высок": "high", "очень высок": "xhigh", "максимальн": "max",
                "максимум": "max", "минимум": "low"}
EFFORT_DIRECTIVE_RE = re.compile(
    r"(?:\b(?:reasoning\s+)?effort|\bусили[еяй]\w*|\bуровень усилий)\s*[:=]?\s*(?:на\s+)?(?P<a>low|medium|high|xhigh|max|очень высок\w*|минимальн\w*|"
    r"низк\w*|средн\w*|высок\w*|максимальн\w*|максимум|минимум)\b"
    r"|\b(?P<b>low|medium|high|xhigh|max|минимальн\w*|низк\w*|средн\w*|высок\w*|максимальн\w*)\s+(?:reasoning\s+)?(?:effort|усили\w*)", FLAGS_RE)
HARD_PHRASES = [  # (регэксп, уровень) — точный уровень, согласие пользователя
    (r"\bultrathink\b|\bультрасинк", "max"),
    (r"без размышлений|не думая\b|минимум усилий|минимальн\w* усили|without thinking|\bno thinking\b|minimal effort|\bno reasoning\b", "low"),
]
SOFT_MIN = [  # (регэксп, пол) — «подумай как следует» и т. п.
    (r"максимально (?:тщательно|глубоко|подробно|внимательно)|очень (?:тщательно|глубоко|внимательно)|think (?:really |very )?harder"
     r"|think (?:really|very) hard|as thoroughly as possible|leave no stone unturned", "xhigh"),
    (r"подумай (?:как следует|хорошенько|хорошо|внимательно)|хорошенько подумай|\bтщательн\w*|\bглубок\w*|\bосновательн\w*|\bдосконально"
     r"|\bвдумчиво|не торопись|не спеши|без спешки|продумай вс[её]|think hard|think carefully|think deeply|\bthorough(?:ly)?\b"
     r"|\bcarefully\b|in depth|\bdeep(?:ly)? (?:dive|analy)|take your time", "high"),
]
SOFT_MAX = [  # (регэксп, потолок) — «кратко», «навскидку»: просьба о быстром ответе
    (r"\bкратко\b|\bкоротко\b|в двух словах|\bнавскидку\b|по-быстрому|на скорую руку|быстрый ответ|(?:ответь|скажи|глянь|посмотри|подскажи) быстро"
     r"|быстро (?:ответь|скажи|глянь|посмотри|подскажи)|одн\w+(?:-двумя)? (?:фраз|строк|предложени)|\bbriefly\b|\bin short\b|in a nutshell"
     r"|quick answer|quickly (?:answer|tell|check)|off the top of your head|\btl;?dr\b|one sentence|one line answer|\bdon'?t overthink", "low"),
]
NEG_BEFORE_RE = re.compile(r"(?:\bне|\bнет|\bни|\bno|\bnot|n't|\bnever|\bбез)(?:\s+[\w-]+){0,2}\s*[,:]?\s*$", FLAGS_RE)
_HARD = [(re.compile(rx, FLAGS_RE), lvl) for rx, lvl in HARD_PHRASES]
_SMIN = [(re.compile(rx, FLAGS_RE), lvl) for rx, lvl in SOFT_MIN]
_SMAX = [(re.compile(rx, FLAGS_RE), lvl) for rx, lvl in SOFT_MAX]
_MARKERS = [TIER_DIRECTIVE_RE, EFFORT_DIRECTIVE_RE] + [rx for rx, _ in _HARD + _SMIN + _SMAX]

# ---------- упоминание (mention) против использования (use) ----------
# Маркер в кавычках/коде или в пересказе чужих слов — это упоминание («слово «ultrathink» ставит максимум»), а не
# указание. Исключение — одиночный маркер в кавычках в императивной фразе («сделай это «на opus»»).
QUOTE_RES = [re.compile(p) for p in (
    r"«[^«»\n]{1,300}»", r"“[^“”\n]{1,300}”", r"„[^„“”\n]{1,300}[“”]", r'"[^"\n]{1,300}"',
    r"(?<![\w'’])['‘][^'‘’\n]{1,120}['’](?![\w'’])", r"`[^`\n]{1,300}`")]
# Пересказ/цитирование: от маркера до конца предложения — упоминание. «я сказал» (первое лицо) — не цитата.
CITE_RE = re.compile(
    r"(?:\bассистент\w*|\bclaude(?: code)?|\bмодель|\bагент|\bсубагент|\bбот|\bон|\bона|\bони|\bпользователь|\bзаметк\w*"
    r"|\bотч[её]т\w*|\bдокументаци\w*|\bинструкци\w*|\bскилл?)\s+(?:мне\s+|нам\s+|тут\s+|здесь\s+|прямо\s+)?"
    r"(?:сказал\w*|ответил\w*|написал\w*|пишет|пишут|говорит|советует|советовал\w*|предлагает|рекомендует|утверждает|сообща\w*)"
    r"|\bответ ассистента|\bв (?:отч[её]те|цитате|ответе ассистента|заметке написано)|\bнаписано\s*:|\bцитирую|\bцитата\b"
    r"|\bпо (?:его|её|ее|их) словам"
    r"|\b(?:the )?(?:note|assistant|model|agent|report|docs?|user|it|he|she|they)\s+(?:says|said|suggests|suggested|wrote|writes"
    r"|replied|recommends|answered)\b|\bin the report\b|\bquote:", FLAGS_RE)
# Подпись «слово/фраза …» — упоминанием считается только следующая за ней кавычка или маркер, а не всё предложение
# («фраза «на opus» не сработала, сделай на opus» — второе «на opus» остаётся указанием).
LABEL_RE = re.compile(r"\b(?:слов[оа]|словами|фраз[аыуе]|фразой|выражени[ея]|маркер\w*|the (?:word|phrase)s?)\s*:?\s*", FLAGS_RE)
IMPERATIVE_RE = re.compile(  # повелительное наклонение вне кавычек: «сделай это «на opus»» — использование
    r"\b(?:с?дела|запуст|запуска|использу|возьм|постав|работа|провер|разбер|реш|ответ|по?дума|оцен|выполн|перепиш|исправ"
    r"|напиш|почин|п(?:ер)?есчита|посчита|сравн|спроектиру|примен|включ|выбер|переключ|прогон|провед|проанализиру|продума"
    r"|перепровер|разработа|подготов|составь?)(?:й|йте|и|ите|ь|ьте)(?:сь|ся)?\b"
    r"|\b(?:пожалуйста|давай(?:те)?|please|let'?s)\b"
    r"|^\W*(?:use|run|do|make|think|answer|check|fix|write|review|set|switch|go|try|analy[sz]e|design|prove|compare|explain)\b",
    FLAGS_RE)
SENT_END_RE = re.compile(r"[.!?;\n]")
REPORT_DUP_MIN = 40                # повтор предложения не короче (знаков) — признак вставленного текста
REPORT_QUOTED_MARKERS = 3          # столько маркеров в кавычках — это перечисление примеров, а не указания
REPORT_MIN_CHARS = 200


def _sentence_index(text):
    """Позиции концов предложений (по .!?; и переводу строки) — для быстрого поиска границ (bisect)."""
    return [m.start() for m in SENT_END_RE.finditer(text)]


def _sentence_bounds(ends, n, start, end):
    """Начало и конец предложения, содержащего [start, end): ends — _sentence_index, n — длина текста."""
    i = bisect.bisect_left(ends, start)
    b = ends[i - 1] + 1 if i else 0
    j = bisect.bisect_left(ends, end)
    return b, (ends[j] if j < len(ends) else n)


def _blank(chars, a, b):
    for i in range(a, b):
        if chars[i] != "\n":
            chars[i] = " "


def _count_markers(s):
    return sum(1 for rx in _MARKERS for _ in rx.finditer(s))


def _has_marker(s):
    return any(rx.search(s) for rx in _MARKERS)


def mentions(text):
    """Текст → (текст с замаскированными упоминаниями, сколько упоминаний-маркеров скрыто, «вставленный отчёт»?).
    Маска — пробелы той же длины (позиции и проверка отрицаний сохраняются). Правило (mention vs use):
      * маркер в `коде` — всегда упоминание;
      * маркер в пересказе («ассистент ответил …», «заметка советует …», «в отчёте …», «пользователь пишет …», «написано: …»)
        — упоминание до конца предложения; после подписи «слово/фраза/выражение» — только следующая кавычка или маркер;
      * маркер в кавычках «…», "…", “…”, '…' — упоминание, кроме одного случая: он единственный маркер в кавычках в своём
        предложении, вне кавычек в этом предложении есть повелительный глагол («сделай это «на opus»»), и текст не похож
        на вставленный отчёт;
      * вставленный отчёт/цитата: длинный текст с повтором предложений (≥ REPORT_DUP_MIN знаков) или ≥ REPORT_QUOTED_MARKERS
        маркеров в кавычках. В нём повторяющиеся предложения маскируются целиком (это вставка), все кавычки — упоминания,
        а мягкие слова («тщательно», «кратко») не учитываются вовсе (их место — в описании, а не в просьбе)."""
    chars = list(text)
    spans = []
    for rx in QUOTE_RES:
        spans += [(m.start(), m.end(), rx is QUOTE_RES[-1]) for m in rx.finditer(text)]
    spans.sort()
    quotes, last = [], -1
    for a, b, code in spans:                  # без перекрытий: внешняя кавычка, затем следующая
        if a >= last:
            quotes.append((a, b, code))
            last = b
    marked = [(a, b, code) for a, b, code in quotes if _has_marker(text[a:b])]
    skeleton = list(text)
    for a, b, _ in quotes:                    # предложение без содержимого кавычек — для поиска глагола и границ
        for i in range(a + 1, b - 1):
            if skeleton[i] != "\n":
                skeleton[i] = "§"
    skeleton = "".join(skeleton)
    norm = [re.sub(r"\s+", " ", s).strip().lower() for s in re.split(r"(?<=[.!?])\s+|\n+", text)]
    counts = Counter(norm)
    dup = {s for s, n in counts.items() if n > 1 and len(s) >= REPORT_DUP_MIN}
    # отчёт: повтор предложений с маркерами (вставили дважды) или перечисление примеров в кавычках; повтор строк лога без
    # маркеров отчётом не делает (иначе «разберись тщательно» перед логом потерялось бы)
    report = len(text) >= REPORT_MIN_CHARS and (any(_has_marker(s) for s in dup) or len(marked) >= REPORT_QUOTED_MARKERS)
    if report:
        for s in dup:                         # вставленный повтор: маскируем все вхождения предложения
            pat = re.compile(r"\s+".join(re.escape(w) for w in s.split(" ")), re.I | re.U)
            for m in pat.finditer(text):
                _blank(chars, m.start(), m.end())
    ends, n = _sentence_index(skeleton), len(skeleton)
    for m in CITE_RE.finditer(skeleton):
        _, e = _sentence_bounds(ends, n, m.end(), m.end())
        _blank(chars, m.start(), e)
    starts = {a: (a, b, code) for a, b, code in marked}
    labelled = set()
    for m in LABEL_RE.finditer(skeleton):
        if m.end() in starts:                 # слово «ultrathink» — упоминание
            labelled.add(m.end())
            continue
        for rx in _MARKERS:                   # слово ultrathink (без кавычек)
            mk = rx.match(text, m.end())
            if mk:
                _blank(chars, m.start(), mk.end())
                break
    where = [_sentence_bounds(ends, n, a, b) for a, b, _ in marked]
    per_sentence = Counter(where)
    for (a, b, code), (sa, sb) in zip(marked, where):
        same = per_sentence[(sa, sb)]
        rest = skeleton[sa:a] + " " + skeleton[b:sb]
        use = not (code or report or same > 1 or a in labelled) and bool(IMPERATIVE_RE.search(rest.strip()))
        if not use:
            _blank(chars, a, b)
    masked = "".join(chars)
    return masked, _count_markers(text) - _count_markers(masked), report


def _dedup(phrases):
    seen, out = set(), []
    for p in phrases:
        k = re.sub(r"\s+", " ", p).strip().lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out
_INTENT_RES = {k: (w, re.compile(rx, FLAGS_RE)) for k, (w, rx) in INTENTS.items()}

# Нормировки «сырых» счётчиков в 0..1
SIZE_FROM, SIZE_TO = 150, 1500     # знаков прозы: короче — 0, длиннее — 1
ITEMS_FULL = 8                     # столько пунктов списка = максимум структуры
PATHS_FULL = 5                     # столько разных файлов/путей = максимум ширины
STEPS_FULL = 4                     # столько слов-связок шагов = максимум многошаговости
CLAUSES_FULL = 6                   # столько запятых/двоеточий сверх одной = максимум перечисленных требований
CHATTER_MAX_CHARS = 160            # длиннее — уже не реплика, даже если начинается со «спасибо»
MAX_CHARS = 100000                 # сверхдлинный ввод: считаем по началу и концу (скорость регулярных выражений)


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


INTENT_DEFAULT = 0.35               # намерение не распознано — «обычная работа»
REQUIRE_FULL = 4                   # столько «должен/нужно/must» = максимум требований
CONSTRAINT_FULL = 3                # столько ограничений = максимум
DIAG_FULL = 3                      # столько слов диагностики = максимум
UNCERTAIN_FULL = 3
# Вклад сигналов в «глубину» текста (ось effort, 0..1). Подбираются через --calibrate; сумма положительных ≈ 1.
DEPTH_BASE = 0.12
DEPTH_W = {"intent": 0.34, "diag": 0.12, "structure": 0.08, "require": 0.05, "constraints": 0.06, "accept": 0.05,
           "uncertain": 0.05, "critical": 0.12, "scope": 0.05, "math": 0.06, "logs": 0.04, "size": 0.04}
DEPTH_LIGHT = 0.12                 # «лёгкие» слова без «глубоких» — вычитается
DEPTH_SHORT_QUESTION = 0.06        # короткий вопрос (< 120 знаков прозы) — вычитается: ответ, а не работа


def _norm(level):
    """Слово уровня (рус./англ.) → один из EFFORTS."""
    s = level.lower()
    if s in EFFORTS:
        return s
    for k in sorted(EFFORT_WORDS, key=len, reverse=True):
        if s.startswith(k):
            return EFFORT_WORDS[k]
    return None


def _negated(text, start):
    return bool(NEG_BEFORE_RE.search(text[max(0, start - 30):start]))


def _step(level, d):
    i = max(0, min(len(EFFORTS) - 1, EFFORTS.index(level) + d))
    return EFFORTS[i]


def directives(text):
    """Явные указания пользователя в тексте → {"tier", "tier_not", "effort", "effort_min", "effort_max", "phrases"}.
    tier/effort — точный выбор (это согласие, повторный вопрос не нужен); effort_min/effort_max — мягкие границы.
    Отрицания учитываются: «не на opus» → tier_not, «не нужно глубоко» → потолок medium, «не кратко» → пол high.
    Упоминания не считаются (см. mentions): маркеры в кавычках, коде, пересказе и вставленном отчёте; mentions — сколько
    таких скрыто, report — текст похож на вставленный отчёт/цитату. Каждая фраза в phrases — один раз."""
    text, hidden, report = mentions(FENCE_RE.sub(" ", text or "")[:MAX_CHARS])
    out = _directives(text, report)
    out["phrases"] = _dedup(out["phrases"])
    out["tier_not"] = _dedup(out["tier_not"])
    out.update(mentions=hidden, report=report)
    return out


# 2.7.0 (#55): «на модели Haiku» в описании выбора модели («убери подтверждение … то есть на модели Haiku, либо Fable»,
# «например, на opus») — не просьба. Не указание: рядом слова обсуждения выбора модели или перечисление нескольких уровней.
DISCUSS_BEFORE_RE = re.compile(
    r"подтвержд\w*|разрешени\w*|выбор\w*|распредел\w*|\bубер\w*|\bубра\w*|отключ\w*|\bто есть\b|\bт\.\s?е\.|например|\bописан\w*|"
    r"переключ\w*|\bпро\s+модел\w*|\bдля\s+модел\w*|тип\w*\s+модел\w*|(?:выше|ниже|высок\w*|низк\w*|дорог\w*|дёшев\w*)\s+модел\w*|"
    r"примен\w+|использовани\w+|эффективност\w+|возможност\w+|особенност\w+|сравн\w+|оцен\w+|\bразбор\w*|\bизуч\w+|\bисследу\w+|"
    r"\bрасскаж\w+|\bопиши\w*|\bобъясн\w+|проанализируй|анализ\w*|"
    r"which model|choice of|\bconfirm\w*|\be\.g\.|\bi\.e\.|such as|\bselect\w* (?:a )?model", FLAGS_RE)
ENUM_AFTER_RE = re.compile(
    r"^[^.!?\n]{0,12}?(?:,|\bлибо\b|\bили\b|\bи\b|/|\bor\b|\band\b)\s*(?:модел\w+\s+|model\s+)?(?:" + "|".join(TIER_ALIASES.values()) + r")\b", FLAGS_RE)


def _is_discussion(text, mt):
    return bool(DISCUSS_BEFORE_RE.search(text[max(0, mt.start() - 70):mt.start()]) or ENUM_AFTER_RE.match(text[mt.end():mt.end() + 40]))


EFFORT_DISCUSS_RE = re.compile(
    r"сравн\w+|эффективност\w+|примен\w+|использовани\w+|особенност\w+|что такое|что значит|разниц\w+ между|чем отлича\w+|"
    r"compare|difference between|what is", FLAGS_RE)
EFFORT_ENUM_RE = re.compile(r"^\s*(?:,|/|\bи\b|\bили\b|\bvs\b|\band\b|\bor\b)\s*(?:effort\s+)?(?:low|medium|high|xhigh|max)\b", FLAGS_RE)


def _effort_discussed(text, mt):
    return bool(EFFORT_DISCUSS_RE.search(text[max(0, mt.start() - 40):mt.start()]) or EFFORT_ENUM_RE.match(text[mt.end():mt.end() + 20]))


def _directives(text, report=False):
    out = {"tier": None, "tier_not": [], "effort": None, "effort_min": None, "effort_max": None, "phrases": []}
    for mt in TIER_DIRECTIVE_RE.finditer(text):
        if not _negated(text, mt.start()) and _is_discussion(text, mt):
            out["discussed"] = True          # упоминание уровня в обсуждении — не указание
            continue
        word = mt.group("t").lower()
        tier = next(k for k, rx in TIER_ALIASES.items() if re.fullmatch(rx, word, FLAGS_RE))
        if _negated(text, mt.start()):
            out["tier_not"].append(tier)
            out["phrases"].append("не %s" % tier)
        elif out["tier"] in (None, tier):
            out["tier"] = tier
            out["phrases"].append(mt.group(0).strip())
        else:
            out["tier"] = None            # два разных уровня в одном тексте — не угадываем
    hard = []
    for mt in EFFORT_DIRECTIVE_RE.finditer(text):
        lvl = _norm(mt.group("a") or mt.group("b"))
        if lvl and not _negated(text, mt.start()) and _effort_discussed(text, mt):
            out["discussed"] = True      # 2.8 (#65): «сравни эффективность effort max и xhigh» — вопрос про уровень, а не просьба
            continue
        if lvl:
            hard.append((lvl, mt.start(), mt.group(0).strip()))
    for rx, lvl in _HARD:
        for mt in rx.finditer(text):
            hard.append((lvl, mt.start(), mt.group(0).strip()))
    for lvl, start, phrase in hard:
        if _negated(text, start):         # «не нужен effort max» → потолок на ступень ниже; «без low» → пол выше
            if EFFORTS.index(lvl) >= 2:
                out["effort_max"] = _step(lvl, -1)
            else:
                out["effort_min"] = _step(lvl, 1)
            out["phrases"].append("не " + phrase)
        elif out["effort"] in (None, lvl):
            out["effort"] = lvl
            out["phrases"].append(phrase)
        else:
            out["effort"] = None
    lo, hi = [], []
    if report:                            # во вставленном отчёте «тщательно/кратко» — описание, а не просьба
        return out
    for rx, lvl in _SMIN:
        for mt in rx.finditer(text):
            neg = _negated(text, mt.start()) and not re.match(r"не |без ", mt.group(0), FLAGS_RE)
            (hi if neg else lo).append(("medium" if neg else lvl, ("не " if neg else "") + mt.group(0)))
    for rx, lvl in _SMAX:
        for mt in rx.finditer(text):
            neg = _negated(text, mt.start())
            (lo if neg else hi).append(("high" if neg else lvl, ("не " if neg else "") + mt.group(0)))
    if lo and hi:                         # «быстро, но тщательно» — противоречие: мягкие указания не применяем
        out["phrases"].append("противоречивые указания (%s / %s) — не учтены" % (lo[0][1], hi[0][1]))
    elif lo:
        out["effort_min"] = max((x[0] for x in lo), key=EFFORTS.index)
        out["phrases"] += [x[1] for x in lo]
    elif hi:
        out["effort_max"] = min((x[0] for x in hi), key=EFFORTS.index)
        out["phrases"] += [x[1] for x in hi]
    return out


def language(text):
    cyr, lat = len(CYR_RE.findall(text)), len(LAT_RE.findall(text))
    if cyr + lat == 0:
        return "other"
    return "ru" if cyr >= 2 * lat else "en" if lat >= 2 * cyr else "mixed"


def is_retry(text):
    """Признаки повтора после неудачи («опять не работает», «не помогло», "still fails")."""
    return bool(RETRY_RE.search(FENCE_RE.sub(" ", text or "")[:MAX_CHARS]))


def is_continuation(text):
    """Короткое продолжение текущей работы: «продолжай …», «и ещё …», "continue …" (не длиннее CONTINUE_MAX_CHARS)."""
    t = FENCE_RE.sub(" ", (text or "")).strip()
    return len(t) <= CONTINUE_MAX_CHARS and bool(CONTINUE_RE.search(t))


def shared_state_text(text):
    """Признаки общего интерактивного состояния в тексте запроса (браузер пользователя, его вход, CDP) — найденные фразы."""
    t = FENCE_RE.sub(" ", (text or ""))[:MAX_CHARS]
    return sorted({m.group(0).lower() for m in SHARED_TEXT_RE.finditer(t)})[:3]


def _wait_phrase(text):
    """Долгое ожидание: сильное слово («soak», «всю ночь», «подожди», «дождись») или длительность ≥ WAIT_MIN_MINUTES
    с предлогом («на 60 минут», «в течение часа», «каждые 10 мин»). → найденная фраза или None."""
    m = WAIT_STRONG_RE.search(text)
    if m:
        return m.group(0).strip().lower()
    for m in WAIT_DUR_RE.finditer(text):
        if m.group(1) is None:
            return m.group(0).strip().lower()
        try:
            n = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        unit = m.group(2).lower()
        minutes = n * 60 if unit.startswith(("ч", "час", "h")) else n
        if minutes >= WAIT_MIN_MINUTES:
            return m.group(0).strip().lower()
    return None


def device_text(text):
    """Признаки одного общего устройства (эмулятор, телефон, adb) в тексте запроса — найденные слова."""
    t = FENCE_RE.sub(" ", (text or ""))[:MAX_CHARS]
    return sorted({m.group(0).lower() for m in DEVICE_RE.finditer(t)})[:2]


UNITS_RE = re.compile(r"\b(\d{1,3})\s+(?:язык\w*|файл\w*|страниц\w*|раздел\w*|пункт\w*|стран\w*|локал\w*|экран\w*|компонент\w*|модул\w*|"
                      r"тест\w*|шаблон\w*|записей|строк\w*|languages?|files?|pages?|sections?|items?|locales?|screens?|components?|modules?|tests?|templates?)\b", re.I)


def action_signals(text):
    """2.3.0 (#27): признаки для решения «сам / субагент / спросить» по тексту запроса. Упоминания (кавычки, код,
    пересказ, вставленный отчёт) не считаются просьбой. → {agent_req: "agent"|"self"|None, agent_phrase, wait,
    parallel (число частей или 0), refs (ссылки на накопленный контекст), dialog (вопрос-реплика), device}."""
    raw = FENCE_RE.sub(" ", (text or ""))[:MAX_CHARS]
    masked, _hidden, report = mentions(raw)
    for rx in QUOTE_RES:                      # просьба в кавычках — цитата («используй субагента»), а не просьба
        masked = rx.sub(lambda mt: " " * len(mt.group(0)), masked)
    out = {"agent_req": None, "agent_phrase": None, "wait": None, "parallel": 0, "refs": False, "dialog": False,
           "device": device_text(raw), "report": bool(report)}
    m = SELF_REQ_RE.search(masked)
    if m:
        out.update(agent_req="self", agent_phrase=m.group(0).strip().lower())
    else:
        m = AGENT_REQ_RE.search(masked)
        if m and not _negated(masked, m.start()):
            out.update(agent_req="agent", agent_phrase=m.group(0).strip().lower())
    out["wait"] = _wait_phrase(masked)
    out["units"] = max([int(n) for n in UNITS_RE.findall(masked)] or [0])   # «19 языков», «12 файлов»: однотипных единиц работы
    items = len(ITEM_RE.findall(raw))
    if PARALLEL_RE.search(masked):
        out["parallel"] = max(2, items)
    out["refs"] = bool(CONTEXT_REF_RE.search(masked))
    prose = raw.strip()
    intents = {k for k, (_, rx) in _INTENT_RES.items() if rx.search(raw)}
    out["dialog"] = bool(prose.endswith("?") and len(prose) < 160 and not PATH_RE.search(raw)
                         and intents <= {"lookup", "explain"})
    return out


def is_chatter(text):
    """Короткая реплика/подтверждение без поручения («спасибо, давай дальше», «ок, продолжай») — не задача."""
    t = (text or "").strip()
    return len(t) <= CHATTER_MAX_CHARS and bool(CHATTER_RE.match(t)) and not WORK_RE.search(t)


def signals(text):
    """Текст задачи → сырые счётчики + оценки по осям (0..1) + собственная «нагрузка» эвристики.
    Оси совпадают с вопросами TypeSafe: complexity, reasoning, ambiguity, risk, breadth."""
    text = text or ""
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS * 6 // 10] + "\n" + text[-MAX_CHARS * 4 // 10:]
    fences = FENCE_RE.findall(text)
    prose = FENCE_RE.sub(" ", text)
    lines = [ln for ln in prose.split("\n") if ln.strip()]
    code_lines = len(CODE_LINE_RE.findall(prose)) + sum(f.count("\n") for f in fences)
    log_hits = len(LOG_RE.findall(text))
    # длинные серии строк (вставленный лог/вывод) не считаем «прозой» задачи
    prose_chars = sum(len(ln) for ln in lines if len(ln) < 400) if len(lines) < 40 else sum(len(ln) for ln in lines[:20] + lines[-5:])
    items = len(ITEM_RE.findall(prose))
    paths = len({p.lower() for p in PATH_RE.findall(text) if not p.lower().startswith(("http", "www."))})
    steps = len(STEP_RE.findall(prose))
    deep = len(DEEP_RE.findall(prose))
    light = len(LIGHT_RE.findall(prose))
    critical = sorted(k for k, rx in CRITICAL_RES.items() if rx.search(prose))
    question = prose.rstrip().endswith("?")
    has_code = bool(fences) or code_lines >= 3
    has_logs = log_hits >= 3 or "traceback" in text.lower()

    size = clamp((prose_chars - SIZE_FROM) / float(SIZE_TO - SIZE_FROM))
    clauses = prose.count(",") + prose.count(";") + prose.count(":")
    structure = max(clamp(items / float(ITEMS_FULL)), clamp(steps / float(STEPS_FULL)), clamp((clauses - 1) / float(CLAUSES_FULL)))
    width = clamp(paths / float(PATHS_FULL))
    deep_s = clamp(deep / 2.0)
    light_s = 1.0 if light and not deep else 0.0
    crit_s = clamp(len(critical) / 2.0)

    axes = {
        "complexity": clamp(0.10 + 0.30 * size + 0.35 * structure + 0.10 * width + 0.25 * deep_s - 0.15 * light_s),
        "reasoning": clamp(0.20 + 0.55 * deep_s + 0.15 * has_logs + 0.15 * structure - 0.20 * light_s),
        "ambiguity": clamp(0.30 + (0.20 if deep and prose_chars < 200 else 0.0) - 0.15 * light_s),
        "risk": clamp(0.10 + 0.60 * crit_s + (0.10 if "irreversible" in critical else 0.0) - 0.05 * light_s),
        "breadth": clamp(0.10 + 0.50 * width + 0.25 * size + 0.15 * (has_code or has_logs)),
    }
    # ---- ось effort: сколько думать (не «сколько работы») ----
    intents = sorted(k for k, (_, rx) in _INTENT_RES.items() if rx.search(prose))
    intent = max((_INTENT_RES[k][0] for k in intents), default=INTENT_DEFAULT)
    require = len(REQUIRE_RE.findall(prose))
    constraints = len(CONSTRAINT_RE.findall(prose))
    accept = bool(ACCEPT_RE.search(prose))
    uncertain = len(UNCERTAIN_RE.findall(prose))
    diag = len(DIAG_RE.findall(text if has_logs else prose))
    scope = bool(SCOPE_RE.search(prose))
    math = bool(MATH_RE.search(prose))
    parts = {
        "intent": intent, "diag": clamp(diag / float(DIAG_FULL)), "structure": structure,
        "require": clamp(require / float(REQUIRE_FULL)), "constraints": clamp(constraints / float(CONSTRAINT_FULL)),
        "accept": float(accept), "uncertain": clamp(uncertain / float(UNCERTAIN_FULL)), "critical": crit_s,
        "scope": float(scope), "math": float(math), "logs": float(has_logs or has_code), "size": size,
    }
    depth = DEPTH_BASE + sum(DEPTH_W[k] * v for k, v in parts.items())
    depth -= DEPTH_LIGHT * light_s
    if question and prose_chars < 120 and not deep and not diag:
        depth -= DEPTH_SHORT_QUESTION
    return {
        "chars": len(text), "prose_chars": prose_chars, "items": items, "paths": paths, "steps": steps,
        "clauses": clauses, "deep": deep, "light": light, "critical": critical, "question": question,
        "has_code": has_code, "has_logs": has_logs, "chatter": is_chatter(text), "axes": axes,
        "horizon": horizon(prose), "fable_avoid": fable_avoid(prose), "precise": precise_edit(prose),
        "effort": {"depth": round(clamp(depth), 3), "intents": intents, "require": require, "constraints": constraints,
                   "accept": accept, "uncertain": uncertain, "diag": diag, "scope": scope, "math": math,
                   "retry": is_retry(text), "lang": language(prose),
                   "parts": {k: round(v, 2) for k, v in parts.items()}},
    }


# ---------- 2.4.2: принудительный запуск триажа из запроса ----------
# Пользователь сам просит триаж: слэш-вызов скилла, метка в начале («triage:», «!триаж opus/high») или фраза в тексте
# («сделай триаж», «через typesafe-triage»). Принудительный запуск снимает только пропуски хука (короткая реплика,
# «болтовня», команда /… этого скилла, режим «реже»); выбор модели, effort и действия остаётся прежним.
_FORCE_LEVEL = r"(?:haiku|sonnet|opus|fable|low|medium|high|xhigh|max)"
_FORCE_LEVELS = r"%s(?:\s*[/,+]\s*%s|\s+%s)?(?![\w-])" % (_FORCE_LEVEL, _FORCE_LEVEL, _FORCE_LEVEL)
FORCE_SLASH_RE = re.compile(r"^\s*/(?:typesafe-triage:)?typesafe-triage(?=\s|$)[ \t]*", re.I)
# «!triage …» — уровень можно писать через пробел; «triage:opus/high …» — уровень вплотную к двоеточию («triage: high …» — обычный текст)
FORCE_LABEL_RE = re.compile(
    r"^\s*(?:!(?:triage|триаж)(?=\s|$)[ \t]*(?P<bang>%s)?|(?:triage|триаж):(?P<colon>%s)?)[ \t]*" % (_FORCE_LEVELS, _FORCE_LEVELS), re.I)
FORCE_PHRASE_RE = re.compile(
    r"\b(?:с|через|используй|примени|прогони|запусти|сделай|проведи)\s+(?:сначала\s+)?(?:триаж\w*|typesafe[- ]triage)\b"
    r"|\bсначала\s+триаж\b|\b(?:run|use|via|through|do|apply|start)\s+(?:the\s+)?(?:typesafe[- ]triage|triage)\b"
    r"|\btriage\s+(?:this|it|first)\b", re.I)
_TIER_WORDS = ("haiku", "sonnet", "opus", "fable")


def _level_directive(levels):
    """«opus/high», «haiku», «max» → «use opus, effort high: » (форма, которую понимает разбор указаний)."""
    parts = []
    for w in re.findall(_FORCE_LEVEL, levels or "", re.I):
        w = w.lower()
        parts.append("use " + w if w in _TIER_WORDS else "effort " + w)
    return ", ".join(parts) + ": " if parts else ""


def force_trigger(text):
    """Запрос → (способ, текст без метки): способ — "slash" | "label" | "phrase" | None.
    slash: «/typesafe-triage[:typesafe-triage] задача»; label: «triage: …», «триаж: …», «!triage …» с необязательным уровнем
    («triage:opus/high …», «!triage haiku …») — уровень превращается в явное указание модели/effort (это согласие на
    haiku/fable/low/max); phrase: фраза в тексте вне кавычек, `кода` и пересказа (текст не меняется)."""
    t = text or ""
    m = FORCE_SLASH_RE.match(t)
    if m:
        return "slash", t[m.end():].strip()
    m = FORCE_LABEL_RE.match(t)
    if m:
        rest = t[m.end():].strip()
        return "label", (_level_directive(m.group("bang") or m.group("colon")) + rest) if rest else ""
    masked, _hidden, report = mentions(FENCE_RE.sub(" ", t)[:MAX_CHARS])
    for rx in QUOTE_RES:                      # фраза в кавычках или `коде` — цитата, а не просьба
        masked = rx.sub(lambda mt: " " * len(mt.group(0)), masked)
    if not report and FORCE_PHRASE_RE.search(masked):
        return "phrase", t.strip()
    return None, t


# ---------- 2.7.0: признаки из источников выбора модели (references/sources.md) ----------
# R10: Fable — многочасовые агентные сессии, глубокое исследование, изменения по всей кодовой базе, поиск первопричин.
HORIZON_RE = re.compile(
    r"несколько\s+часов|многочасов\w*|\bвсю\s+ночь|\bсутки\b|\bмного\s*дн\w*|по\s+всей\s+(?:кодов\w+\s+баз\w+|кодбаз\w*|репозитори\w+|системе)|"
    r"(?:всю|вся|всей)\s+кодов\w+\s+баз\w+|глубок\w+\s+исследован\w+|первопричин\w+|"
    r"multi-?hour|long[- ]running|codebase-wide|across\s+(?:the\s+)?(?:whole\s+|entire\s+)?(?:codebase|repo)|deep\s+research|root[- ]cause", FLAGS_RE)
# R10: запросы по кибербезопасности и биологии на Fable автоматически перенаправляются на менее мощные модели — платить за неё незачем.
FABLE_AVOID_RE = re.compile(
    r"эксплойт|\bexploit|вредонос|\bmalware|\bransomware|шифровальщик|пентест|\bpentest|\bctf\b|capture the flag|взлом|\bхакер|"
    r"патоген|\bpathogen|биооруж|bioweapon|токсин|\btoxin|нейротоксин|геном\w*|\bgenom\w*|\bcrispr\b|дизайн\w*\s+белк\w+|protein design|"
    r"синтез\w*\s+(?:вируса|патоген)|химическ\w+\s+оруж|chemical weapon|нервно-паралитическ|nerve agent", FLAGS_RE)
# R3: точно описанные правки и вопросы по коду в контексте — рутина для меньшей модели.
PRECISE_EDIT_RE = re.compile(
    r"\bзамени\w*\s+[`\"'«]?\S+[`\"'»]?\s+на\s+[`\"'«]?\S+|\bпереименуй\w*\s+\S+|\b(?:поправь|исправь)\s+опечатк\w+|\bопечатк\w+|"
    r"\b(?:в|на)\s+(?:файле\s+)?\S+\s+(?:в\s+)?строк[еау]\s+\d+|\brename\s+\S+\s+to\s+\S+|\bfix\s+(?:the\s+|a\s+)?typo|"
    r"\bline\s+\d+|\bдобавь\s+(?:одно\s+|ещё одно\s+)?поле\s+\S+|\bbump\s+(?:the\s+)?version|\bизмени\w*\s+(?:значение|название|текст|имя)\s+\S+", FLAGS_RE)
CODE_QUESTION_RE = re.compile(
    r"\bчто\s+делает\s+(?:эта\s+|данная\s+)?(?:функци|класс|метод|команд|строк)|\bгде\s+(?:используется|определ[её]н\w*|объявлен\w*|лежит|находится)|"
    r"\bпокажи\s+(?:файл|функци|где)|\bwhat\s+does\s+(?:this|the)\s+\w+\s+(?:do|mean)|\bwhere\s+is\s+\w+\s+(?:used|defined|declared)", FLAGS_RE)
# R2: причина неудачи — «не знала» (модель мощнее) или «не старалась» (выше effort).
RETRY_EFFORT_RE = re.compile(
    r"пропустил\w*|не\s+(?:запустил|прогнал|проверил|выполнил|дочитал|дописал|доделал|учёл|учел)\w*|забыл\w*|недоделал\w*|бросил\w*|не\s+до\s+конца|"
    r"только\s+часть|половин\w+\s+(?:сделал|работ)\w*|остановил\w*\s+на\s+половине|"
    r"\bskipped\b|didn'?t\s+(?:run|test|check|finish|read)|forgot\s+to|incomplete|half[- ]?done|left\s+out|stopped\s+(?:early|halfway)", FLAGS_RE)
RETRY_KNOWLEDGE_RE = re.compile(
    r"выдумал\w*|придумал\w*|несуществующ\w+|не\s+существует|галлюцин\w*|не\s+понял\w*|не\s+понимает|(?:неправильно|неверно)\s+понял\w*|"
    r"не\s+тот\s+подход|не\s+знает|не\s+разобрал\w*|не\s+видит\s+(?:причин|архитектур)\w*|неверн\w+\s+(?:подход|архитектур|API|предположен)\w*|"
    r"\bhallucinat\w*|made\s+up|doesn'?t\s+exist|misunderstood|wrong\s+(?:approach|assumption|api)|doesn'?t\s+understand|has\s+no\s+idea", FLAGS_RE)


def horizon(text):
    return bool(HORIZON_RE.search(FENCE_RE.sub(" ", text or "")[:MAX_CHARS]))


def fable_avoid(text):
    """Слова кибер/био-тем: для таких запросов Fable не выбирается (они уходят на менее мощные модели)."""
    return sorted({m.group(0).lower() for m in FABLE_AVOID_RE.finditer(FENCE_RE.sub(" ", text or "")[:MAX_CHARS])})[:3]


def precise_edit(text):
    t = FENCE_RE.sub(" ", text or "")[:MAX_CHARS]
    return bool(PRECISE_EDIT_RE.search(t) or CODE_QUESTION_RE.search(t))


def retry_kind(text):
    """Причина неудачи в тексте: "knowledge" (не знала/не поняла/выдумала → модель мощнее), "effort" (пропустила, не запустила,
    не доделала → выше effort), "both" или None (не сказано)."""
    t = FENCE_RE.sub(" ", text or "")[:MAX_CHARS]
    k, e = bool(RETRY_KNOWLEDGE_RE.search(t)), bool(RETRY_EFFORT_RE.search(t))
    return "both" if k and e else "knowledge" if k else "effort" if e else None
