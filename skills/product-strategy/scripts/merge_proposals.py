#!/usr/bin/env python3
"""Склейка черновиков реестра data/proposals-draft-*.json → data/proposals.json с поиском семантических дублей.

  merge_proposals.py <OUT> [--threshold 0.275] [--title-threshold 0.75] [--min N] [--dry-run] [--renumber]
  merge_proposals.py <OUT> --suggest [--top 40]                 только печать пар-кандидатов (смысловые, затем лексические)
  merge_proposals.py <OUT> --pairs pairs.json [--auto] [--pairs-winner given|auto]
  merge_proposals.py <OUT> --pairs-from-dry-run [FILE]          слить только пары, отмеченные в выводе/файле --dry-run
  merge_proposals.py <OUT> --append G7[,G8] [--dry-run] [--allow-merge] [--pairs-from-dry-run [FILE]]
  merge_proposals.py <OUT> --apply-overrides [FILE …]           наложить патчи на готовый data/proposals.json без слияния

Порядок:
1. Читает все data/proposals-draft-<group>.json (список предложений по контракту, id вида <group>-NN).
2. Ручные слияния:
   - --pairs FILE: {"победитель": ["проигравший", …]} — доказательства переносятся (объединение без дублей по
     url/file), теги и зависимости проигравших добавляются, победителю — тег merged:<id проигравшего>, merged_from
     заполняется всегда. С --pairs-winner auto победителя группы выбирает скрипт (правила п. 4). С --pairs
     автоматическое слияние выключено, если не указан --auto.
   - --pairs-from-dry-run [FILE]: решения из build/merge-candidates.json (пишет --dry-run; у записи "merge": true —
     слить) или из сохранённого текстового вывода --dry-run (строки «[x] <снять> «…» → <оставить>»; «[ ]» — не сливать).
     Автослияние выключено (как с --pairs); победитель — как в решении («оставить», по умолчанию выбран так, чтобы не
     ронять минимумы категорий), --pairs-winner auto — пересчитать.
   - build/merge-map.json (необязательно): {"merge": [{"drop": "G2-18", "into": "G4-03", "reason": "…"}],
     "distinct": [["G1-03", "G5-07"]]} или упрощённо {"G2-18": "G4-03"}; distinct запрещает автослияние пары.
   Ручное слияние, роняющее минимум категории, выполняется (это решение человека), но попадает в отчёт
   (min_violations) с подсказкой, кого сделать победителем.
3. Автодедупликация (сходство, см. ниже): пары с баллом ≥ --threshold или с Жаккаром основ названий
   ≥ --title-threshold объединяются в группы (одиночная связь; новая связь принимается, только если среднее сходство
   между группами ≥ 0,5·порога и группа не больше --max-group), затем в каждой группе выбирается победитель.
4. Победитель: (а) слияние не должно ронять минимум категории (check_registry.category_requirements: минимумы от
   strategy.proposals_min или --min, categories_na, профиль): проигравший из категории, которая упала бы ниже
   минимума, не сливается (пометка «не слито» в отчёте); (б) из допустимых — тот, при ком сливается больше
   проигравших; (в) предложение из категории, близкой к минимуму (запас ≤ 2) или уже ниже него; (г) лучший класс
   доказательств (A > B > C > D); (д) более полное описание (число доказательств, длина описания и обоснования,
   шаги); (е) раньше по порядку файлов.
5. Номера P###: если есть build/id-map.json (карта прошлых запусков) и не указан --renumber, предложение сохраняет
   прежний P-id (по своему черновику, затем по влитым); новые получают следующие свободные номера после
   наибольшего из карты (номера слитых не переиспользуются). Без карты или с --renumber — сортировка по категории
   (порядок контракта), файлу, исходному id и перенумерация P001… (прежняя карта → build/id-map.prev.json).
   merged_from — исходный id и id всех влитых черновиков (у не слитых — пусто); зависимости переводятся на новые id.
6. Карта id: build/id-map.json — накопительная {черновик-id: P-id} (дополняется при каждом запуске, в т. ч.
   --append; слитые id → id победителя). По ней в тексте предложений (title, description, rationale, steps,
   evidence[].note и др. строковые поля), dependencies и tags (кроме merged:…) ссылки вида G3-07 переводятся в P-id;
   непереведённые перечисляются (stdout, merge-report.json → unresolved_refs); check_registry.py считает оставшиеся
   ссылки ошибкой. Тем же переводом обновляется data/gap-audit-deps.json (ключи и значения; P-id не меняются).
7. Ручные правки: build/overrides.json — {"P012": {патч}, …} (ключ — P-id или id черновика из карты), применяется
   ПОСЛЕ слияния при каждом запуске и между запусками сохраняется (скрипт файл не меняет). Патч: словари сливаются
   рекурсивно (например, "scores": {"value": 4}), прочие значения заменяются (dependencies, tags, horizon…);
   "_delete": ["seo", "scores.revenue"] — удалить ключи на этом уровне (точка — путь вглубь). Тот же формат
   понимает --apply-overrides FILE (например, build/calibration-patch.json калибровщика).

Сходство пары (a, b), все части 0…1:
  нормализация: нижний регистр, ё → е, слова [a-zа-я0-9]+, стоп-слова RU/EN (служебные слова и общие глаголы
  «сделать/добавить/выпустить…»), «обрезка» окончаний (лёгкий стеммер RU/EN) и усечение основы до 7/8 знаков;
  title_cos — косинус tf-idf основ названий; title_tri — Жаккар символьных триграмм названий;
  desc_cos — косинус tf-idf основ описаний; desc_jac — Жаккар множеств основ описаний;
  full_cos — косинус tf-idf «название ×2 + описание + теги»;
  балл = 0,25·title_cos + 0,15·title_tri + 0,20·desc_cos + 0,10·desc_jac + 0,30·full_cos.
  tf = 1 + ln(частота), idf = ln((1 + N)/(1 + df)) + 1 по всем черновикам прогона (частые слова продукта весят меньше).
  Порог 0,275 откалиброван на реальном прогоне (139 кандидатов, 14 известных слияний): 12 из 14 найдены без ложных.

Смысловые подсказки (второй, локальный проход без сети; только подсказки, автослияний не делает): слова названия
приводятся к каноническим токенам — понятие словаря синонимов RU/EN вместо слова («ярлык/shortcut», «оценка/review»,
«обновление/update», «PWA/манифест»…), класс действия среди первых четырёх слов (создать, интегрировать,
экспортировать, уведомить…), иначе основа слова. Пара — кандидат, если у названий есть общий токен и нет конфликта
объектов (у обоих есть понятия словаря, но ни одного общего — «оценка» ≠ «обновление»). Балл = 0,58·объекты
(idf-взвешенный Жаккар токенов названий; при ≥ 2 общих редких понятиях — не меньше их Жаккара) + 0,28·косинус tf-idf
канонических токенов описания и шагов + 0,10·действие (общее 1, иначе 0,5) + 0,02·та же категория + 0,02·Жаккар
тегов; порог 0,30. На реальном прогоне (203 черновика, 28 ручных слияний) — 18 кандидатов, из них 14 настоящих,
ни одной пары из «distinct». В --suggest печатаются первыми; в отчёте — semantic_candidates; в --dry-run — в списке
решений (не отмечены). Подозрительные автослияния (понятия названий не пересекаются) — semantic_warnings.

--append G7: существующий data/proposals.json сохраняет id; черновики указанных групп сверяются с реестром и между
собой. По умолчанию ничего не вливается: новые получают следующие номера P###, пары-кандидаты (сходство ≥ порог −
0,10, Жаккар названий ≥ --title-threshold или смысловая подсказка) печатаются списком «[ ] новый → существующий» для
ручного решения (--dry-run пишет их в build/merge-candidates.json; решения — --pairs-from-dry-run). --allow-merge —
автослияние дубля в существующее при сходстве ≥ 0,40 (или явном --threshold); дубль из категории ниже минимума не
вливается в другую категорию. Черновики, уже попавшие в реестр (по карте id или merged_from), пропускаются.
Отчёт — stdout и build/merge-report.json (слияния с баллами и причиной выбора победителя, не слитые, кандидаты на
ручную проверку, смысловые подсказки, ручные нарушения минимумов, карта id, непереведённые ссылки, патчи);
--dry-run пишет только отчёт и build/merge-candidates.json. Только стандартная библиотека.
"""
import argparse
import copy
import itertools
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_registry import category_requirements  # noqa: E402

CATEGORY_ORDER = ["product", "acquisition", "conversion", "retention", "monetization", "analytics", "partnerships",
                  "localization", "new_lines", "platform"]
CLASS_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
DEFAULT_THRESHOLD = 0.275
APPEND_THRESHOLD = 0.40       # --append --allow-merge: порог выше (ложное слияние 0,30 «оценка» ↔ «обновление»)
DEFAULT_TITLE_THRESHOLD = 0.75
REVIEW_MARGIN = 0.10          # кандидаты на ручную проверку: балл ≥ порог − 0,10
CHAIN_FACTOR = 0.5            # среднее сходство между группами ≥ 0,5·порога (защита от «цепочек»)
MAX_GROUP = 5
AT_RISK_SLACK = 2             # запас над минимумом категории, при котором победитель берётся из неё
SIM_WEIGHTS = {"title_cos": 0.25, "title_tri": 0.15, "desc_cos": 0.20, "desc_jac": 0.10, "full_cos": 0.30}
SEM_WEIGHTS = {"objects": 0.58, "context": 0.28, "action": 0.10, "category": 0.02, "tags": 0.02}
SEM_MIN = 0.30
GREF_RE = re.compile(r"\bG\d+-\d+\b")          # ссылка на черновик: G3-07, G7-12
REF_SKIP = {"id", "merged_from", "source_group"}
URL_KEYS = {"url", "doc_url", "file"}           # адреса и пути не переводятся
CANDIDATES_FILE = "merge-candidates.json"

STOP = set((
    "и в во на для по с со из к ко о об от у за не ни что как это или при без над под до после чтобы его её ее их "
    "а но же ли бы то так также уже ещё еще все всё весь вся этот эта эти тот та те свой своя свои своё свое "
    "который которая которые которое где когда если чем там тут сам сама сами один одна одно через между "
    "вместо только даже очень более менее можно нужно надо есть нет был была были будет будут ваш ваша ваши наш "
    "сделать сделайте добавить выпустить запустить дать ввести создать показать показывать показывайте перевести "
    "вынести довести открыть открывать сделай давать добавлять "
    "the of to a an for and in on with by from at is are be this that into via or as it its not no your our "
    "add make build create launch ship release new use using get").split())
RU_END = sorted(set((
    "ейшими ейшего ейшему ейшая ейший ость ости остью ами ями ием иями ией ьев ов ев ей ой ий ый ая яя ое ее ие ые "
    "ую юю ого его ому ему ыми ими ых их ом ем ам ям ах ях ию ью ия ья ть ти ет ют ит ят ешь ишь ете ите ут ат ила "
    "ыла ило ыло или ыли ся сь а я о е и ы у ю ь й").split()), key=len, reverse=True)
EN_END = ["ations", "ation", "ings", "ing", "edly", "ed", "ers", "er", "es", "ly", "ments", "ment", "s"]
WORD_RE = re.compile(r"[a-zа-я0-9]+")

# ---------------------------------------------------------------- словари смысловых подсказок (префиксы, RU/EN)
# Префикс до 3 знаков — только целое слово (кириллица — с окончанием до 2 букв): «бот», «боты», но не «ботаник».
ACTION_CLASSES = {
    "create": "добав внедр встро реализ созда сдела запуст выпуст ввест add create build launch introduc implement embed ship",
    "integrate": "интегр подключ синхрониз integrat connect sync",
    "export": "экспорт выгруз export",
    "import": "импорт import",
    "publish": "опублик публик размест выложи publish",
    "localize": "перевест перевод локализ translat locali i18n",
    "notify": "уведом напомин оповещ notif remind alert",
    "share": "подели шеринг расшар share",
    "improve": "улучш ускор оптимиз упрост переработ передел improv optimi speed simplif redesign rework",
    "measure": "измер отслеж трекинг track measur monitor",
    "test": "тестир эксперимент test experiment",
    "open": "открыт открыв open",
    "automate": "автоматиз automat",
    "monetize": "монетиз monetiz charge",
    "invite": "приглас приглаш invite refer",
    "ask": "попрос просьб запрос ask request prompt",
}
OBJECT_CONCEPTS = {
    "shortcut": "ярлык shortcut",
    "pwa": "pwa манифест manifest serviceworker",
    "share_target": "share_target sharetarget",
    "tile": "плитк tile",
    "widget": "виджет widget",
    "mcp": "mcp",
    "github": "github гитхаб",
    "review": "отзыв оценк рейтинг review rating stars звезд",
    "update": "обновлен апдейт update upgrade",
    "notification": "уведомлен пуш push notification напоминан reminder",
    "onboarding": "онбординг onboarding мастер wizard tutorial обучен",
    "pricing": "тариф цен pricing price подписк subscription оплат payment paywall пейвол",
    "trial": "пробн trial триал",
    "referral": "реферал referral приглашен invite",
    "affiliate": "партнерск affiliate партнер partner",
    "export": "экспорт export выгруз",
    "import": "импорт import",
    "pdf": "pdf",
    "spreadsheet": "csv excel xlsx табличн таблиц spreadsheet",
    "api": "api апи sdk webhook вебхук",
    "plugin": "плагин plugin расширени extension addon аддон",
    "browser": "браузер browser chrome firefox",
    "mobile": "мобильн mobile android ios смартфон телефон",
    "desktop": "десктоп desktop windows macos",
    "bot": "бот bot telegram телеграм",
    "messenger": "мессенджер messenger slack discord whatsapp",
    "email": "email почт письм рассылк newsletter digest дайджест",
    "seo": "seo сео поисков",
    "search": "поиск search",
    "landing": "лендинг landing посадочн сайт website",
    "comparison": "сравнен comparison versus альтернатив alternative",
    "docs": "документац docs documentation справк faq гайд guide руководств",
    "video": "видео video youtube ролик shorts",
    "community": "сообществ community форум forum reddit",
    "blog": "блог blog стать article",
    "localization": "английск english локализ перевод i18n язык language locale локал",
    "theme": "темн тема theme dark",
    "offline": "офлайн оффлайн offline",
    "sync": "синхрон sync облак cloud",
    "backup": "бэкап backup резервн",
    "security": "шифрован encrypt безопасн security 2fa двухфактор",
    "auth": "регистрац login signup авторизац sso oauth",
    "analytics": "аналитик analytics метрик metric дашборд dashboard воронк funnel когорт cohort телеметр telemetry",
    "ab_test": "abtest сплит эксперимент experiment",
    "demo": "демо demo песочниц sandbox playground витрин",
    "template": "шаблон template пресет preset",
    "team": "команд team совместн collaborat workspace",
    "license": "лиценз license opensource исходн",
    "install": "установ install инсталлят installer релиз release homebrew winget pypi",
    "store": "магазин store googleplay rustore appstore маркетплейс marketplace",
    "ai": "ии ai llm gpt нейросет",
    "voice": "голос voice речь speech расшифров transcri диктов",
    "calendar": "календар calendar",
    "gamification": "геймиф gamif бейдж badge достижен achievement streak",
    "summary": "итог wrapped сводк summary отчет report",
    "legal": "политик policy соглашен terms оферт gdpr персональн privacy конфиденц ркн",
    "support": "поддержк support helpdesk тикет",
    "performance": "скорост производительн performance быстродейств",
    "accessibility": "доступност accessibility a11y",
    "keyboard": "клавиш hotkey keyboard горяч",
}


def _lexicon(table):
    return {k: v.split() for k, v in table.items()}


ACTIONS = _lexicon(ACTION_CLASSES)
OBJECTS = _lexicon(OBJECT_CONCEPTS)


# ---------------------------------------------------------------- нормализация и сходство
def words(text):
    """Слова текста: нижний регистр, ё → е."""
    return WORD_RE.findall(str(text or "").lower().replace("ё", "е"))


def stem(w):
    """Лёгкая «обрезка» окончаний RU/EN и усечение основы (грубая, но устойчивая к падежам и числам)."""
    if re.fullmatch(r"[а-я]+", w):
        if len(w) >= 6 and w[-2:] in ("ся", "сь"):
            w = w[:-2]
        for e in RU_END:
            if w.endswith(e) and len(w) - len(e) >= 3:
                w = w[:-len(e)]
                break
        return w[:7]
    if re.fullmatch(r"[a-z]+", w):
        for e in EN_END:
            if w.endswith(e) and len(w) - len(e) >= 3:
                w = w[:-len(e)]
                break
        return w[:8]
    return w


def stems(text):
    """Список основ значимых слов (без стоп-слов; кириллица от 3 букв, латиница и цифры от 2)."""
    out = []
    for w in words(text):
        if w in STOP or len(w) < 2 or (len(w) < 3 and re.match(r"[а-я]", w)):
            continue
        out.append(stem(w))
    return out


def trigrams(text):
    """Множество символьных триграмм текста без стоп-слов."""
    s = " %s " % " ".join(w for w in words(text) if w not in STOP)
    return {s[i:i + 3] for i in range(len(s) - 2)} if len(s) > 3 else set()


def tfidf(docs):
    """Нормированные tf-idf векторы (tf = 1 + ln f, idf = ln((1+N)/(1+df)) + 1)."""
    df = Counter()
    for d in docs:
        df.update(set(d))
    n = len(docs)
    idf = {t: math.log((1.0 + n) / (1.0 + c)) + 1.0 for t, c in df.items()}
    vecs = []
    for d in docs:
        v = {t: (1.0 + math.log(c)) * idf[t] for t, c in Counter(d).items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def jaccard(a, b):
    return len(a & b) / float(len(a | b)) if (a or b) else 0.0


class Similarity:
    """Попарное сходство набора предложений (векторы считаются один раз по всему набору)."""

    def __init__(self, props, weights=None):
        self.w = dict(weights or SIM_WEIGHTS)
        self.ids = [str(p.get("id")) for p in props]
        self.pos = {pid: k for k, pid in enumerate(self.ids)}
        T = [stems(p.get("title")) for p in props]
        D = [stems(p.get("description")) for p in props]
        F = [t * 2 + d + stems(" ".join(map(str, p.get("tags") or []))) for t, d, p in zip(T, D, props)]
        self.tset, self.dset = [set(t) for t in T], [set(d) for d in D]
        self.tv, self.dv, self.fv = tfidf(T), tfidf(D), tfidf(F)
        self.tt = [trigrams(p.get("title")) for p in props]

    def parts(self, i, j):
        """Части сходства и итоговый балл пары по индексам."""
        r = {"title_cos": cosine(self.tv[i], self.tv[j]), "title_tri": jaccard(self.tt[i], self.tt[j]),
             "desc_cos": cosine(self.dv[i], self.dv[j]), "desc_jac": jaccard(self.dset[i], self.dset[j]),
             "full_cos": cosine(self.fv[i], self.fv[j])}
        den = sum(self.w.values()) or 1.0
        r["score"] = sum(self.w[k] * r[k] for k in self.w) / den
        r["title_jac"] = jaccard(self.tset[i], self.tset[j])
        return r

    def score(self, a, b):
        """Балл по id."""
        return self.parts(self.pos[a], self.pos[b])["score"]

    def pairs(self, min_score=0.0, idx=None, min_title=0.999):
        """Все пары (i, j, parts) с баллом ≥ min_score или Жаккаром основ названий ≥ min_title, по убыванию балла."""
        idx = list(range(len(self.ids))) if idx is None else idx
        out = []
        for i, j in itertools.combinations(idx, 2):
            r = self.parts(i, j)
            if r["score"] >= min_score or r["title_jac"] >= min_title:
                out.append((i, j, r))
        out.sort(key=lambda x: (-x[2]["score"], self.ids[x[0]], self.ids[x[1]]))
        return out


def rounded(parts):
    return {k: round(v, 3) for k, v in parts.items()}


# ---------------------------------------------------------------- смысловые подсказки (локально)
def _norm_text(text):
    t = str(text or "").lower().replace("ё", "е")
    t = re.sub(r"\ba\s*/\s*b\b", " abtest ", t)
    t = re.sub(r"\b(google|app)\s+(play|store)\b", r" \1\2 ", t)
    t = re.sub(r"\bopen[\s-]+source\b", " opensource ", t)
    t = t.replace("share_target", " sharetarget ")
    return words(t)


def _match(word, prefix):
    if len(prefix) <= 3:
        if word == prefix:
            return True
        return bool(re.fullmatch(r"[а-я]+", prefix)) and word.startswith(prefix) and len(word) <= len(prefix) + 2
    return word.startswith(prefix)


def concepts(text, table=None):
    """Понятия текста по словарю (по умолчанию — объекты)."""
    table = OBJECTS if table is None else table
    found = set()
    for w in _norm_text(text):
        for key, prefixes in table.items():
            if key not in found and any(_match(w, pf) for pf in prefixes):
                found.add(key)
    return found


def actions(title):
    """Классы действия по первым четырём словам названия (глагол или отглагольное существительное)."""
    ws = _norm_text(title)[:4]
    return {k for k, prefixes in ACTIONS.items() if any(_match(w, pf) for w in ws for pf in prefixes)}


def canon_tokens(text, title=False):
    """Канонические токены: понятие словаря (c:…) вместо слова-синонима RU/EN, класс действия (a:…) среди первых
    четырёх слов названия, иначе основа слова (stem) без стоп-слов."""
    toks = []
    for k, w in enumerate(_norm_text(text)):
        obj = [c for c, pf in OBJECTS.items() if any(_match(w, x) for x in pf)]
        if obj:
            toks += ["c:" + c for c in obj]
            continue
        if title and k < 4:
            act = [a for a, pf in ACTIONS.items() if any(_match(w, x) for x in pf)]
            if act:
                toks += ["a:" + a for a in act]
                continue
        if w not in STOP and len(w) >= 2 and not (len(w) < 3 and re.match(r"[а-я]", w)):
            toks.append(stem(w))
    return toks


class SemanticHints:
    """Второй проход подсказок (локально, без сети): «действие + объект» в названии через словарь синонимов RU/EN,
    понятия и основы описания и шагов, категория, теги. Только подсказки — автослияний не делает."""

    def __init__(self, props):
        self.ids = [str(p.get("id")) for p in props]
        self.props = props
        T = [canon_tokens(p.get("title"), title=True) for p in props]
        C = []
        for p in props:
            steps = " ".join("%s %s" % (s.get("what", ""), s.get("how", "")) for s in (p.get("steps") or []) if isinstance(s, dict))
            C.append(canon_tokens("%s %s" % (p.get("description") or "", steps)))
        n = len(props)
        df = Counter()
        for t in T + C:
            df.update(set(t))
        self.idf = {t: math.log((1.0 + 2 * n) / (1.0 + c)) for t, c in df.items()}
        dft = Counter()
        for t in T:
            dft.update(set(t))
        rare = max(3, int(0.05 * n))                  # «редкое» понятие: в названиях не больше max(3, 5 % реестра)
        self.tset = [{x for x in t if not x.startswith("a:")} for t in T]
        self.obj = [{x[2:] for x in t if x.startswith("c:")} for t in self.tset]
        self.rare = [{x for x in o if dft["c:" + x] <= rare} for o in self.obj]
        self.act = [{x[2:] for x in t if x.startswith("a:")} for t in T]
        self.cv = tfidf(C)
        self.cat = [p.get("category") for p in props]
        self.tags = [{str(t).lower() for t in (p.get("tags") or []) if not str(t).startswith("merged:")} for p in props]

    def parts(self, i, j):
        inter = self.tset[i] & self.tset[j]
        if not inter:
            return None
        oi, oj = self.obj[i], self.obj[j]
        if oi and oj and not (oi & oj):               # разные объекты (оценка ≠ обновление) — не дубль
            return None
        ai, aj = self.act[i], self.act[j]
        wj = sum(self.idf[x] for x in inter) / (sum(self.idf[x] for x in self.tset[i] | self.tset[j]) or 1.0)
        ri, rj = self.rare[i], self.rare[j]
        boost = jaccard(ri, rj) if len(ri & rj) >= 2 else 0.0       # синонимы/перевод: ≥ 2 общих редких понятия
        r = {"objects": max(wj, boost),
             "action": 1.0 if ai & aj else 0.5, "context": cosine(self.cv[i], self.cv[j]),
             "category": 1.0 if self.cat[i] and self.cat[i] == self.cat[j] else 0.0,
             "tags": jaccard(self.tags[i], self.tags[j])}
        r["score"] = sum(SEM_WEIGHTS[k] * r[k] for k in SEM_WEIGHTS) / sum(SEM_WEIGHTS.values())
        r["shared"] = sorted(x[2:] if x.startswith("c:") else x for x in inter)
        r["verbs"] = sorted(ai & aj)
        return r

    def pairs(self, min_score=SEM_MIN, idx=None):
        idx = list(range(len(self.ids))) if idx is None else idx
        out = []
        for i, j in itertools.combinations(idx, 2):
            r = self.parts(i, j)
            if r and r["score"] >= min_score:
                out.append((i, j, r))
        out.sort(key=lambda x: (-x[2]["score"], self.ids[x[0]], self.ids[x[1]]))
        return out


def semantic_warnings(pairs, title_of):
    """Автослияния, у которых в названиях есть объекты-понятия, но ни одного общего (вероятно ложное слияние)."""
    out = []
    for a, b in pairs:
        oa, ob = concepts(title_of(a)), concepts(title_of(b))
        if oa and ob and not (oa & ob):
            out.append({"a": a, "b": b, "a_objects": sorted(oa), "b_objects": sorted(ob),
                        "text": "автослияние %s ↔ %s: в названиях разные объекты (%s / %s) — проверьте; запретить — "
                                "build/merge-map.json → distinct" % (a, b, ", ".join(sorted(oa)), ", ".join(sorted(ob)))})
    return out


def semantic_list(props, sim=None, idx=None, min_score=SEM_MIN, limit=60):
    """Смысловые кандидаты [{a, b, semantic, similarity, shared, …}] по убыванию смыслового балла."""
    sem = SemanticHints(props)
    out = []
    for i, j, r in sem.pairs(min_score, idx):
        a, b = sem.ids[i], sem.ids[j]
        lex = sim.score(a, b) if sim is not None and a in sim.pos and b in sim.pos else None
        out.append({"a": a, "b": b, "semantic": round(r["score"], 3), "similarity": None if lex is None else round(lex, 3),
                    "shared": r["shared"], "verbs": r["verbs"], "same_category": bool(r["category"]),
                    "a_title": props[i].get("title"), "b_title": props[j].get("title")})
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- загрузка
def load_drafts(data_dir, groups=None):
    """Список элементов {file, group, p} из черновиков (groups — ограничить группами)."""
    items = []
    files = sorted(data_dir.glob("proposals-draft-*.json"))
    if groups:
        files = [f for f in files if f.stem[len("proposals-draft-"):] in groups]
    for f in files:
        raw = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("proposals", [])
        group = f.stem[len("proposals-draft-"):]
        for k, p in enumerate(raw):
            if not isinstance(p, dict):
                print("пропущен не-объект в %s[%d]" % (f.name, k), file=sys.stderr)
                continue
            if not p.get("id"):
                p["id"] = "%s-%02d" % (group, k + 1)
            p["id"] = str(p["id"])
            items.append({"file": f.name, "group": group, "p": p})
    return files, items


def load_map(path):
    """Ручная карта: (force: {drop_id: (into_id, reason)}, distinct: set(frozenset))."""
    force, distinct = {}, set()
    if not path.exists():
        return force, distinct
    m = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(m, dict) and ("merge" in m or "distinct" in m):
        for e in m.get("merge", []):
            force[e["drop"]] = (e["into"], e.get("reason", "ручная карта"))
        for pair in m.get("distinct", []):
            distinct.add(frozenset(pair))
    elif isinstance(m, dict):
        for k, v in m.items():
            force[k] = (v, "ручная карта") if isinstance(v, str) else (v.get("into"), v.get("reason", "ручная карта"))
    return force, distinct


def load_pairs(path):
    """--pairs: {"победитель": ["проигравший", …]} (строка вместо списка допустима) → [(winner, [losers])]."""
    m = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(m, dict):
        raise ValueError("pairs.json должен быть объектом {\"победитель\": [\"проигравшие\"…]}")
    out = []
    for w, losers in m.items():
        if isinstance(losers, str):
            losers = [losers]
        out.append((str(w), [str(x) for x in losers or [] if str(x) != str(w)]))
    return out


DECISION_LINE = re.compile(r"^\s*(?:[-*]\s*)?\[(.)\]\s+(\S+)(?:\s+«[^»]*»)?\s+(?:→|->)\s+(\S+)")


def load_decisions(path):
    """Решения по выводу --dry-run → [(снять, оставить)] только отмеченных к слиянию.

    JSON (build/merge-candidates.json): список или {"decisions": [...]}, записи {"drop", "keep", "merge": true|false}.
    Текст (сохранённый stdout --dry-run): строки «[x] G7-05 «…» → P012 «…» …»; [x]/[X]/[+] — слить, [ ] — нет."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    out = []
    if data is not None:
        rows = data.get("decisions", []) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError("%s: ожидается список решений или {\"decisions\": [...]}" % path)
        for r in rows:
            if isinstance(r, dict) and r.get("merge") is True and r.get("drop") and r.get("keep"):
                out.append((str(r["drop"]), str(r["keep"])))
        return out
    for line in text.splitlines():
        m = DECISION_LINE.match(line)
        if m and m.group(1) in "xX+":
            out.append((m.group(2).strip("«»,;"), m.group(3).strip("«»,;")))
    return out


def load_config(out_dir):
    p = out_dir / "build" / "run-config.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------- карта id, ссылки, патчи
def draft_sort_key(k):
    m = re.fullmatch(r"G(\d+)-(\d+)", str(k))
    return (0, int(m.group(1)), int(m.group(2)), "") if m else (1, 0, 0, str(k))


def load_id_map(out_dir):
    """Накопительная карта {черновик: P-id}: build/id-map.json; нет — id_map из прежнего build/merge-report.json."""
    p = out_dir / "build" / "id-map.json"
    src = None
    if p.exists():
        try:
            src = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            src = None
    if src is None:
        rp = out_dir / "build" / "merge-report.json"
        try:
            src = (json.loads(rp.read_text(encoding="utf-8")) or {}).get("id_map") if rp.exists() else None
        except (json.JSONDecodeError, AttributeError):
            src = None
    if isinstance(src, dict) and isinstance(src.get("map"), dict):
        src = src["map"]
    if not isinstance(src, dict):
        return {}
    return {str(k): str(v) for k, v in src.items()
            if isinstance(v, str) and str(k) != str(v) and not re.fullmatch(r"P\d+", str(k))}


def save_id_map(out_dir, m):
    (out_dir / "build").mkdir(parents=True, exist_ok=True)
    data = {k: m[k] for k in sorted(m, key=draft_sort_key)}
    (out_dir / "build" / "id-map.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def pnum(pid):
    m = re.fullmatch(r"P(\d+)", str(pid))
    return int(m.group(1)) if m else None


def _translate_str(s, idmap, unresolved, pid, path):
    def rep(m):
        t = idmap.get(m.group(0))
        if t is None:
            unresolved.append({"id": pid, "field": path, "ref": m.group(0)})
            return m.group(0)
        return t
    return GREF_RE.sub(rep, s)


def _walk(v, idmap, unresolved, pid, path):
    if isinstance(v, str):
        return _translate_str(v, idmap, unresolved, pid, path)
    if isinstance(v, list):
        return [_walk(x, idmap, unresolved, pid, "%s[%d]" % (path, k)) for k, x in enumerate(v)]
    if isinstance(v, dict):
        return {k: (x if k in URL_KEYS else _walk(x, idmap, unresolved, pid, "%s.%s" % (path, k))) for k, x in v.items()}
    return v


def translate_refs(props, idmap):
    """Ссылки G\\d+-\\d+ → P-id по карте во всех строковых полях (кроме id, merged_from, source_group и тегов merged:…),
    в dependencies и tags. Возвращает (число изменённых предложений, непереведённые [{id, field, ref}])."""
    unresolved, changed = [], 0
    for p in props:
        pid = p.get("id")
        before = json.dumps(p, ensure_ascii=False, sort_keys=True)
        for k in list(p):
            if k in REF_SKIP:
                continue
            v = p[k]
            if k == "dependencies" and isinstance(v, list):
                new = []
                for d in v:
                    d2 = d
                    if isinstance(d, str) and GREF_RE.fullmatch(d):
                        d2 = idmap.get(d)
                        if d2 is None:
                            unresolved.append({"id": pid, "field": "dependencies", "ref": d})
                            d2 = d
                    if d2 != pid and d2 not in new:
                        new.append(d2)
                p[k] = new
            elif k == "tags" and isinstance(v, list):
                p[k] = [t if (not isinstance(t, str) or t.startswith("merged:"))
                        else _translate_str(t, idmap, unresolved, pid, "tags[%d]" % n) for n, t in enumerate(v)]
            else:
                p[k] = _walk(v, idmap, unresolved, pid, k)
        if json.dumps(p, ensure_ascii=False, sort_keys=True) != before:
            changed += 1
    return changed, unresolved


def remap_gap_deps(out_dir, idmap, write=True):
    """data/gap-audit-deps.json: ключи и значения G\\d+-\\d+ → P-id по карте; P-id не меняются.

    Возвращает {"changed", "unresolved": [ссылки], "missing": bool}."""
    path = out_dir / "data" / "gap-audit-deps.json"
    if not path.exists():
        return {"changed": 0, "unresolved": [], "missing": True}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"changed": 0, "unresolved": [], "missing": False, "error": "не разбирается как JSON"}
    if not isinstance(d, dict):
        return {"changed": 0, "unresolved": [], "missing": False, "error": "не объект"}
    unresolved, changed, out = [], 0, {}

    def tr(x):
        nonlocal changed
        if isinstance(x, str) and GREF_RE.fullmatch(x):
            t = idmap.get(x)
            if t is None:
                unresolved.append(x)
                return x
            changed += 1
            return t
        return x

    for k, v in d.items():
        nk = tr(k)
        lst = out.setdefault(nk, [])
        for x in (v if isinstance(v, list) else [v]):
            nx = tr(x)
            if nx != nk and nx not in lst:
                lst.append(nx)
    if write and changed:
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"changed": changed, "unresolved": sorted(set(unresolved), key=draft_sort_key), "missing": False}


def _delete_path(obj, dotted):
    parts = str(dotted).split(".")
    for part in parts[:-1]:
        if not isinstance(obj, dict) or part not in obj:
            return False
        obj = obj[part]
    if isinstance(obj, dict) and parts[-1] in obj:
        del obj[parts[-1]]
        return True
    return False


def apply_patch(target, patch):
    """Патч на месте: сначала "_delete" (ключи уровня или пути через точку), затем словари — рекурсивно, прочее — замена."""
    for key in patch.get("_delete") or []:
        _delete_path(target, key)
    for k, v in patch.items():
        if k == "_delete":
            continue
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            apply_patch(target[k], v)
        elif isinstance(v, dict):
            target[k] = {}
            apply_patch(target[k], v)
        else:
            target[k] = copy.deepcopy(v)
    return target


def load_overrides(path):
    """build/overrides.json → ({id: патч}, ошибки). Ключи на «_» (комментарии) пропускаются."""
    p = Path(path)
    if not p.exists():
        return {}, []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {}, ["%s не разбирается как JSON: %s" % (p.name, e)]
    if not isinstance(data, dict):
        return {}, ["%s должен быть объектом {\"P012\": {патч}}" % p.name]
    out, errs = {}, []
    for k, v in data.items():
        if str(k).startswith("_"):
            continue
        if not isinstance(v, dict):
            errs.append("%s: патч %s не объект — пропущен" % (p.name, k))
            continue
        out[str(k)] = v
    return out, errs


def apply_overrides(props, overrides, idmap=None, source="overrides.json"):
    """Патчи по P-id (или id черновика из карты). Возвращает (применено [id], неизвестные [ключ], предупреждения)."""
    by_id = {p.get("id"): p for p in props}
    applied, unknown, warns = [], [], []
    for key, patch in overrides.items():
        pid = key if key in by_id else (idmap or {}).get(key)
        if pid not in by_id:
            unknown.append(key)
            warns.append("%s: %s нет в реестре — патч не применён" % (source, key))
            continue
        patch = dict(patch)
        if "id" in patch:
            warns.append("%s: %s — поле id не меняется патчем (пропущено)" % (source, key))
            patch.pop("id")
        apply_patch(by_id[pid], patch)
        applied.append(pid)
    return applied, unknown, warns


# ---------------------------------------------------------------- слияние
def completeness(p):
    """Полнота описания: число доказательств, длина описания и обоснования, шаги."""
    return (len(p.get("evidence") or []), len(str(p.get("description") or "")) + len(str(p.get("rationale") or ""))
            + 40 * len(p.get("steps") or []))


def quality_key(it):
    """Меньше — лучше: класс доказательств, полнота, порядок."""
    p = it["p"]
    comp = completeness(p)
    return (CLASS_RANK.get(p.get("evidence_class"), 9), -comp[0], -comp[1], it["order"])


def absorb(keeper, dup, tag=True):
    """Переносит в keeper id, доказательства (без дублей по url/file), теги, зависимости дубля; тег merged:<id>."""
    kp, dp = keeper["p"], dup["p"]
    keeper["absorbed"] += [dp["id"]] + [x for x in dup["absorbed"] if x != dp["id"]]

    def ekey(e):
        if not isinstance(e, dict):
            return None
        if e.get("url") or e.get("file"):
            return (str(e.get("url") or "").strip().rstrip("/").lower(), str(e.get("file") or "").strip())
        return ("", "", str(e.get("title") or ""), str(e.get("note") or ""))

    seen = {ekey(e) for e in kp.get("evidence") or []}
    for e in dp.get("evidence") or []:
        k = ekey(e)
        if k is not None and k not in seen:
            kp.setdefault("evidence", []).append(e)
            seen.add(k)
    if not isinstance(kp.get("tags"), list):
        kp["tags"] = []
    tags = kp["tags"]
    for t in (dp.get("tags") or []) + (["merged:%s" % dp["id"]] if tag else []):
        if t not in tags:
            tags.append(t)
    for d in dp.get("dependencies") or []:
        if d not in (kp.get("dependencies") or []):
            kp.setdefault("dependencies", []).append(d)


def choose_winner(members, counts, reqs, fixed=None):
    """Победитель группы с учётом минимумов категорий.

    Возвращает (winner, merged_losers, kept_apart[(item, причина)], reason)."""
    cands = [fixed] if fixed is not None else list(members)
    best = None
    for w in cands:
        tmp = Counter(counts)
        ok, apart = [], []
        for l in sorted([m for m in members if m is not w], key=quality_key):
            c = l["p"].get("category")
            need = (reqs.get(c) or {}).get("required") or 0
            if need and tmp[c] >= need and tmp[c] - 1 < need:
                apart.append((l, "уронило бы минимум категории %s (%d при минимуме %d)" % (c, tmp[c], need)))
                continue
            ok.append(l)
            tmp[c] -= 1
        wc = w["p"].get("category")
        need_w = (reqs.get(wc) or {}).get("required") or 0
        slack = counts[wc] - need_w if need_w else 10 ** 6
        at_risk = slack <= AT_RISK_SLACK
        key = (-len(ok), 0 if at_risk else 1, slack if at_risk else 0) + quality_key(w)
        if best is None or key < best[0]:
            best = (key, w, ok, apart, at_risk, slack)
    _, w, ok, apart, at_risk, slack = best
    if fixed is not None:
        reason = "задан вручную"
    elif len(members) - 1 > len(ok) or (apart and len(cands) > 1):
        reason = "максимум слияний без нарушения минимумов категорий"
    elif at_risk and len({m["p"].get("category") for m in members}) > 1:
        wc = w["p"].get("category")
        reason = "категория %s близко к минимуму или ниже (%d при минимуме %d)" % (
            wc, counts[wc], (reqs.get(wc) or {}).get("required") or 0)
    else:
        others = [m for m in members if m is not w]
        wcls = CLASS_RANK.get(w["p"].get("evidence_class"), 9)
        if others and all(wcls < CLASS_RANK.get(m["p"].get("evidence_class"), 9) for m in others):
            reason = "лучший класс доказательств (%s)" % w["p"].get("evidence_class")
        elif others and all(completeness(w["p"]) > completeness(m["p"]) for m in others):
            reason = "более полное описание и доказательства"
        else:
            reason = "равные основания — раньше по порядку"
    return w, ok, apart, reason


def apply_merge(winner, losers, alias, counts):
    for l in losers:
        absorb(winner, l)
        alias[l["p"]["id"]] = winner["p"]["id"]
        counts[l["p"].get("category")] -= 1


def manual_merges(items, by_id, pairs, force, reqs, counts, alias, pairs_winner, origin_name="pairs"):
    """Ручные слияния (--pairs/--pairs-from-dry-run и merge-map). Возвращает (merges, dropped, warnings, min_violations)."""
    merges, dropped, warns, viol = [], [], [], []
    groups = []
    for w, losers in pairs:
        groups.append((w, losers, origin_name))
    for drop, (into, why) in force.items():
        groups.append((into, [drop], "merge-map: " + why))
    for w, losers, origin in groups:
        def live(pid):
            while pid in alias:
                pid = alias[pid]
            return pid
        w_live = live(w)
        missing = [x for x in [w] + losers if x not in by_id]
        if missing:
            warns.append("ручное слияние %s ← %s: нет черновиков %s — пропущено" % (w, ", ".join(losers), ", ".join(missing)))
            continue
        ls = []
        for x in losers:
            lx = live(x)
            if lx != w_live and by_id[lx] not in ls:
                ls.append(by_id[lx])
        if not ls:
            continue
        members = [by_id[w_live]] + ls
        if pairs_winner == "auto" and origin == origin_name:
            winner, ok, apart, reason = choose_winner(members, counts, reqs)
            for it, why in apart:
                warns.append("ручная группа %s: %s не слито — %s" % (w, it["p"]["id"], why))
            ls = ok
            reason = "ручная группа, победитель выбран автоматически: " + reason
        else:
            winner, reason = by_id[w_live], "задан вручную (%s)" % origin
            ls = [m for m in members if m is not winner]
            before = Counter(counts)
            after = Counter(counts)
            for l in ls:
                after[l["p"].get("category")] -= 1
            for c, r in reqs.items():
                need = r.get("required") or 0
                if need and before[c] >= need > after[c]:
                    alt = [m["p"]["id"] for m in members if m["p"].get("category") == c]
                    viol.append({"winner": winner["p"]["id"], "losers": [l["p"]["id"] for l in ls], "category": c,
                                 "before": before[c], "after": after[c], "required": need,
                                 "hint": "сделайте победителем %s или используйте --pairs-winner auto" % ", ".join(alt)})
        apply_merge(winner, ls, alias, counts)
        merges.append({"winner": winner["p"]["id"], "losers": [l["p"]["id"] for l in ls], "score": None,
                       "reason": reason, "manual": True})
        for l in ls:
            dropped.append({"id": l["p"]["id"], "title": l["p"].get("title"), "into": winner["p"]["id"], "similarity": None,
                            "reason": "manual: " + origin})
    return merges, dropped, warns, viol


def auto_merge(alive, sim, thr, title_thr, distinct, reqs, counts, alias, max_group=MAX_GROUP):
    """Автодедупликация по сходству. Возвращает (merges, dropped, not_merged, candidates)."""
    pos = {it["p"]["id"]: k for k, it in enumerate(alive)}
    idx = [sim.pos[it["p"]["id"]] for it in alive]
    pairs = sim.pairs(min(thr - REVIEW_MARGIN, 0.999), idx, min(title_thr, 0.999))
    group = {it["p"]["id"]: {it["p"]["id"]} for it in alive}
    link = {}
    candidates = []
    for i, j, r in pairs:
        a, b = sim.ids[i], sim.ids[j]
        hit = r["score"] >= thr or r["title_jac"] >= title_thr
        if not hit:
            candidates.append({"a": a, "b": b, "similarity": round(r["score"], 3), "parts": rounded(r),
                               "a_title": alive[pos[a]]["p"].get("title"), "b_title": alive[pos[b]]["p"].get("title")})
            continue
        ga, gb = group[a], group[b]
        if ga is gb:
            continue
        if any(frozenset((x, y)) in distinct for x in ga for y in gb):
            candidates.append({"a": a, "b": b, "similarity": round(r["score"], 3), "parts": rounded(r), "note": "distinct",
                               "a_title": alive[pos[a]]["p"].get("title"), "b_title": alive[pos[b]]["p"].get("title")})
            continue
        if len(ga) + len(gb) > max_group:
            candidates.append({"a": a, "b": b, "similarity": round(r["score"], 3), "parts": rounded(r),
                               "note": "группа больше %d" % max_group,
                               "a_title": alive[pos[a]]["p"].get("title"), "b_title": alive[pos[b]]["p"].get("title")})
            continue
        avg = sum(sim.score(x, y) for x in ga for y in gb) / float(len(ga) * len(gb))
        if avg < CHAIN_FACTOR * thr and r["title_jac"] < title_thr:
            candidates.append({"a": a, "b": b, "similarity": round(r["score"], 3), "parts": rounded(r),
                               "note": "цепочка: среднее сходство групп %.3f" % avg,
                               "a_title": alive[pos[a]]["p"].get("title"), "b_title": alive[pos[b]]["p"].get("title")})
            continue
        merged = ga | gb
        for x in merged:
            group[x] = merged
        link.setdefault(frozenset(merged), [])
        for key in (frozenset(ga), frozenset(gb)):
            link[frozenset(merged)] += link.pop(key, [])
        link[frozenset(merged)].append({"a": a, "b": b, "score": round(r["score"], 3), "parts": rounded(r)})
    merges, dropped, not_merged = [], [], []
    clusters = sorted({frozenset(g) for g in group.values() if len(g) > 1},
                      key=lambda g: (-max(e["score"] for e in link.get(g, [{"score": 0}])), sorted(g)))
    for g in clusters:
        members = sorted((alive[pos[x]] for x in g), key=lambda it: it["order"])
        winner, ok, apart, reason = choose_winner(members, counts, reqs)
        edges = link.get(g, [])
        top = max((e["score"] for e in edges), default=None)
        apply_merge(winner, ok, alias, counts)
        if ok:
            merges.append({"winner": winner["p"]["id"], "losers": [l["p"]["id"] for l in ok], "score": top,
                           "pairs": edges, "reason": reason, "manual": False,
                           "categories": {m["p"]["id"]: m["p"].get("category") for m in members}})
        for l in ok:
            sc = max((e["score"] for e in edges if l["p"]["id"] in (e["a"], e["b"])), default=top)
            dropped.append({"id": l["p"]["id"], "title": l["p"].get("title"), "into": winner["p"]["id"],
                            "similarity": sc, "reason": "similarity"})
        for l, why in apart:
            not_merged.append({"id": l["p"]["id"], "title": l["p"].get("title"), "would_merge_into": winner["p"]["id"],
                               "similarity": max((e["score"] for e in edges if l["p"]["id"] in (e["a"], e["b"])), default=top),
                               "reason": why})
    return merges, dropped, not_merged, candidates


def resolve(pid, alias, depth=0):
    while pid in alias and depth < 100:
        pid = alias[pid]
        depth += 1
    return pid


def finalize(kept, prior=None):
    """Номера P###, merged_from. prior — карта прошлых запусков {черновик: P-id} (стабильные номера).

    Возвращает (proposals, id_map исходный → P###)."""
    def key(it):
        cat = it["p"].get("category")
        return (CATEGORY_ORDER.index(cat) if cat in CATEGORY_ORDER else len(CATEGORY_ORDER), it["file"], str(it["p"]["id"]))

    kept = sorted(kept, key=key)
    id_map = {}
    if prior:
        taken = set()
        for it in kept:                                   # 1) свой черновик
            t = prior.get(it["p"]["id"])
            if t and pnum(t) is not None and t not in taken:
                id_map[it["p"]["id"]] = t
                taken.add(t)
        for it in kept:                                   # 2) влитые черновики
            if it["p"]["id"] in id_map:
                continue
            for x in it["absorbed"]:
                t = prior.get(x)
                if t and pnum(t) is not None and t not in taken:
                    id_map[it["p"]["id"]] = t
                    taken.add(t)
                    break
        nxt = max([pnum(v) or 0 for v in prior.values()] + [0]) + 1
        for it in kept:                                   # 3) новые — после наибольшего номера карты
            if it["p"]["id"] not in id_map:
                id_map[it["p"]["id"]] = "P%03d" % nxt
                nxt += 1
        kept = sorted(kept, key=lambda it: pnum(id_map[it["p"]["id"]]))
    else:
        for n, it in enumerate(kept, 1):
            id_map[it["p"]["id"]] = "P%03d" % n
    out = []
    for it in kept:
        p = dict(it["p"])
        orig = p["id"]
        p["id"] = id_map[orig]
        p.setdefault("source_group", it["group"])
        mf = [orig] + [x for x in it["absorbed"] if x != orig]
        p["merged_from"] = list(dict.fromkeys(mf)) if it["absorbed"] else []
        out.append(p)
    return out, id_map


def remap_dependencies(props, id_map, alias, keep_ids=(), fallback=None):
    """Зависимости черновиков → новые id; ссылки на влитые дубли — на держателя; fallback — карта прошлых запусков.
    Возвращает предупреждения."""
    warn = []
    known = set(keep_ids)
    present = {p["id"] for p in props} | known
    for p in props:
        new = []
        for d in p.get("dependencies") or []:
            d = str(d)
            target = id_map.get(resolve(d, alias))
            if target is None and fallback and fallback.get(d) in present:
                target = fallback[d]
            if target is None and (d in known or (not known and re.fullmatch(r"P\d{3,}", d))):
                target = d
            if target is None:
                warn.append("%s: зависимость %r не найдена среди черновиков — удалена" % (p["id"], d))
                continue
            if target != p["id"] and target not in new:
                new.append(target)
        p["dependencies"] = new
    return warn


def prepare(items):
    for k, it in enumerate(items):
        it["order"] = k
        it["absorbed"] = list(it["p"].get("merged_from") or [])
        if it["absorbed"] and it["absorbed"][0] == it["p"]["id"]:
            it["absorbed"] = it["absorbed"][1:]


def print_suggest(sim, items, top, thr):
    by = {it["p"]["id"]: it["p"] for it in items}
    sem = semantic_list([it["p"] for it in items], sim, limit=top)
    print("Смысловые кандидаты (локально: действие + объект в названии, категория, теги, шаги; автослияния нет): %d"
          % len(sem))
    for n, c in enumerate(sem, 1):
        lex = "" if c["similarity"] is None else "; лексика %.3f%s" % (c["similarity"], " ≥ порога" if c["similarity"] >= thr else "")
        print("%3d ~ %.3f  %s [%s] «%s»\n             %s [%s] «%s»\n             общее: %s%s%s"
              % (n, c["semantic"], c["a"], by[c["a"]].get("category"), c["a_title"], c["b"], by[c["b"]].get("category"),
                 c["b_title"], ", ".join(c["shared"]), "; действие: " + ", ".join(c["verbs"]) if c["verbs"] else "", lex))
    rows = sim.pairs(0.0)
    print("Лексические пары по убыванию сходства (порог слияния %.3f); части: title_cos/title_tri/desc_cos/desc_jac/full_cos"
          % thr)
    for n, (i, j, r) in enumerate(rows[:top], 1):
        a, b = sim.ids[i], sim.ids[j]
        mark = "≥" if r["score"] >= thr else " "
        print("%3d %s %.3f  %s [%s] «%s»\n             %s [%s] «%s»\n             %.2f/%.2f/%.2f/%.2f/%.2f"
              % (n, mark, r["score"], a, by[a].get("category"), by[a].get("title"), b, by[b].get("category"),
                 by[b].get("title"), r["title_cos"], r["title_tri"], r["desc_cos"], r["desc_jac"], r["full_cos"]))
    print("Шаблон ручных пар: {\"победитель\": [\"проигравший\"]} → --pairs build/merge-pairs.json")


def write_decisions(out_dir, decisions, mode):
    """build/merge-candidates.json — решения для --pairs-from-dry-run (merge: true — слить)."""
    (out_dir / "build").mkdir(parents=True, exist_ok=True)
    doc = {"mode": mode, "help": "merge: true — слить drop в keep; затем merge_proposals.py <OUT> %s--pairs-from-dry-run"
                                 % ("--append <группы> " if mode == "append" else ""),
           "decisions": decisions}
    (out_dir / "build" / CANDIDATES_FILE).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def print_decisions(decisions):
    if not decisions:
        return
    print("Решения (отметьте [x] — слить, [ ] — оставить раздельно; файл build/%s или сохранённый вывод → "
          "--pairs-from-dry-run):" % CANDIDATES_FILE)
    for d in decisions:
        sim = "" if d.get("similarity") is None else "сходство %.2f" % d["similarity"]
        sem = "" if d.get("semantic") is None else "смысл %.2f" % d["semantic"]
        print("  [%s] %s «%s» → %s «%s» (%s; %s)" % ("x" if d["merge"] else " ", d["drop"], d.get("drop_title") or "",
                                                  d["keep"], d.get("keep_title") or "", ", ".join(x for x in (sim, sem) if x) or "—",
                                                  d.get("source")))


def finish_common(out_dir, props, run_map, prior, a, report, warns):
    """Общий хвост: карта id, патчи overrides.json, перевод ссылок, gap-audit-deps.json. Меняет props на месте."""
    acc = dict(prior)
    acc.update(run_map)
    ov, ov_err = load_overrides(out_dir / "build" / "overrides.json")
    warns += ov_err
    applied, unknown, ov_warn = apply_overrides(props, ov, acc)
    warns += ov_warn
    changed, unresolved = translate_refs(props, acc)
    gap = remap_gap_deps(out_dir, acc, write=not a.dry_run)
    report.update({"id_map": acc, "id_map_run": run_map, "translated_refs": changed, "unresolved_refs": unresolved,
                   "overrides": {"file": "build/overrides.json" if ov or ov_err else None, "applied": applied, "unknown": unknown},
                   "gap_audit_deps": gap})
    if applied:
        print("Патчи build/overrides.json применены: %s" % ", ".join(applied))
    if changed:
        print("Ссылки на черновики переведены в P-id в %d предложениях" % changed)
    if unresolved:
        print("  ! непереведённые ссылки на черновики (%d): %s" % (
            len(unresolved), "; ".join("%s.%s → %s" % (u["id"], u["field"], u["ref"]) for u in unresolved[:20])
            + (" …" if len(unresolved) > 20 else "")))
    if gap.get("changed"):
        print("data/gap-audit-deps.json: переведено ссылок %d%s" % (gap["changed"], " (--dry-run, файл не менялся)" if a.dry_run else ""))
    if gap.get("unresolved"):
        print("  ! data/gap-audit-deps.json: непереведённые %s" % ", ".join(gap["unresolved"]))
    if not a.dry_run:
        save_id_map(out_dir, acc)
    return acc


def run_append(out_dir, a, cfg, reqs):
    """--append: новые черновики указанных групп к существующему реестру без перенумерации."""
    reg_path = out_dir / "data" / "proposals.json"
    if not reg_path.exists():
        print("нет data/proposals.json — сначала обычное слияние", file=sys.stderr)
        return 1
    existing = [p for p in json.loads(reg_path.read_text(encoding="utf-8")) if isinstance(p, dict) and p.get("id")]
    groups = {g.strip() for g in a.append.split(",") if g.strip()}
    files, new_items = load_drafts(out_dir / "data", groups)
    if not new_items:
        print("нет черновиков групп %s" % ", ".join(sorted(groups)), file=sys.stderr)
        return 1
    old_ids = {p["id"] for p in existing}
    prior = load_id_map(out_dir)
    for p in existing:                                   # восстановить карту по merged_from (реестры до id-map.json)
        for x in (p.get("merged_from") or []):
            if x != p["id"] and not re.fullmatch(r"P\d+", str(x)):
                prior.setdefault(str(x), p["id"])
    skipped = [it for it in new_items if prior.get(it["p"]["id"]) in old_ids]
    new_items = [it for it in new_items if prior.get(it["p"]["id"]) not in old_ids]
    for it in skipped:
        print("  уже в реестре: %s → %s — пропущено" % (it["p"]["id"], prior[it["p"]["id"]]))
    old_items = [{"file": "proposals.json", "group": p.get("source_group") or "", "p": p} for p in existing]
    prepare(old_items + new_items)
    for it in old_items:
        it["absorbed"] = [x for x in (it["p"].get("merged_from") or [])[1:]]
    sim = Similarity([it["p"] for it in old_items + new_items])
    counts = Counter(p.get("category") for p in existing)
    alias, merges, dropped, not_merged, warns = {}, [], [], [], []
    by_id = {it["p"]["id"]: it for it in old_items + new_items}
    thr = a.threshold if a.threshold is not None else APPEND_THRESHOLD
    title_thr = a.title_threshold
    decisions_in = None
    if a.pairs_from_dry_run:
        try:
            decisions_in = {d: k for d, k in load_decisions(a.pairs_from_dry_run)}
        except (OSError, ValueError) as e:
            print("не прочитать решения %s: %s" % (a.pairs_from_dry_run, e), file=sys.stderr)
            return 1
    new_kept = []
    new_ids = {it["p"]["id"] for it in new_items}

    def do_merge(keeper, it, r, reason, kind):
        absorb(keeper, it)
        alias[it["p"]["id"]] = keeper["p"]["id"]
        merges.append({"winner": keeper["p"]["id"], "losers": [it["p"]["id"]],
                       "score": None if r is None else round(r["score"], 3), "parts": None if r is None else rounded(r),
                       "reason": reason, "manual": kind != "append-similarity"})
        dropped.append({"id": it["p"]["id"], "title": it["p"].get("title"), "into": keeper["p"]["id"],
                        "similarity": None if r is None else round(r["score"], 3), "reason": kind})

    for it in new_items:
        iid = it["p"]["id"]
        c = it["p"].get("category")
        need = (reqs.get(c) or {}).get("required") or 0
        if decisions_in is not None:
            target = decisions_in.get(iid)
            if target:
                target = resolve(target, alias)
                keeper = by_id.get(target)
                if keeper is None or (target in new_ids and keeper not in new_kept):
                    warns.append("решение %s → %s: нет такого предложения среди реестра и новых — добавлено отдельно"
                                 % (iid, target))
                else:
                    if need and counts[c] < need and keeper["p"].get("category") != c:
                        warns.append("решение %s → %s: категория %s ниже минимума (%d < %d) — слито по решению человека"
                                     % (iid, target, c, counts[c], need))
                    do_merge(keeper, it, None, "append: решение из --pairs-from-dry-run", "append-decision")
                    continue
        elif a.allow_merge:
            best = None
            for other in old_items + new_kept:
                r = sim.parts(sim.pos[iid], sim.pos[other["p"]["id"]])
                if r["score"] >= thr or r["title_jac"] >= title_thr:
                    if best is None or r["score"] > best[1]["score"]:
                        best = (other, r)
            if best is not None:
                keeper, r = best
                kc = keeper["p"].get("category")
                if need and counts[c] < need and kc != c:
                    not_merged.append({"id": iid, "title": it["p"].get("title"), "would_merge_into": keeper["p"]["id"],
                                       "similarity": round(r["score"], 3),
                                       "reason": "категория %s ниже минимума (%d < %d) — добавлено отдельно" % (c, counts[c], need)})
                elif keeper["p"]["id"] in new_ids:            # дубль среди новых — победитель по правилам минимумов
                    tmp = Counter(counts)
                    tmp[c] += 1
                    w, ok, apart, why = choose_winner([keeper, it], tmp, reqs)
                    if not ok:
                        not_merged.append({"id": iid, "title": it["p"].get("title"), "would_merge_into": keeper["p"]["id"],
                                           "similarity": round(r["score"], 3), "reason": apart[0][1] if apart else "минимум"})
                    elif w is it:                              # новый лучше — он занимает место прежнего нового
                        new_kept[new_kept.index(keeper)] = it
                        counts[kc] -= 1
                        counts[c] += 1
                        do_merge(it, keeper, r, "append: дубль среди новых; " + why, "append-similarity")
                        continue
                    else:
                        do_merge(keeper, it, r, "append: дубль среди новых; " + why, "append-similarity")
                        continue
                else:
                    do_merge(keeper, it, r, "append: существующее предложение сохраняется", "append-similarity")
                    continue
        new_kept.append(it)
        counts[c] += 1
    # кандидаты на ручное решение (по всем новым, кроме уже слитых)
    decisions = []
    for m in merges:
        for l in m["losers"]:
            decisions.append({"drop": l, "keep": m["winner"], "merge": True, "similarity": m["score"], "semantic": None,
                              "drop_title": by_id[l]["p"].get("title"), "keep_title": by_id[m["winner"]]["p"].get("title"),
                              "source": "auto" if not m["manual"] else "decision"})
    merged_new = set(alias)
    seen = {(d["drop"], d["keep"]) for d in decisions}
    all_props = [it["p"] for it in old_items + new_items]
    pos_all = {p["id"]: k for k, p in enumerate(all_props)}
    order = {it["p"]["id"]: k for k, it in enumerate(old_items + new_items)}
    sem = SemanticHints(all_props)
    cand = {}
    for it in new_items:
        iid = it["p"]["id"]
        if iid in merged_new:
            continue
        for other in old_items + new_items:
            oid = other["p"]["id"]
            if oid == iid or oid in merged_new or (oid in new_ids and order[oid] > order[iid]):
                continue
            r = sim.parts(sim.pos[iid], sim.pos[oid])
            s = sem.parts(pos_all[iid], pos_all[oid])
            lex_hit = r["score"] >= thr - REVIEW_MARGIN or r["title_jac"] >= title_thr
            sem_hit = s is not None and s["score"] >= SEM_MIN
            if not (lex_hit or sem_hit) or (iid, oid) in seen:
                continue
            e = {"drop": iid, "keep": oid, "merge": False, "similarity": round(r["score"], 3),
                 "semantic": round(s["score"], 3) if s else None, "drop_title": it["p"].get("title"),
                 "keep_title": other["p"].get("title"),
                 "source": "+".join(x for x, f in (("lexical", lex_hit), ("semantic", sem_hit)) if f)}
            prev = cand.get(iid)
            if prev is None or max(e["similarity"], e["semantic"] or 0) > max(prev["similarity"], prev["semantic"] or 0):
                cand[iid] = e
    candidates = sorted(cand.values(), key=lambda d: -max(d["similarity"], d["semantic"] or 0))
    decisions += candidates
    # номера
    nums = [pnum(pid) for pid in old_ids if pnum(pid) is not None]
    nums += [pnum(v) for v in prior.values() if pnum(v) is not None]
    nxt = max(nums or [0]) + 1
    id_map = {pid: pid for pid in old_ids}
    for it in new_kept:
        id_map[it["p"]["id"]] = "P%03d" % nxt
        nxt += 1
    out = []
    for it in old_items:
        p = dict(it["p"])
        if it["absorbed"]:
            base = (p.get("merged_from") or [])[:1] or [p["id"]]
            p["merged_from"] = list(dict.fromkeys(base + it["absorbed"]))
        out.append(p)
    added = []
    for it in new_kept:
        p = dict(it["p"])
        orig = p["id"]
        p["id"] = id_map[orig]
        p.setdefault("source_group", it["group"])
        p["merged_from"] = list(dict.fromkeys([orig] + it["absorbed"])) if it["absorbed"] else []
        added.append(p)
    warns += remap_dependencies(added, id_map, alias, keep_ids=old_ids | set(id_map.values()), fallback=prior)
    run_map = {}
    for it in new_kept:
        run_map[it["p"]["id"]] = id_map[it["p"]["id"]]
        for x in it["absorbed"]:
            run_map.setdefault(x, id_map[it["p"]["id"]])
    for old, tgt in alias.items():
        run_map[old] = id_map.get(resolve(tgt, alias), resolve(tgt, alias))
    sem_warn = semantic_warnings([(m["winner"], l) for m in merges if not m["manual"] for l in m["losers"]],
                                 lambda x: by_id[x]["p"].get("title"))
    for w in sem_warn:
        print("  ? " + w["text"])
    report = {"mode": "append", "semantic_warnings": sem_warn, "groups": sorted(groups), "files": [f.name for f in files], "existing": len(existing),
              "loaded": len(new_items) + len(skipped), "skipped_already_in_registry": [it["p"]["id"] for it in skipped],
              "added": [p["id"] for p in added], "kept": len(out) + len(added), "allow_merge": bool(a.allow_merge),
              "pairs_from_dry_run": a.pairs_from_dry_run, "merges": merges, "dropped": dropped, "not_merged": not_merged,
              "candidates": candidates, "threshold": thr, "title_threshold": title_thr, "warnings": warns,
              "dry_run": a.dry_run}
    print("Дописано к реестру: %d новых из %d черновиков (%s); слито с существующими: %d%s"
          % (len(added), len(new_items), ", ".join(sorted(groups)), len(dropped),
             "" if (a.allow_merge or decisions_in is not None) else " (автослияние выключено; --allow-merge — включить)"))
    for d in dropped:
        print("  слито %s «%s» → %s%s" % (d["id"], d["title"], d["into"],
                                         "" if d["similarity"] is None else " (сходство %.2f)" % d["similarity"]))
    for nm in not_merged:
        print("  не слито %s «%s» (с %s): %s" % (nm["id"], nm["title"], nm["would_merge_into"], nm["reason"]))
    if candidates:
        print("Пары-кандидаты для ручного решения: %d" % len(candidates))
    print_decisions(decisions)
    all_props = out + added
    finish_common(out_dir, all_props, run_map, prior, a, report, warns)
    for w in warns:
        print("  ! " + w)
    (out_dir / "build").mkdir(parents=True, exist_ok=True)
    (out_dir / "build" / "merge-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.dry_run:
        write_decisions(out_dir, decisions, "append")
        print("Записано: build/merge-report.json, build/%s (--dry-run, реестр не менялся)" % CANDIDATES_FILE)
        return 0
    reg_path.write_text(json.dumps(all_props, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Записано: data/proposals.json, build/merge-report.json, build/id-map.json")
    return 0


def run_apply_overrides(out_dir, files):
    """--apply-overrides: патчи к готовому data/proposals.json (без слияния)."""
    reg = out_dir / "data" / "proposals.json"
    if not reg.exists():
        print("нет data/proposals.json", file=sys.stderr)
        return 1
    props = [p for p in json.loads(reg.read_text(encoding="utf-8")) if isinstance(p, dict)]
    idmap = load_id_map(out_dir)
    files = files or [str(out_dir / "build" / "overrides.json")]
    total, bad = [], 0
    for f in files:
        ov, errs = load_overrides(f)
        if not Path(f).exists():
            errs.append("нет файла %s" % f)
        for e in errs:
            print("  ! " + e)
            bad += 1
        applied, unknown, warns = apply_overrides(props, ov, idmap, Path(f).name)
        for w in warns:
            print("  ! " + w)
        total += applied
        print("%s: применено %d, неизвестных id %d" % (Path(f).name, len(applied), len(unknown)))
    changed, unresolved = translate_refs(props, idmap)
    for u in unresolved[:20]:
        print("  ! непереведённая ссылка %s.%s → %s" % (u["id"], u["field"], u["ref"]))
    reg.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Записано: data/proposals.json (патчей %d)" % len(total))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Склейка черновиков реестра с поиском дублей и перенумерацией.")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--threshold", type=float, default=None,
                    help="порог объединённого сходства (%.3f; с --append --allow-merge — %.2f)" % (DEFAULT_THRESHOLD, APPEND_THRESHOLD))
    ap.add_argument("--title-threshold", type=float, default=DEFAULT_TITLE_THRESHOLD,
                    help="порог Жаккара основ названий — сливать почти одинаковые названия (0.75)")
    ap.add_argument("--min", type=int, default=None, help="минимум предложений для минимумов категорий (иначе run-config или 100)")
    ap.add_argument("--max-group", type=int, default=MAX_GROUP, help="наибольший размер группы дублей (5)")
    ap.add_argument("--pairs", help="JSON ручных пар {\"победитель\": [\"проигравшие\"…]}")
    ap.add_argument("--pairs-from-dry-run", nargs="?", const="__default__", default=None, metavar="FILE",
                    help="решения из build/merge-candidates.json (по умолчанию) или сохранённого вывода --dry-run")
    ap.add_argument("--pairs-winner", choices=["given", "auto"], default="given",
                    help="given — победитель как в файле; auto — выбрать по правилам (минимумы категорий, класс, полнота)")
    ap.add_argument("--auto", action="store_true", help="с --pairs: дополнительно автослияние по сходству")
    ap.add_argument("--no-auto", action="store_true", help="без автослияния (только ручные карты)")
    ap.add_argument("--suggest", action="store_true", help="только напечатать пары-кандидаты (смысловые, затем лексические)")
    ap.add_argument("--top", type=int, default=40, help="сколько пар печатать в --suggest (40)")
    ap.add_argument("--append", help="группы черновиков через запятую — дописать к готовому data/proposals.json")
    ap.add_argument("--allow-merge", action="store_true", help="с --append: вливать дубли в существующие (порог 0,40)")
    ap.add_argument("--renumber", action="store_true", help="перенумеровать P001… заново, без прежней карты id")
    ap.add_argument("--apply-overrides", nargs="*", default=None, metavar="FILE",
                    help="наложить патчи (по умолчанию build/overrides.json) на готовый реестр без слияния")
    ap.add_argument("--dry-run", action="store_true", help="только отчёт и build/merge-candidates.json, без записи реестра")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    if a.pairs_from_dry_run == "__default__":
        a.pairs_from_dry_run = str(out_dir / "build" / CANDIDATES_FILE)
    if a.apply_overrides is not None:
        return run_apply_overrides(out_dir, a.apply_overrides)
    cfg = load_config(out_dir)
    min_n = a.min if a.min is not None else (cfg.get("strategy") or {}).get("proposals_min") or 100
    reqs = category_requirements(cfg, min_n)
    if a.append:
        return run_append(out_dir, a, cfg, reqs)
    if a.threshold is None:
        a.threshold = DEFAULT_THRESHOLD
    files, items = load_drafts(out_dir / "data")
    if not files:
        print("нет черновиков data/proposals-draft-*.json в %s" % out_dir, file=sys.stderr)
        return 1
    dup_ids = [k for k, v in Counter(it["p"]["id"] for it in items).items() if v > 1]
    if dup_ids:
        print("повторяющиеся id черновиков: %s — исправьте до слияния" % ", ".join(sorted(dup_ids)), file=sys.stderr)
        return 1
    prepare(items)
    sim = Similarity([it["p"] for it in items])
    if a.suggest:
        print_suggest(sim, items, a.top, a.threshold)
        return 0
    by_id = {it["p"]["id"]: it for it in items}
    force, distinct = load_map(out_dir / "build" / "merge-map.json")
    pairs = load_pairs(a.pairs) if a.pairs else []
    origin = "pairs"
    if a.pairs_from_dry_run:
        try:
            dec = load_decisions(a.pairs_from_dry_run)
        except (OSError, ValueError) as e:
            print("не прочитать решения %s: %s" % (a.pairs_from_dry_run, e), file=sys.stderr)
            return 1
        grouped = {}
        for drop, keep in dec:
            grouped.setdefault(keep, []).append(drop)
        pairs += list(grouped.items())
        origin = "pairs" if a.pairs else "dry-run"
    counts = Counter(it["p"].get("category") for it in items)
    counts_before = dict(counts)
    alias = {}
    m_merges, m_dropped, warns, viol = manual_merges(items, by_id, pairs, force, reqs, counts, alias, a.pairs_winner,
                                                     origin_name=origin)
    alive = [it for it in items if it["p"]["id"] not in alias]
    do_auto = not a.no_auto and (not (a.pairs or a.pairs_from_dry_run) or a.auto)
    if do_auto:
        a_merges, a_dropped, not_merged, candidates = auto_merge(alive, sim, a.threshold, a.title_threshold, distinct,
                                                                 reqs, counts, alias, a.max_group)
    else:
        a_merges, a_dropped, not_merged, candidates = [], [], [], []
    alive_after = [it for it in items if it["p"]["id"] not in alias]
    sem_warn = semantic_warnings([(e["a"], e["b"]) for m in a_merges for e in m.get("pairs") or []],
                                 lambda x: by_id[x]["p"].get("title"))
    sem = semantic_list([it["p"] for it in items], sim, idx=[sim.pos[it["p"]["id"]] for it in alive_after])
    kept = alive_after
    prior_file = load_id_map(out_dir)
    prior = {} if a.renumber else prior_file
    if a.renumber and prior_file and not a.dry_run:
        (out_dir / "build").mkdir(parents=True, exist_ok=True)
        (out_dir / "build" / "id-map.prev.json").write_text(json.dumps(prior_file, ensure_ascii=False, indent=2), encoding="utf-8")
    props, id_map = finalize(kept, prior)
    warns += remap_dependencies(props, id_map, alias, fallback=prior)
    full_map = dict(id_map)
    for it in kept:
        for x in it["absorbed"]:
            full_map.setdefault(x, id_map[it["p"]["id"]])
    for old in alias:
        tgt = resolve(old, alias)
        if tgt in id_map:
            full_map[old] = id_map[tgt]
    for m in m_merges + a_merges:
        m["winner_new_id"] = id_map.get(m["winner"])
    dropped = m_dropped + a_dropped
    for d in dropped:
        d["into"] = resolve(d["into"], alias)
    decisions = []
    title = {it["p"]["id"]: it["p"].get("title") for it in items}
    for m in m_merges + a_merges:
        for l in m["losers"]:
            decisions.append({"drop": l, "keep": m["winner"], "merge": True, "similarity": m["score"], "semantic": None,
                              "drop_title": title.get(l), "keep_title": title.get(m["winner"]),
                              "source": "manual" if m["manual"] else "auto"})
    seen = {frozenset((d["drop"], d["keep"])) for d in decisions}
    for c in sorted(candidates, key=lambda c: -c["similarity"]):
        if frozenset((c["a"], c["b"])) not in seen and c["a"] not in alias and c["b"] not in alias:
            seen.add(frozenset((c["a"], c["b"])))
            decisions.append({"drop": c["b"], "keep": c["a"], "merge": False, "similarity": c["similarity"], "semantic": None,
                              "drop_title": c["b_title"], "keep_title": c["a_title"], "source": "lexical" + (" (%s)" % c["note"] if c.get("note") else "")})
    for c in sem:
        if frozenset((c["a"], c["b"])) not in seen:
            seen.add(frozenset((c["a"], c["b"])))
            decisions.append({"drop": c["b"], "keep": c["a"], "merge": False, "similarity": c["similarity"],
                              "semantic": c["semantic"], "drop_title": c["b_title"], "keep_title": c["a_title"],
                              "source": "semantic: " + ", ".join(c["shared"])})
    report = {"files": [f.name for f in files], "loaded": len(items), "kept": len(props), "threshold": a.threshold,
              "title_threshold": a.title_threshold, "similarity_weights": SIM_WEIGHTS, "auto": do_auto,
              "pairs_file": a.pairs, "pairs_from_dry_run": a.pairs_from_dry_run, "pairs_winner": a.pairs_winner, "min": min_n,
              "renumber": bool(a.renumber or not prior), "merges": m_merges + a_merges, "dropped": dropped,
              "not_merged": not_merged, "candidates": sorted(candidates, key=lambda c: -c["similarity"])[:60],
              "semantic_candidates": sem, "semantic_warnings": sem_warn, "min_violations": viol,
              "category_counts": {"before": counts_before, "after": dict(Counter(p.get("category") for p in props)),
                                  "required": {c: r["required"] for c, r in reqs.items()}},
              "warnings": warns, "dry_run": a.dry_run}
    print("Загружено %d из %d файлов; оставлено %d, слито %d%s"
          % (len(items), len(files), len(props), len(dropped), "" if do_auto else " (автослияние выключено)"))
    for m in m_merges + a_merges:
        sc = "" if m["score"] is None else " (сходство %.3f)" % m["score"]
        print("  %s ← %s%s; победитель: %s" % (m["winner"], ", ".join(m["losers"]), sc, m["reason"]))
    for nm in not_merged:
        print("  не слито %s «%s» (с %s): %s" % (nm["id"], nm["title"], nm["would_merge_into"], nm["reason"]))
    for v in viol:
        print("  ! ручное слияние %s ← %s роняет минимум %s: %d → %d < %d; %s"
              % (v["winner"], ", ".join(v["losers"]), v["category"], v["before"], v["after"], v["required"], v["hint"]))
    if candidates:
        print("Пары на ручную проверку (близко к порогу): %d — см. build/merge-report.json или --suggest" % len(candidates))
    for w in sem_warn:
        print("  ? " + w["text"])
    if sem:
        print("Смысловые подсказки (без автослияния): %d — см. build/merge-report.json → semantic_candidates или --suggest" % len(sem))
    if a.dry_run:
        print_decisions(decisions)
    finish_common(out_dir, props, full_map, prior, a, report, warns)
    for w in warns:
        print("  ! " + w)
    (out_dir / "build").mkdir(parents=True, exist_ok=True)
    (out_dir / "build" / "merge-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.dry_run:
        write_decisions(out_dir, decisions, "merge")
        print("Записано: build/merge-report.json, build/%s (--dry-run, реестр не менялся)" % CANDIDATES_FILE)
        return 0
    (out_dir / "data" / "proposals.json").write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Записано: data/proposals.json, build/merge-report.json, build/id-map.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
