#!/usr/bin/env python3
"""Секреты и персональные данные в запросе: поиск, маскировка и политика «что не отправлять в TypeSafe» (2.5.0).

Три уровня находок (по цене утечки и по тому, насколько надёжно их можно вырезать):
  critical — приватные ключи (PEM, OpenSSH, PGP, WIF, Ethereum), seed-фразы (12/15/18/21/24 слов), номера банковских карт
             (префикс платёжной системы + Luhn). Вырезать такое регулярными выражениями ненадёжно (промах = утечка всего
             кошелька или счёта), поэтому по умолчанию запрос с такой находкой в TypeSafe НЕ отправляется вовсе;
  secret   — пароли и PIN (русские и английские формы), токены и ключи API (по форме и по контексту), JWT, строки
             подключения и URL с учётными данными, CVV, заголовки Authorization, переменные окружения вида *_SECRET=…;
             значение заменяется на «[скрыто]», запрос уходит с маской;
  pii      — e-mail, телефоны, IBAN, паспорт/ИНН/СНИЛС/SSN рядом с названием документа: заменяются на «[скрыто]».

Политика — переменная TYPESAFE_TRIAGE_SECRETS (маскировка включена всегда, выключить её нельзя):
  block  (по умолчанию) — critical → в TypeSafe не отправлять (уровень по локальной эвристике), остальное маскировать;
  strict                — любая находка (critical, secret, pii) → не отправлять;
  mask                  — только маскировать и отправлять (менее безопасно: промах регулярки = утечка).

Значения находок нигде не печатаются и не пишутся: наружу идут только виды и количества. Только стандартная библиотека.
"""
import os
import re

CRITICAL, SECRET, PII = "critical", "secret", "pii"
MASK = "[скрыто]"
ENV = "TYPESAFE_TRIAGE_SECRETS"
POLICIES = ("block", "strict", "mask")

KIND_NAMES = {
    "private_key": "приватный ключ", "seed_phrase": "seed-фраза", "card": "номер банковской карты", "crypto_key": "ключ кошелька",
    "password": "пароль", "token": "токен или ключ API", "jwt": "JWT", "url_cred": "учётные данные в URL",
    "cvv": "CVV", "otp": "одноразовый код", "hash": "длинный хеш или ключ", "email": "e-mail", "phone": "телефон", "iban": "IBAN", "doc_id": "номер документа (паспорт, ИНН, СНИЛС)",
}
LEVEL_OF = {"private_key": CRITICAL, "seed_phrase": CRITICAL, "card": CRITICAL, "crypto_key": CRITICAL,
            "password": SECRET, "token": SECRET, "jwt": SECRET, "url_cred": SECRET, "cvv": SECRET, "otp": SECRET, "hash": PII,
            "email": PII, "phone": PII, "iban": PII, "doc_id": PII}

_I = re.I
_VALUE = r"(?P<v>\"[^\"\n]{1,200}\"|'[^'\n]{1,200}'|`[^`\n]{1,200}`|[^\s\"'`,;]{1,200})"
_SEP = r"""["'`]?\s*(?:[:=]|=>|:=)\s*"""

# ---------- critical ----------
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----(?:.*?-----END [A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----|.*\Z)", re.S)
PUTTY_RE = re.compile(r"PuTTY-User-Key-File-\d:.*?(?:Private-MAC:\s*\w+|\Z)", re.S)
CRYPTO_KEY_RES = (
    re.compile(r"\b0x[a-fA-F0-9]{64}\b"),                                   # приватный ключ Ethereum
    re.compile(r"(?<![A-Za-z0-9])[5KL][1-9A-HJ-NP-Za-km-z]{50,51}(?![A-Za-z0-9])"),   # Bitcoin WIF
    re.compile(r"(?<![A-Za-z0-9])[xyz]prv[1-9A-HJ-NP-Za-km-z]{100,112}(?![A-Za-z0-9])"),  # расширенный приватный ключ
)
SEED_KEYWORD_RE = re.compile(
    r"(?:seed(?:[- ]?phrase)?|mnemonic(?:[- ]?phrase)?|recovery[- ]?(?:phrase|words)|backup[- ]?(?:phrase|words)|secret[- ]?recovery[- ]?phrase|"
    r"сид[- ]?фраз\w*|seed[- ]?фраз\w*|мнемоник\w*|мнемоническ\w+\s+фраз\w*|секретн\w+\s+фраз\w*|фраз\w+\s+восстановлени\w+|"
    r"кодов\w+\s+фраз\w*|резервн\w+\s+фраз\w*|слов\w*\s+восстановлени\w+)", _I)
SEED_AFTER_RE = re.compile(r"[^\n]{0,40}?(?:[:=\-—–]|\n|\bis\b|\bэто\b|\bтакая\b)\s*", _I)
_WORD = r"[A-Za-zА-Яа-яЁё]{2,12}"
SEED_WORDS_RE = re.compile(r"(?:\d{1,2}[.):]\s*)?%s(?:(?:[ \t,;]+|\s*\n\s*)(?:\d{1,2}[.):]\s*)?%s){11,23}" % (_WORD, _WORD))
# 12–24 слов из 3–8 латинских букв подряд без знаков препинания: seed-фраза BIP-39 без подписи
BARE_SEED_RE = re.compile(r"(?<![\w-])(?:\d{1,2}[.):]\s*)?[a-z]{3,8}(?:(?:[ \t,;]+|\s*\n\s*)(?:\d{1,2}[.):]\s*)?[a-z]{3,8}){11,}(?![\w-])")
SEED_LENGTHS = (12, 15, 18, 21, 24)
STOPWORDS = frozenset((
    "the and for with that this from have not are was were been will would should could can you your our their they them its but "
    "all any one has had does did how what when where which who why into out over then than also more most some such only just "
    "use used using make made need needs want please fix add change check update create write read run set get see let").split())
CARD_RE = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")
CARD_GROUPED_RE = re.compile(r"(?<![\w-])\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,7}(?![\w-])")      # 4 группы: любой префикс, но Luhn
_CARD_PREFIX = re.compile(r"^(?:4\d{12}(?:\d{3}(?:\d{3})?)?|5[1-5]\d{14}|2(?:2[2-9]|[3-6]\d|7[01]|720)\d{12}|3[47]\d{13}|6(?:011|5\d\d|22[1-9])\d{12}|"
                          r"220[0-4]\d{12}|35(?:2[89]|[3-8]\d)\d{12}|62\d{14,17}|30[0-5]\d{11}|3[689]\d{12})$")

# ---------- secret ----------
_PWD_KW = (r"(?:(?:[\w]{2,12}[-‑])?парол\w*|(?:[\w]{2,12}[-‑])?passw(?:or)?d\w*|пасс?ворд\w*|passw(?:or)?d\w*|passwd|pwd|passphrase|парольн\w+\s+фраз\w*|кодов\w+\s+слов\w*|"
           r"пин[- ]?код\w*|pin(?:[- ]?code)?|pass(?=[\"']?\s*[:=]))")
_OF_ITEM = r"(?:\s+(?:от|для|к|на|в|of|for|to|on)\s+[\w.@/-]{1,60})"
_OF = _OF_ITEM + "{0,2}"
_GAP = r"(?:\s+[\w.@/-]{1,40}){0,3}"                  # «пароль админа: x», «пароль для root@host: x»
PWD_STRONG_RE = re.compile(r"(?<![\w-])" + _PWD_KW + _GAP + _SEP + _VALUE, _I)
PIN_RE = re.compile(r"(?<![\w-])(?:пин(?:[- ]?код\w*)?|pin(?:[- ]?code)?)\s+(?:карты\s+|от\s+\S+\s+)?(?P<v>\d{4,6})(?!\d)", _I)
PWD_DASH_RE = re.compile(r"(?<![\w-])(?:парол\w*|passw(?:or)?d\w*|pwd|пин[- ]?код\w*)" + _OF + r"\s+[—–-]\s+" + _VALUE, _I)
PWD_WEAK_RE = re.compile(r"(?<![\w-])(?P<pre>[\w]{2,12}[-‑])?(?P<kw>парол[ьяю]|password|passwd)(?P<of>" + _OF + r")\s+(?P<is>(?:это|is|будет|теперь|такой|now)\s+)?(?P<v>[^\s\"'`,;:.!?()]{1,120})", _I)
FUNCTION_WORDS = frozenset("в на и не для от это к с по из за что как или то но а же ли бы у о об при до без под над the a an to of in on for is are was be not "
                           "and or it this that with from by at as".split())
# токен без известного префикса рядом со словом «ключ»/«key»/«token»: смесь регистров и цифр, от 16 знаков
KEY_NEAR_RE = re.compile(r"(?<![\w-])(?:ключ\w*|key|token|токен\w*|secret|секрет\w*)(?![\w-])[^\n]{0,40}?(?<![\w-])(?P<v>(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[a-z])"
                         r"(?=[A-Za-z0-9_\-]*[A-Z])[A-Za-z0-9_\-]{16,})(?![\w-])", _I)
PREFIXED_KEY_RE = re.compile(r"\b[a-z]{2,8}_(?:live|test|prod|secret)_[A-Za-z0-9]{8,}\b")
WEAK_COMMON = frozenset("admin root qwerty password secret letmein welcome default guest test master dragon monkey changeme".split())
WEAK_PROSE = frozenset("reset validation field input manager policy strength hashing hashed hash storage form page change length check rules complexity "
                       "expiry expiration required optional encryption encrypted generator recovery should must cannot does doesn must".split())
ENV_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]{0,40}?(?:SECRET|TOKEN|PASSWORD|PASSWD|PASS|PWD|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|CREDENTIALS?)[A-Za-z0-9_]{0,40}"
                    + _SEP + _VALUE, _I)
KEYVAL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:токен\w*|секрет\w*|(?:секретн|приватн|закрыт|мастер)\w+\s+ключ|ключ(?:\s+api)?|api[ _-]?key|apikey|secret(?:[ _-]?key)?|"
    r"(?:private|master|signing|encryption|ssh|access|refresh|auth|id|session|client)[ _-]?(?:key|token|secret)|session[ _-]?(?:id|key)|phpsessid|sid|csrf[ _-]?token|xsrf[ _-]?token|"
    r"token|credentials?|bearer|authorization|cookie|set-cookie)" + _SEP + _VALUE, _I)
PASSPHRASE_RE = re.compile(r"(?<![\w-])(?:passphrase|парольная\s+фраза|кодовая\s+фраза|фраза-пароль)" + r"""["'`]?\s*(?:[:=]|=>|:=|[—–-])\s*""" + r"(?P<v>[^\n]{3,120})", _I)
CLI_CRED_RES = (
    re.compile(r"(?i)(?:\bcurl\b[^\n]{0,80}?\s(?:-u|--user)\s+|\s--password(?:=|\s+)|\bsshpass\s+-p\s+)(?P<v>\"[^\"\n]+\"|'[^'\n]+'|[^\s\"']+)"),
    re.compile(r"(?i)\bcurl\b[^\n]{0,80}?\s(?:-u|--user)\s+[^\s:]{1,64}:(?P<v>[^\s\"']+)"),
)
OTP_RE = re.compile(r"(?:код\s+(?:из\s+)?(?:смс|sms)|одноразов\w+\s+код|код\s+подтверждени\w+|\botp\b|\b2fa\s+code|verification\s+code|one[- ]time\s+(?:code|password))"
                    r"[^\n\d]{0,12}(?P<v>\d{4,8})(?!\d)", _I)
AUTH_BASIC_RE = re.compile(r"(?i)\b(?:authorization\s*[:=]\s*)?(?:basic|bearer|token)\s+[A-Za-z0-9+/=._~-]{12,}")
URL_CRED_RE = re.compile(r"\b[a-z][a-z0-9+.-]{1,20}://[^\s/:@]{0,80}:(?P<v>[^\s/@]{1,200})@", _I)
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")
CVV_RE = re.compile(r"(?<![\w-])(?:cvv2?|cvc2?|cvn|cid)\s*[:=]?\s*(?P<v>\d{3,4})(?!\d)", _I)
TOKEN_RES = (
    re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test|ant|proj)?[-_]?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr|github_pat|glpat|hf|npm|xox[abprs]|SG)[_.\-][A-Za-z0-9_\-.]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bpypi-[A-Za-z0-9_\-]{30,}"),
    re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[A-Z0-9]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b"),                              # токен Telegram-бота
    re.compile(r"\bAccountKey=[A-Za-z0-9+/=]{20,}"),
    re.compile(r"(?<![A-Za-z0-9+/_\-])(?=[A-Za-z0-9+/_\-]*\d)(?=[A-Za-z0-9+/_\-]*[A-Za-z])[A-Za-z0-9+/_\-]{40,}={0,2}(?![A-Za-z0-9+/_\-])"),
)

HASH_RE = re.compile(r"\b[a-f0-9]{32,}\b", re.I)                                 # длинный hex: хеш коммита или ключ — маскируется молча
TYPE_WORDS = frozenset("str string int integer float bool boolean none null nil true false undefined any object dict list array optional "
                       "required value token secret key password string[] bytes".split())

# ---------- pii ----------
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){1,5}\b")
PHONE_RE = re.compile(r"(?<![\w.:])(?:\+\d{1,3}|\b[78])[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?![\w.])")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
DOC_ID_RE = re.compile(r"(?<![\w-])(?:паспорт\w*|серия\s+и\s+номер|\bинн\b|\bснилс\b|\bогрн\w*|\bssn\b|passport(?:\s+no\.?|\s+number)?|номер\s+документа)"
                       r"[^\n\d]{0,25}(?P<v>\d[\d \-]{5,20}\d)", _I)


def luhn_ok(digits):
    s, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        s += n
        alt = not alt
    return s % 10 == 0


def iban_ok(raw):
    s = raw.replace(" ", "").upper()
    if not 15 <= len(s) <= 34:
        return False
    moved = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def _span(m, group=None):
    return (m.start(group), m.end(group)) if group else (m.start(), m.end())


def _looks_secret_value(v):
    """Значение после «пароль <слово>» без разделителя: похоже на пароль, а не на слово из фразы."""
    v = v.strip("\"'`")
    if len(v) < 4 or v == MASK:
        return False
    low = v.lower()
    if low in WEAK_COMMON:
        return True
    has_digit = any(c.isdigit() for c in v)
    has_sym = any(not c.isalnum() for c in v)
    has_alpha = any(c.isalpha() for c in v)
    return (has_digit and has_alpha) or has_sym or (has_digit and len(v) >= 6)


def _plausible_value(v):
    """Значение после «token:» / «SECRET=»: не тип, не пустышка и не слово из фразы."""
    v = v.strip("\"'`")
    if len(v) < 4 or v == MASK or v.lower() in TYPE_WORDS or v.endswith(("(", ")")):
        return False
    if any(c.isdigit() for c in v) or any(not c.isalnum() and c not in "_-" for c in v):
        return True
    return v.isascii() and len(v) >= 8


def find(text):
    """Текст → список (start, end, kind). Значения не возвращаются."""
    out = []

    def add(kind, m, group=None):
        s, e = _span(m, group)
        if e > s and text[s:e] != MASK:
            out.append((s, e, kind))

    for m in PRIVATE_KEY_RE.finditer(text):
        add("private_key", m)
    for m in PUTTY_RE.finditer(text):
        add("private_key", m)
    for rx in CRYPTO_KEY_RES:
        for m in rx.finditer(text):
            add("crypto_key", m)
    # seed-фраза с подписью: «seed: слово слово …» (12+ слов)
    for km in SEED_KEYWORD_RE.finditer(text):
        am = SEED_AFTER_RE.match(text, km.end())
        if not am:
            continue
        wm = SEED_WORDS_RE.match(text, am.end())
        if wm:
            out.append((wm.start(), wm.end(), "seed_phrase"))
    # seed-фраза без подписи: ровно 12/15/18/21/24 слов BIP-39-вида, без служебных слов
    for m in BARE_SEED_RE.finditer(text):
        words = re.findall(r"[a-z]+", m.group(0))
        if len(words) in SEED_LENGTHS and sum(w in STOPWORDS for w in words) < 2 and len(set(words)) >= len(words) - 2:
            add("seed_phrase", m)
    for m in CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _CARD_PREFIX.match(digits) and luhn_ok(digits):
            add("card", m)

    for m in CARD_GROUPED_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            add("card", m)
    for m in PIN_RE.finditer(text):
        add("password", m, "v")
    for m in PWD_STRONG_RE.finditer(text):
        add("password", m, "v")
    for m in PWD_DASH_RE.finditer(text):
        add("password", m, "v")
    for m in PWD_WEAK_RE.finditer(text):
        v = m.group("v")
        low = v.lower().rstrip(".")
        if low in WEAK_PROSE or low in FUNCTION_WORDS:
            continue
        if v.isdigit():                                    # «пароль 1» — число никогда не слово из фразы
            add("password", m, "v")
        elif m.group("pre") and not re.fullmatch(r"[а-яё]{3,}", v):   # «sudo-пароль x», «wifi-password x»: значение; русское слово — проза
            add("password", m, "v")
        elif len(v) >= 4 and (_looks_secret_value(v) or (m.group("is") and v.isascii() and v.isalnum())):
            add("password", m, "v")
    for rx in (KEY_NEAR_RE, PREFIXED_KEY_RE):
        for m in rx.finditer(text):
            add("token", m, "v" if rx is KEY_NEAR_RE else None)
    for rx in (ENV_RE, KEYVAL_RE):
        for m in rx.finditer(text):
            if _plausible_value(m.group("v")):
                add("token", m, "v")
    for m in PASSPHRASE_RE.finditer(text):
        add("password", m, "v")
    for rx in CLI_CRED_RES:
        for m in rx.finditer(text):
            add("password", m, "v")
    for m in OTP_RE.finditer(text):
        add("otp", m, "v")
    for m in AUTH_BASIC_RE.finditer(text):
        add("token", m)
    for m in URL_CRED_RE.finditer(text):
        add("url_cred", m, "v")
    for m in JWT_RE.finditer(text):
        add("jwt", m)
    for m in CVV_RE.finditer(text):
        add("cvv", m, "v")
    for rx in TOKEN_RES:
        for m in rx.finditer(text):
            if not re.fullmatch(r"[0-9a-fA-F]{32,}", m.group(0)):      # чистый hex — «хеш», ниже
                add("token", m)
    for m in HASH_RE.finditer(text):
        add("hash", m)

    for m in EMAIL_RE.finditer(text):
        add("email", m)
    for m in PHONE_RE.finditer(text):
        add("phone", m)
    for m in IBAN_RE.finditer(text):
        if iban_ok(m.group(0)):
            add("iban", m)
    for m in DOC_ID_RE.finditer(text):
        add("doc_id", m, "v")
    return out


def _merge(spans):
    spans = sorted(spans, key=lambda x: (x[0], -x[1]))
    merged = []
    for s, e, k in spans:
        if merged and s < merged[-1][1]:
            ps, pe, pk = merged[-1]
            if e > pe:
                merged[-1] = (ps, e, pk)
            if LEVEL_RANK[LEVEL_OF[k]] > LEVEL_RANK[LEVEL_OF[pk]]:
                merged[-1] = (merged[-1][0], merged[-1][1], k)
        else:
            merged.append((s, e, k))
    return merged


LEVEL_RANK = {PII: 0, SECRET: 1, CRITICAL: 2}


def inspect(text):
    """Текст → {"text": с маской, "kinds": {вид: число}, "level": critical|secret|pii|None, "count": число находок}.
    Значения находок в результат не попадают."""
    text = text or ""
    spans = _merge(find(text))
    if not spans:
        return {"text": text, "kinds": {}, "level": None, "count": 0}
    parts, pos, kinds = [], 0, {}
    for s, e, k in spans:
        parts.append(text[pos:s])
        parts.append(MASK)
        pos = e
        kinds[k] = kinds.get(k, 0) + 1
    parts.append(text[pos:])
    level = max((LEVEL_OF[k] for k in kinds), key=lambda lv: LEVEL_RANK[lv])
    return {"text": "".join(parts), "kinds": kinds, "level": level, "count": sum(kinds.values())}


def scrub(text):
    """Текст с замаскированными секретами и персональными данными."""
    return inspect(text)["text"]


def policy():
    v = os.environ.get(ENV, "").strip().lower()
    return v if v in POLICIES else "block"


def withhold(found, pol=None):
    """Нельзя ли отправлять запрос (даже с маской) в TypeSafe по политике."""
    pol = pol or policy()
    if pol == "mask" or not found["level"]:
        return False
    return found["level"] == CRITICAL or pol == "strict"


def describe(kinds):
    """{'password': 1, 'email': 2} → «пароль ×1, e-mail ×2» (только виды и числа)."""
    return ", ".join("%s ×%d" % (KIND_NAMES.get(k, k), n) for k, n in sorted(kinds.items(), key=lambda kv: (-LEVEL_RANK[LEVEL_OF[kv[0]]], kv[0])))
