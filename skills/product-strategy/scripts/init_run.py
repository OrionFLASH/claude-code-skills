#!/usr/bin/env python3
"""Создаёт папку прогона <OUT> по run-config: подпапки, build/STATUS.md с чек-листом фаз, .gitignore для node-модулей.

  init_run.py <OUT>                  по <OUT>/build/run-config.json (его пишет intake.py)
  init_run.py <OUT> --status "фаза 3 готова: …"   дописать строку в STATUS.md (чекпоинт)
  init_run.py <OUT> --status         без текста — таблица статуса (SM 10.2): фаза → статус → что открыть сейчас → ETA →
                                     кто работает (агенты из build/agents.json); внизу — что уже можно посмотреть и сколько
                                     осталось (оценка dispatch.py forecast ±30 %); --status-json — то же JSON
  init_run.py <OUT> --done 3         отметить фазу 3 выполненной; проверяет обязательные артефакты фазы (PHASE_ARTIFACTS):
                                     без них — предупреждение и пометка «без артефактов» в STATUS.md; с --require-artifacts
                                     (или run-config tools.strict_phases: true) — отказ (код 2), пока не будет --force;
                                     после фазы оценки (6 / C6) создаёт data/decisions.json (decisions.py --init), если его нет
  init_run.py <OUT> --show           фазы по чек-листу и по артефактам, следующая фаза по факту, волны агентов (agents.json),
                                     сверка ветки с run-config output.git_branch (+ output.branch_status / branch_note от
                                     concept-apply), чек-лист, открытые пункты сверки (data/model.json → reconciliation.items,
                                     data/plan-baseline.json → gantt_contract.messages), последние чекпоинты;
                                     фазы, чьи артефакты уже есть, отмечаются автоматически (--no-sync — только показать)
  init_run.py <OUT> --sync           только отметить фазы по артефактам (и синхронизировать блок фаз в TASKS.md владельца)
  init_run.py <OUT> --tasks-file TASKS.md | STRATEGY_TASKS.md | auto
                                     один чек-лист (FB-040): TASKS.md в корне репозитория — блок фаз дописывается туда и
                                     синхронизируется со STATUS.md, STRATEGY_TASKS.md не создаётся; auto (по умолчанию) —
                                     TASKS.md, если он есть в корне или его требует CLAUDE.md владельца (корень репозитория,
                                     .claude/CLAUDE.md, ~/.claude/CLAUDE.md) или run-config owner_rules.tasks_file (внутри
                                     git-репозитория), иначе STRATEGY_TASKS.md в <OUT>
  init_run.py <OUT> --intervention "что | почему | файл" --by owner|orchestrator|agent [--why …] [--file …] [--kind …]
                                     журнал ручных вмешательств (FB-004) → build/interventions.jsonl (ретроспектива —
                                     collect_reports.py --retro, раздел REPORT «Ручные вмешательства» — report.py)
  init_run.py <OUT> --impact "что меняется" [--keys design.chosen,P012,…] [--by owner] [--reopen]
                                     протокол смены решения (SM 10.1): какие фазы, файлы, предложения и части текста
                                     затронуты, какие команды пересобирают; --reopen снимает отметки затронутых фаз;
                                     запись — в build/interventions.jsonl (kind: decision-change)
  init_run.py <OUT> --owner-materials  каркас build/owner-materials.md (FB-002) по run-config sources.owner_docs[]: ссылка, роль
                                     (base | follow | ref), статус чтения (read | blocked | not_attempted), инструмент, выжимка
                                     5–10 строк, как используется; существующий файл не затирается (дописываются новые ссылки)
  init_run.py <OUT> --relocate <NEW> [--repo R] [--inside-repo|--no-inside-repo] [--branch B] [--dry-run]
                                     перенос папки прогона: пути в файлах заменяются (relocate_run.py), run-config обновляется;
                                     дальше `build_all.py <NEW>` и `check_gitignore.py <NEW>`
Строки --status и записи в STATUS.md хранятся без абсолютных путей: <OUT> → путь от корня репозитория (или «<OUT>»),
домашняя папка → «~».
Режим идеи (run-config mode: concept, references/concept-mode.md) — фазы C0…C9, C4.5 (пересмотр идеи, pivot_check.py),
C5.5, C7.5 (второй раунд зависимостей), C8.5 (рабочий прототип — только при phases.prototype: true или
idea.facets.prototype_needed); `--done 3` и `--done C3` равносильны.
Внешний продукт (product.mode: external, references/external-product.md) — фазы 0–9 с текстами фаз 1–3 «без кода» (store_stats,
app_scan, сайт, трекер); repo_scan/repo_facts — строками «—» в разделе «Не применяется».

Только стандартная библиотека.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIRS = ["build/briefs", "research/specs", "research/experiments", "data", "charts/flows", "mockups/current", "mockups/concepts",
        "design-refs", "competitors/shots", "deliverables"]
OUT_GITIGNORE = ["build/node/", "node_modules/", "build/tmp/", "build/preview/", "build/pdf-preview/"]
PHASES = [
    (0, "Подготовка: папка, ветка, проверка инструментов (check_env), план"),
    (1, "Понимание продукта по репозиторию (repo_scan, issues_export) → research/product-understanding.md"),
    (2, "Запуск и изучение приложения (audit_site, ui-inventory, пути пользователя, токены дизайна)"),
    (3, "Тип продукта и адаптация акцентов"),
    (4, "Рынок: конкуренты, сообщества, спрос, события, право (субагенты) → data/*.json"),
    (5, "Реестр предложений: двухпроходная генерация → merge_proposals → check_registry"),
    ("5.5", "Аудит пробелов и предпосылок: gap_audit.py → агент-аудитор → research/gap-audit.md, черновики G7, зависимости"),
    (6, "Оценка: score, validate_scores, typesafe_eval, model, charts, чувствительность"),
    (7, "Стратегия: разделы, спеки топ-N, эксперименты, Гант, Kanban, вопросы владельцу"),
    (8, "Макеты, блок-схемы, референсы дизайна, скриншоты конкурентов"),
    (9, "Сборка и QA: build_all (html, xlsx, pptx, pdf), check_links, smoke_html, REPORT.md"),
]
# режим «внешний продукт» (product.mode = external, references/external-product.md): кода продукта нет — тексты фаз 1–3
# заменяются, repo_scan/repo_facts идут в STATUS.md строками со статусом «—» (не фазы, отмечать не нужно)
EXTERNAL_PHASE_TEXT = {
    1: "Понимание продукта без кода: store_stats.py, app_scan.py, сайт (audit_site), трекер (issues_export) → research/product-understanding.md",
    2: "Обход приложения: эмулятор (android-qa-audit по APK), сайт; скриншоты → mockups/current/, замеры → data/",
    3: "Тип продукта и акценты: seeds.py → build/seeds.md (затравки по типу, сигналы APK и магазинов)",
}
EXTERNAL_SKIPPED = [("repo_scan.py", "режим external: кода продукта нет, scope.repo_analysis=false"),
                    ("repo_facts.py", "режим external: кода продукта нет, факты — из APK, магазинов и сайта")]
CONCEPT_PHASES = [   # режим «Идея → концепция» (references/concept-mode.md)
    ("C0", "Опрос об идее (intake.py concept-*), инструменты (check_env), папка"),
    ("C1", "Досье идеи: concept_dossier.py → research/idea-dossier.md, data/idea.json, build/search-plan.md, build/seeds.md"),
    ("C2", "Предпроверка жизнеспособности: typesafe_concept.py → data/typesafe-concept.json (красный — спросить владельца)"),
    ("C3", "Тип продукта и акценты по ответам, затравки реестра"),
    ("C4", "Рынок: конкуренты и аналоги, сообщества, спрос, события, право → data/*.json"),
    ("C4.5", "Пересмотр идеи: pivot_check.py → data/premises.json, решение владельца (продолжить / сузить / остановиться)"),
    ("C5", "Реестр решений (≥ proposals_min): генерация → merge_proposals → check_registry"),
    ("C5.5", "Аудит предпосылок: юрлицо, домен, прототип, первые пользователи, аккаунты платформ (gap_audit.py)"),
    ("C6", "Оценка: score, validate_scores, typesafe_eval, model, charts"),
    ("C7", "Текст концепции по references/concept-outline.md, спеки MVP, эксперименты, Гант, Kanban"),
    ("C7.5", "Второй раунд зависимостей: collect_reports.py --deps → build/deps-patch.json → merge_proposals → score"),
    ("C8", "Дизайн: язык дизайна, макеты ключевых экранов, референсы аналогов"),
    ("C8.5", "Рабочий прототип (если выбран): ядро расчётов с тестами, оболочка, режимы, регрессия"),
    ("C9", "Сборка и QA: build_all --strict, REPORT.md с go/no-go"),
]


# Обязательные артефакты фаз (references/phases.md → «Артефакты» и «Готово, когда»). Элемент — (путь | «a|b» | glob, ключ run-config):
# при значении ключа False артефакт не требуется. Фаза без своих артефактов (пустой список) готова только по отметке.
PHASE_ARTIFACTS = {
    "0": [("build/env.json", None)],
    "1": [("research/product-understanding.md", None), ("data/repo-scan.json", "scope.repo_analysis")],
    "2": [("research/ui-inventory.md", None)],
    "3": [("build/seeds.md", None)],
    "4": [("research/market.md", None), ("data/competitors.json", "scope.competitors"), ("data/sources.json|data/sources-*.json", None)],
    "5": [("data/proposals.json", None)],
    "5.5": [("research/gap-audit.md", None)],
    "6": [("data/scores.json", None), ("data/critical-path.json", None)],
    "7": [("research/strategy.md", None), ("data/gantt.json", None)],
    "8": [("charts/charts-index.json", None), ("data/mockups-index.json", "scope.design_mockups")],
    "9": [("deliverables/index.html", None), ("deliverables/REPORT.md", None)],
    "C0": [("build/env.json", None)],
    "C1": [("research/idea-dossier.md", None), ("data/idea.json", None)],
    "C2": [("data/typesafe-concept.json", None)],
    "C3": [],                                   # build/seeds.md пишет уже C1 — отдельного артефакта у C3 нет
    "C4": [("data/competitors.json", None)],
    "C4.5": [("data/premises.json", None)],     # плюс решение владельца в файле (PHASE_CHECKS)
    "C5": [("data/proposals.json", None)],
    "C5.5": [("research/gap-audit.md", None)],
    "C6": [("data/scores.json", None)],
    "C7": [("research/strategy.md", None), ("data/gantt.json", None)],
    "C7.5": [("build/deps-patch.json", None)],  # пустой список — тоже итог («зависимостей от авторов нет»)
    "C8": [("mockups/tokens.css", None)],
    "C8.5": [("prototype/index.html|prototype/*.html", None)],
    "C9": [("deliverables/index.html", None), ("deliverables/REPORT.md", None)],
}
EXISTS_OK = {"build/deps-patch.json"}           # пустой JSON-контейнер — тоже артефакт
PHASE_SWITCH = {"5.5": "phases.gap_audit", "C5.5": "phases.gap_audit", "C4.5": "phases.pivot_check",
                "C7.5": "phases.deps_round", "C8.5": "phases.prototype"}     # фаза выключена выбором владельца
PHASE_DEFAULT_OFF = {"C8.5"}                    # включается только явно: phases.prototype: true или idea.facets.prototype_needed

# что открыть по фазе (статус SM 10.2) — первые существующие пути
OPEN_FILES = {
    "0": ["build/run-config.json", "build/env.json"], "1": ["research/product-understanding.md"], "2": ["research/ui-inventory.md"],
    "3": ["build/seeds.md"], "4": ["research/market.md", "data/competitors.json", "research/integration.md", "research/legal.md"],
    "4.5": ["data/premises.json"], "5": ["data/proposals.json"], "5.5": ["research/gap-audit.md"],
    "6": ["data/scores.json", "charts/charts-index.json", "data/model.json"],
    "7": ["research/strategy.md", "build/parts/", "data/gantt.json"], "7.5": ["build/deps-patch.json"],
    "8": ["mockups/gallery.html", "design/directions.md", "mockups/concepts/"], "8.5": ["prototype/index.html"],
    "9": ["deliverables/index.html", "deliverables/REPORT.md"],
}
OPEN_FILES.update({"C" + k: v for k, v in list(OPEN_FILES.items())})
OPEN_FILES["C1"] = ["research/idea-dossier.md", "build/search-plan.md"]
OPEN_FILES["C2"] = ["data/typesafe-concept.json"]
# минуты оркестратора на фазы без субагентов (оценка для ETA)
ORCH_MINUTES = {"0": 20, "1": 25, "2": 40, "3": 10, "4.5": 15, "6": 15, "7.5": 10, "9": 30, "C0": 20, "C1": 5, "C2": 5, "C3": 10,
                "C4.5": 15, "C6": 15, "C7.5": 10, "C9": 30}
TASKS_BEGIN = "<!-- product-strategy:phases %s -->"
TASKS_END = "<!-- /product-strategy:phases %s -->"
INTERVENTIONS = "build/interventions.jsonl"


def load_cfg(out):
    try:
        return json.loads((Path(out) / "build" / "run-config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_cfg(out, cfg):
    p = Path(out) / "build" / "run-config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def cfg_get(cfg, dotted, default=True):
    cur = cfg
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def artifact_ok(path):
    """Файл есть и не пустой (JSON — разбирается и не пустой контейнер; для EXISTS_OK — достаточно валидного JSON)."""
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if any(str(path).replace("\\", "/").endswith(x) for x in EXISTS_OK):
                return True
            return data not in ([], {}, None, "")
        return bool(path.read_text(encoding="utf-8", errors="replace").strip())
    except (OSError, json.JSONDecodeError):
        return False


def premises_decided(out):
    """C4.5 готова, когда в data/premises.json записано решение владельца (decision), а не только черновик."""
    try:
        d = json.loads((Path(out) / "data" / "premises.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(d, dict) and bool(d.get("decision"))


PHASE_CHECKS = {"C4.5": (premises_decided, "решение в data/premises.json (pivot_check.py --decide …)")}


def missing_artifacts(out, cfg, phase):
    """Список недостающих обязательных артефактов фазы (пустой — всё есть)."""
    out = Path(out)
    miss = []
    for spec, cond in PHASE_ARTIFACTS.get(str(phase), []):
        if cond and cfg_get(cfg, cond, True) is False:
            continue
        alts = spec.split("|")
        if not any(any(artifact_ok(f) for f in out.glob(a)) if any(ch in a for ch in "*?[") else artifact_ok(out / a) for a in alts):
            miss.append(spec)
    chk = PHASE_CHECKS.get(str(phase))
    if chk and not miss and not chk[0](out):
        miss.append(chk[1])
    return miss


def phase_disabled(cfg, phase):
    key = PHASE_SWITCH.get(str(phase))
    if not key:
        return False
    if str(phase) in PHASE_DEFAULT_OFF:
        on = cfg_get(cfg, key, None) is True or bool(cfg_get(cfg, "idea.facets.prototype_needed", False))
        return not on
    return cfg_get(cfg, key, True) is False


def repo_top(path):
    p = Path(path).resolve()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return None


def rel_display(out, cfg=None):
    """<OUT> для записей: путь от корня репозитория (run-config repo.path или git), иначе «<OUT>»."""
    out = Path(out).resolve()
    cfg = cfg if cfg is not None else load_cfg(out)
    repo = (cfg.get("repo") or {}).get("path")
    cands = [Path(repo).expanduser().resolve()] if repo else []
    top = repo_top(out)
    if top:
        cands.append(top)
    for c in cands:
        if c == out:
            return "."
        if c in out.parents:
            return out.relative_to(c).as_posix()
    return "<OUT>"


def sanitize(out, text, cfg=None):
    """Абсолютные пути в строке STATUS.md → относительные: <OUT> → путь от репозитория, домашняя папка → ~."""
    out_abs = str(Path(out).resolve())
    forms = {out_abs, os.path.abspath(str(out))}
    forms |= {f[len("/private"):] for f in list(forms) if f.startswith("/private/")}
    shown = rel_display(out, cfg)
    for f in sorted(forms, key=len, reverse=True):
        text = re.sub(re.escape(f) + r"(?![\w\-])", shown, text)
    home = str(Path.home())
    if home and home != "/":
        text = re.sub(re.escape(home) + r"(?=/|$|\s)", "~", text)
    return text


def status_path(out):
    return Path(out) / "build" / "STATUS.md"


def now_s():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- один чек-лист (FB-040)
def owner_claude_files(top):
    files = []
    if top:
        files += [Path(top) / "CLAUDE.md", Path(top) / ".claude" / "CLAUDE.md"]
    env = os.environ.get("PS_OWNER_CLAUDE_MD")
    files.append(Path(env).expanduser() if env else Path.home() / ".claude" / "CLAUDE.md")
    return files


def claude_requires_tasks(top):
    """CLAUDE.md владельца (корень репозитория, .claude/, ~/.claude/) упоминает TASKS.md → путь к файлу правила или None."""
    for f in owner_claude_files(top):
        try:
            if f.is_file() and re.search(r"\bTASKS\.md\b", f.read_text(encoding="utf-8", errors="replace")):
                return f
        except OSError:
            continue
    return None


def tasks_target(out, cfg, explicit=None):
    """Куда вести чек-лист: (Path | None, причина). None — STRATEGY_TASKS.md в <OUT> (поведение 1.4)."""
    # FB-040: явный выбор → output.tasks_file → правило владельца из CLAUDE.md (run-config owner_rules.tasks_file) → auto
    top = repo_top(out)
    rule_file = (cfg.get("owner_rules") or {}).get("tasks_file") if isinstance(cfg.get("owner_rules"), dict) else None
    if not top:
        rule_file = None                                # вне git-репозитория правило «TASKS.md в корне проекта» не применяется
    choice = (explicit or (cfg.get("output") or {}).get("tasks_file") or rule_file or "auto").strip()
    if rule_file and choice == str(rule_file).strip() and not explicit and not (cfg.get("output") or {}).get("tasks_file"):
        p = Path(choice).expanduser()
        return (p if p.is_absolute() else top / p), "правило владельца (run-config owner_rules.tasks_file): чек-лист в %s" % choice
    if choice in ("STRATEGY_TASKS.md", "own", "strategy"):
        return None, "выбрано: STRATEGY_TASKS.md в папке прогона"
    if choice != "auto":
        base = top or Path(out).resolve()
        p = Path(choice).expanduser()
        return (p if p.is_absolute() else base / p), "выбрано: --tasks-file %s" % choice
    if not top:
        return None, "папка прогона вне git-репозитория"
    if (top / "TASKS.md").is_file():
        return top / "TASKS.md", "в корне репозитория есть TASKS.md"
    rule = claude_requires_tasks(top)
    if rule:
        where = "~/.claude/CLAUDE.md" if str(rule).startswith(str(Path.home() / ".claude")) else rule.name
        return top / "TASKS.md", "правило владельца (%s): чек-лист в TASKS.md" % where
    return None, "TASKS.md в корне нет и CLAUDE.md его не требует"


def tasks_block(out, cfg, rows_checked):
    key = rel_display(out, cfg)
    concept = cfg.get("mode") == "concept"
    lines = [TASKS_BEGIN % key, "## Фазы прогона %s `%s` (product-strategy; синхронизируется с `%s/build/STATUS.md` — init_run.py --sync)"
             % ("концепции" if concept else "стратегии", key, key)]
    for num, checked, text in rows_checked:
        lines.append("- [%s] %s. %s" % ("x" if checked else " ", num, text))
    lines.append(TASKS_END % key)
    return "\n".join(lines)


def block_re(key):
    return re.compile(r"%s.*?%s" % (re.escape(TASKS_BEGIN % key), re.escape(TASKS_END % key)), re.S)


def sync_tasks_file(out, quiet=True):
    """Двусторонняя синхронизация блока фаз в TASKS.md со STATUS.md: отмеченная в любом из файлов фаза — отмечена в обоих."""
    cfg = load_cfg(out)
    target, _why = tasks_target(out, cfg)
    sp = status_path(out)
    if target is None or not sp.exists():
        return None
    s = sp.read_text(encoding="utf-8")
    rows = phases_in(s)
    key = rel_display(out, cfg)
    text = target.read_text(encoding="utf-8") if target.exists() else "# TASKS\n"
    m = block_re(key).search(text)
    in_tasks = {n for n, c, _t in phases_in(m.group(0)) if c} if m else set()
    newly = [n for n, c, _t in rows if not c and n in in_tasks]
    for n in newly:
        s = check_phase(s, n)
    if newly:
        s = s.rstrip("\n") + "\n- %s — отмечены по чек-листу %s: %s (init_run.py)\n" % (now_s(), target.name, ", ".join(newly))
        sp.write_text(s, encoding="utf-8")
        rows = phases_in(s)
    block = tasks_block(out, cfg, rows)
    text = block_re(key).sub(lambda _m: block, text, count=1) if m else text.rstrip("\n") + "\n\n" + block + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    if newly and not quiet:
        print("из %s отмечены фазы: %s" % (target.name, ", ".join(newly)))
    return target


# ---------------------------------------------------------------- создание папки
def init(out, tasks_file=None):
    out = Path(out).resolve()
    cfgp = out / "build" / "run-config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8")) if cfgp.exists() else {}
    for d in DIRS:
        (out / d).mkdir(parents=True, exist_ok=True)
    gi = out / ".gitignore"
    if not gi.exists():
        gi.write_text("!build/\n!data/\n!deliverables/\n" + "\n".join(OUT_GITIGNORE) + "\n*.tmp\n", encoding="utf-8")   # «!» переопределяют корневые правила (build/)
    else:
        lines = gi.read_text(encoding="utf-8").splitlines()
        add = [x for x in OUT_GITIGNORE if x not in lines]
        if add:
            gi.write_text("\n".join(lines + add) + "\n", encoding="utf-8")
    if tasks_file and cfg is not None:
        cfg.setdefault("output", {})["tasks_file"] = tasks_file
        if cfgp.exists():
            save_cfg(out, cfg)
    concept = cfg.get("mode") == "concept"
    external = not concept and (cfg.get("product") or {}).get("mode") == "external"
    sp = status_path(out)
    if not sp.exists():
        s = cfg.get("strategy", {})
        head = ["# STATUS — %s %s" % ("концепция" if concept else "стратегия", cfg.get("product", {}).get("name", out.name)), "",
                "Создано: %s. Глубина: %s, предложений ≥ %s, горизонт %s мес + %s г." % (
                    now_s(), s.get("depth", "?"), s.get("proposals_min", "?"),
                    s.get("horizon_months", "?"), s.get("vision_years", "?")), "", "## Фазы"]
        if concept:
            head.insert(3, "Режим: идея → концепция продукта (продукта ещё нет). Идея: %s" % ((cfg.get("idea") or {}).get("pitch") or "—"))
        if external:
            head.insert(3, "Режим: внешний продукт без кода (product.mode=external) — источники: сайт, магазины, APK, трекер")
        head += ["- [ ] %s. %s" % (n, EXTERNAL_PHASE_TEXT.get(n, t) if external else t) for n, t in (CONCEPT_PHASES if concept else PHASES)]
        if external:
            head += ["", "## Не применяется (режим external)"] + ["- — %s: %s" % (k, why) for k, why in EXTERNAL_SKIPPED]
        head += ["", "## Чекпоинты", ""]
        sp.write_text("\n".join(head), encoding="utf-8")
    target, why = tasks_target(out, cfg, tasks_file)
    if target is None:
        tp = out / "STRATEGY_TASKS.md"
        if not tp.exists():
            tp.write_text("# STRATEGY_TASKS — чек-лист прогона %s\n\nФазы — в build/STATUS.md; здесь — найденные по дороге задачи.\n\n"
                          "- [ ] %s по build/STATUS.md\n\n## Где остановился\n\n—\n" % (("концепции", "фазы C0–C9") if concept else ("стратегии", "фаза 0–9")),
                          encoding="utf-8")
    else:
        sync_tasks_file(out)
        print("Чек-лист: %s (%s) — блок фаз синхронизируется со STATUS.md; STRATEGY_TASKS.md не создаётся" % (target.name, why))
    if cfg and concept and not (cfg.get("output") or {}).get("inside_repo", True):
        print("Папка концепции ВНЕ git-репозитория (в git не попадёт). Нужна в репозитории: "
              "init_run.py %s --relocate <repo>/concept/<имя>/<дата> --repo <repo> --inside-repo" % out, file=sys.stderr)
    elif cfg and not (cfg.get("output") or {}).get("inside_repo", True):
        print("ВНИМАНИЕ: результат лежит ВНЕ репозитория (в git проекта не попадёт). Если нужна папка внутри репозитория: "
              "init_run.py %s --relocate <repo>/strategy/<дата> --repo <repo> --inside-repo" % out, file=sys.stderr)
    print("OUT=%s" % out)
    return 0


def add_status(out, text):
    sp = status_path(out)
    with sp.open("a", encoding="utf-8") as f:
        f.write("- %s — %s\n" % (now_s(), sanitize(out, text.strip())))
    return 0


PHASE_LINE = re.compile(r"^- \[( |x)\] (C?[\d.]+)\. (.*)$", re.M)


def phases_in(s):
    """[(номер, отмечена, текст)] из STATUS.md (или блока TASKS.md)."""
    return [(m.group(2), m.group(1) == "x", m.group(3)) for m in PHASE_LINE.finditer(s)]


def resolve_phase(s, n):
    """Номер фазы из аргумента: «3» в режиме идеи = «C3»."""
    n = str(n).strip()
    nums = [p for p, _, _ in phases_in(s)]
    for cand in (n, n.upper(), "C" + n):
        if cand in nums:
            return cand
    return None


def check_phase(s, n):
    return re.sub(r"^- \[ \] %s\. " % re.escape(n), "- [x] %s. " % n, s, count=1, flags=re.M)


def uncheck_phase(s, n):
    return re.sub(r"^- \[x\] %s\. " % re.escape(n), "- [ ] %s. " % n, s, count=1, flags=re.M)


def ensure_decisions(out, num):
    """FB-049: после фазы оценки (6 / C6) — data/decisions.json заготовкой decisions.py --init, если файла нет."""
    if str(num) not in ("6", "C6"):
        return None
    out = Path(out)
    if (out / "data" / "decisions.json").exists() or not (HERE / "decisions.py").exists():
        return None
    try:
        r = subprocess.run([sys.executable, "-B", str(HERE / "decisions.py"), str(out), "--init"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode == 0 and (out / "data" / "decisions.json").exists():
        print("data/decisions.json создан заготовкой (decisions.py --init): уточните ставки, North Star и критерии отказа")
        return True
    return False


def mark_done(out, n, force=False, strict=None):
    sp = status_path(out)
    s = sp.read_text(encoding="utf-8")
    num = resolve_phase(s, n)
    if num is None:
        print("нет фазы %s в STATUS.md" % n, file=sys.stderr)
        return 1
    cfg = load_cfg(out)
    strict = bool((cfg.get("tools") or {}).get("strict_phases")) if strict is None else strict
    miss = [] if phase_disabled(cfg, num) else missing_artifacts(out, cfg, num)
    if miss and strict and not force:
        print("отказ: у фазы %s нет обязательных артефактов: %s. Создайте их или повторите с --force (причину — в --status)."
              % (num, ", ".join(miss)), file=sys.stderr)
        return 2
    s2 = check_phase(s, num)
    if s2 == s:
        if re.search(r"^- \[x\] %s\. " % re.escape(num), s, re.M):
            ensure_decisions(out, num)
            return 0
        return 1
    if miss:
        print("ВНИМАНИЕ: фаза %s отмечена без артефактов: %s" % (num, ", ".join(miss)), file=sys.stderr)
        s2 = s2.rstrip("\n") + "\n- %s — фаза %s отмечена%s без артефактов: %s\n" % (
            now_s(), num, " с --force" if force else "", ", ".join(miss))
    sp.write_text(s2, encoding="utf-8")
    ensure_decisions(out, num)
    sync_tasks_file(out)
    return 0


def phase_report(out):
    """Состояние фаз → (список словарей, следующая фаза по факту | None)."""
    s = status_path(out).read_text(encoding="utf-8")
    cfg = load_cfg(out)
    rows = []
    for num, checked, text in phases_in(s):
        disabled = phase_disabled(cfg, num)
        miss = [] if disabled else missing_artifacts(out, cfg, num)
        has_own = bool(PHASE_ARTIFACTS.get(num))
        by_art = has_own and not miss and not disabled
        rows.append({"num": num, "text": text, "checked": checked, "disabled": disabled, "missing": miss,
                     "by_artifacts": by_art, "done": checked or by_art or disabled})
    last = max((i for i, r in enumerate(rows) if (r["checked"] or r["by_artifacts"]) and not r["disabled"]), default=-1)
    nxt = next((r for r in rows[last + 1:] if not r["disabled"] and not r["done"]), None)
    return rows, nxt


def open_phases(out):
    """Фазы без отметки, без артефактов и не выключенные выбором (ворота FB-015) → [(номер, причина)]."""
    rows, _ = phase_report(out)
    return [(r["num"], ", ".join(r["missing"]) or "не отмечена (--done %s)" % r["num"]) for r in rows if not r["done"]]


def sync(out, quiet=False):
    """Отмечает фазы, все обязательные артефакты которых есть → список номеров."""
    rows, _ = phase_report(out)
    todo = [r["num"] for r in rows if not r["checked"] and r["by_artifacts"]]
    if todo:
        sp = status_path(out)
        s = sp.read_text(encoding="utf-8")
        for n in todo:
            s = check_phase(s, n)
        s = s.rstrip("\n") + "\n- %s — по артефактам отмечены фазы: %s (init_run.py)\n" % (now_s(), ", ".join(todo))
        sp.write_text(s, encoding="utf-8")
        if not quiet:
            print("по артефактам отмечены фазы: %s" % ", ".join(todo))
        for n in todo:
            ensure_decisions(out, n)
    sync_tasks_file(out, quiet=quiet)
    return todo


# ---------------------------------------------------------------- агенты (build/agents.json, dispatch.py)
def norm_phase(value, concept):
    m = re.match(r"^C?(\d+(?:\.5)?)", str(value or "").strip(), re.I)
    if not m:
        return None
    return ("C" if concept else "") + m.group(1)


def agents_by_phase(out, cfg):
    """{фаза: {"total", "done", "running": [id], "pending": [id], "failed": [id], "started": [iso]}} из build/agents.json."""
    try:
        st = json.loads((Path(out) / "build" / "agents.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    concept = cfg.get("mode") == "concept"
    res = {}
    for t in st.get("tasks") or []:
        ph = norm_phase(t.get("phase") or t.get("wave"), concept)
        if not ph:
            continue
        d = res.setdefault(ph, {"total": 0, "done": 0, "running": [], "pending": [], "failed": [], "started": [], "kinds": []})
        d["total"] += 1
        stt = t.get("status")
        if stt == "done":
            d["done"] += 1
        elif stt in ("running", "pending", "failed"):
            d[stt].append(t.get("id"))
        if stt == "running" and t.get("started"):
            d["started"].append(t["started"])
        if t.get("kind"):
            d["kinds"].append(t["kind"])
    return res


def waves_lines(out, cfg):
    """«C7: 5 агентов, 3 готовы, ждём S2, S4» — по фазам из agents.json (FB-014)."""
    L = []
    for ph, d in agents_by_phase(out, cfg).items():
        wait = d["running"] + d["pending"]
        L.append("  %s: %d агент(ов), готово %d%s%s" % (ph, d["total"], d["done"], (", ждём %s" % ", ".join(wait)) if wait else "",
                                                       (", не выполнено %s" % ", ".join(d["failed"])) if d["failed"] else ""))
    return L


# ---------------------------------------------------------------- ветка (FB-034)
def current_branch(top):
    try:
        r = subprocess.run(["git", "-C", str(top), "symbolic-ref", "--short", "-q", "HEAD"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None


BRANCH_STATUS = {"created": "создана скриптом", "switched": "переключена", "current": "уже была текущей", "skipped": "не создавалась",
                 "failed": "не удалось создать", "planned": "запланирована (dry-run)"}


def branch_line(out, cfg):
    top = repo_top(out)
    o = cfg.get("output") or {}
    want = o.get("git_branch")
    if not top:
        return None
    cur = current_branch(top)
    st = o.get("branch_status")
    tail = ""
    if st or o.get("branch_note"):                      # FB-034: как intake.py concept-apply обошёлся с веткой прогона
        tail = "; при создании прогона: %s%s" % (BRANCH_STATUS.get(st, st or "—"), " — %s" % o["branch_note"] if o.get("branch_note") else "")
    if not want:
        return "Ветка: %s (в run-config output.git_branch не задана)%s" % (cur or "?", tail)
    if cur == want:
        return "Ветка: %s — совпадает с run-config%s" % (cur, tail)
    return ("ВНИМАНИЕ: текущая ветка %s, а в run-config output.git_branch = %s — переключитесь (git switch %s) "
            "или исправьте run-config (intake.py update <OUT> --set output.git_branch=%s)%s" % (cur or "?", want, want, cur or "<ветка>", tail))


def open_items(out):
    """Открытые пункты сверки (B9): расхождения модели с планом и реестром (data/model.json → reconciliation.items) и дыры
    Ганта (data/plan-baseline.json → gantt_contract.messages) → [строка]."""
    res = []
    for rel, getter, label in (("data/model.json", lambda d: (d.get("reconciliation") or {}).get("items") or [], "модель ↔ план/реестр"),
                               ("data/plan-baseline.json", lambda d: (d.get("gantt_contract") or {}).get("messages") or [], "Гант")):
        try:
            d = json.loads((Path(out) / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        for it in getter(d):
            msg = it.get("message") if isinstance(it, dict) else it
            if msg:
                res.append("%s: %s (%s)" % (label, msg, rel))
    return res


def show(out, do_sync=True):
    if do_sync:
        sync(out)
    cfg = load_cfg(out)
    rows, nxt = phase_report(out)
    for r in rows:
        if r["disabled"]:
            st = "выключена выбором"
        elif r["checked"] and r["missing"]:
            st = "отмечена, но нет: %s" % ", ".join(r["missing"])
        elif r["checked"]:
            st = "готова"
        elif r["by_artifacts"]:
            st = "готова по артефактам (не отмечена: --sync)"
        elif not PHASE_ARTIFACTS.get(r["num"]):
            st = "открыта (своих артефактов нет — отметить --done %s)" % r["num"]
        else:
            st = "открыта, нет: %s" % ", ".join(r["missing"])
        print("  [%s] %-5s %s" % ("x" if r["done"] else " ", r["num"], st))
    idx = {r["num"]: i for i, r in enumerate(rows)}
    gaps = [r for r in rows[:idx[nxt["num"]] if nxt else len(rows)] if not r["done"]]
    print("Следующая фаза: %s" % ("%s. %s" % (nxt["num"], nxt["text"]) if nxt else "все фазы отмечены"))
    if gaps:
        print("Пропущены раньше (нет отметки и артефактов): %s" % ", ".join(
            "%s (%s)" % (r["num"], ", ".join(r["missing"]) or "отметить --done") for r in gaps))
    wl = waves_lines(out, cfg)
    if wl:
        print("Агенты по фазам (build/agents.json):")
        for line in wl:
            print(line)
    elif cfg.get("mode") == "concept":
        print("Агенты: build/agents.json пуст — запуски записывайте через dispatch.py (add / ready --start / done)")
    bl = branch_line(out, cfg)
    if bl:
        print(bl)
    target, why = tasks_target(out, cfg)
    print("Чек-лист: %s" % ("%s (%s; блок фаз синхронизирован со STATUS.md)" % (target.name, why) if target else "STRATEGY_TASKS.md (%s)" % why))
    n_int = count_interventions(out)
    if n_int:
        print("Ручных вмешательств в журнале: %d (build/interventions.jsonl)" % n_int)
    oi = open_items(out)
    if oi:
        print("Открытые пункты сверки (%d):" % len(oi))
        for x in oi[:10]:
            print("  - " + x)
    s = status_path(out).read_text(encoding="utf-8")
    cps = re.findall(r"^- \d{4}-\d\d-\d\d .*$", s, re.M)
    for c in cps[-5:]:
        print(c)
    return 0


# ---------------------------------------------------------------- статус с ETA (SM 10.2)
def forecast_minutes(cfg, concept):
    """Минуты на фазу по прогнозу dispatch.py (агенты) → {фаза: минут}."""
    try:
        sys.path.insert(0, str(HERE))
        import dispatch
        depth = (cfg.get("strategy") or {}).get("depth") or "standard"
        if depth not in dispatch.DEPTH_AGENTS:
            depth = "standard"
        fc = dispatch.forecast(depth, dispatch.max_parallel(cfg), cfg)
    except Exception:                                  # noqa: BLE001 — статус работает и без прогноза
        return {}
    res = {}
    for r in fc.get("phases") or []:
        m = re.search(r"\d+", str(r.get("minutes")))
        if not m:
            continue
        mins = int(m.group(0))
        ph = str(r.get("phase"))
        if "7+8" in str(r.get("minutes")):
            mins = round(mins / 2)                      # фазы 7 и 8 идут общими волнами — делим пополам
        res[("C" if concept else "") + ph] = mins
    return res


def first_existing(out, rels):
    found = []
    for rel in rels:
        p = Path(out) / rel
        if rel.endswith("/"):
            if p.is_dir() and any(p.iterdir()):
                found.append(rel)
        elif p.exists():
            found.append(rel)
    return found


def status_table(out):
    cfg = load_cfg(out)
    concept = cfg.get("mode") == "concept"
    rows, nxt = phase_report(out)
    agents = agents_by_phase(out, cfg)
    fmins = forecast_minutes(cfg, concept)
    now = datetime.now()
    table, total = [], 0
    for r in rows:
        num = r["num"]
        ag = agents.get(num) or {}
        running = ag.get("running") or []
        if r["disabled"]:
            st, eta = "выключена выбором", 0
        elif r["done"]:
            st, eta = "готова", 0
        else:
            base = fmins.get(num, ORCH_MINUTES.get(num, 20))
            if running:
                el = 0
                for s in ag.get("started") or []:
                    try:
                        el = max(el, (now - datetime.fromisoformat(s)).total_seconds() / 60)
                    except ValueError:
                        pass
                eta = max(5, round(base - el))
                st = "идёт (агентов работает %d)" % len(running)
            else:
                eta = base
                st = "следующая" if nxt and num == nxt["num"] else "открыта"
        total += eta
        who = ", ".join(running) if running else ("ждут: %s" % ", ".join(ag["pending"]) if ag.get("pending") else ("оркестратор" if st in ("следующая",) else "—"))
        table.append({"phase": num, "status": st, "open": first_existing(out, OPEN_FILES.get(num, [])), "eta_min": eta, "who": who,
                      "text": r["text"]})
    can_open = first_existing(out, ["build/preview/index.html", "deliverables/index.html", "research/idea-dossier.md", "research/market.md",
                                    "research/integration.md", "mockups/gallery.html", "research/strategy.md", "deliverables/REPORT.md"])
    hint = None
    if "build/preview/index.html" not in can_open and (Path(out) / "data" / "proposals.json").exists():
        hint = "черновую страницу можно собрать: build_all.py <OUT> --preview → build/preview/index.html"
    return {"rows": table, "remaining_min": total, "can_open": can_open, "hint": hint, "open_items": open_items(out),
            "branch": branch_line(out, cfg),
            "basis": "агенты — прогноз dispatch.py forecast (±30 %), фазы без агентов — типовые минуты оркестратора"}


def print_status_table(st):
    if not st["rows"]:
        print("В build/STATUS.md нет чек-листа фаз (демо или прогон без init_run.py) — статус по фазам недоступен")
    print("| Фаза | Статус | Что открыть сейчас | ETA | Кто работает |")
    print("|---|---|---|---|---|")
    for r in st["rows"]:
        print("| %s | %s | %s | %s | %s |" % (r["phase"], r["status"], ", ".join("`%s`" % x for x in r["open"]) or "—",
                                            ("≈%d мин" % r["eta_min"]) if r["eta_min"] else "—", r["who"]))
    if st["can_open"]:
        print("Можно открыть уже сейчас: %s" % ", ".join(st["can_open"]))
    if st.get("hint"):
        print(st["hint"])
    if st.get("open_items"):
        print("Открытые пункты сверки: %s" % "; ".join(st["open_items"][:6]))
    if st.get("branch"):
        print(st["branch"])
    m = st["remaining_min"]
    print("Осталось ≈ %d ч %02d мин (%s)" % (m // 60, m % 60, st["basis"]))


# ---------------------------------------------------------------- журнал вмешательств (FB-004)
def looks_like_path(s):
    return bool(re.search(r"/|\.(md|json|py|mjs|html|css|txt|csv|jsonl)$", s.strip()))


def parse_intervention(text, why=None, file=None):
    what = text.strip()
    if why is None and file is None:
        if " | " in what:
            parts = [x.strip() for x in what.split(" | ")]
            what, why, file = parts[0], (parts[1] if len(parts) > 1 else None), (parts[2] if len(parts) > 2 else None)
        else:
            parts = [x.strip() for x in what.split(",")]
            if len(parts) >= 3 and looks_like_path(parts[-1]):
                what, why, file = ", ".join(parts[:-2]), parts[-2], parts[-1]
    return what, why, file


def guess_kind(file, what):
    f = (file or "").replace("\\", "/")
    if "build/briefs/" in f or re.search(r"\bбриф", what or "", re.I):
        return "brief"
    if f.endswith(("run-config.json", "model-params.json", "overrides.json", "pairs.json", "merge-map.json", "decisions.json")):
        return "data-edit"
    if f:
        return "file-edit"
    return "other"


def add_intervention(out, text, by="orchestrator", why=None, file=None, kind=None, phase=None):
    cfg = load_cfg(out)
    what, why, file = parse_intervention(text, why, file)
    if phase is None and status_path(out).exists():
        _rows, nxt = phase_report(out)
        phase = nxt["num"] if nxt else None
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "by": by, "what": sanitize(out, what, cfg),
           "why": sanitize(out, why, cfg) if why else None, "file": sanitize(out, file, cfg) if file else None,
           "kind": kind or guess_kind(file, what), "phase": phase}
    p = Path(out) / INTERVENTIONS
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_interventions(out):
    p = Path(out) / INTERVENTIONS
    res = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                res.append(json.loads(line))
            except ValueError:
                continue
    return res


def count_interventions(out):
    return len(read_interventions(out))


# ---------------------------------------------------------------- протокол смены решения (SM 10.1)
IMPACT = [   # (шаблон ключа/слова, фазы, файлы (glob), команды)
    (r"idea\b|idea\.pitch|pivot|пивот|иде[яи]", ["C1", "C2", "C3", "C4.5", "C5", "C7", "C8"],
     ["data/idea.json", "data/premises.json", "research/idea-dossier.md", "build/seeds.md", "build/search-plan.md", "build/parts/strategy-*.md"],
     ["pivot_check.py <OUT> --decide narrow --pitch-v2 \"…\"", "concept_dossier.py <OUT> --refresh", "typesafe_concept.py <OUT>",
      "render_brief.py … --auto (брифы следующих фаз)"]),
    (r"product\.type|product\.forms|forms?\b|форм|платформ|mobile|мобил|веб|web", ["C3", "C5", "C6", "C8"],
     ["build/seeds.md", "data/proposals.json", "data/model.json", "build/model-params.json", "mockups/concepts/*.html"],
     ["concept_dossier.py <OUT> --refresh", "model.py <OUT>", "mockup_kit.py init <OUT> --forms …", "build_all.py <OUT>"]),
    (r"audience|аудитор|личн|personal|circle", ["C3", "C4", "C5", "C6", "C7", "C8"],
     ["data/proposals.json", "data/model.json", "build/parts/strategy-*.md", "mockups/concepts/*.html"],
     ["check_registry.py <OUT>", "model.py <OUT> --profile personal", "render_brief.py strategy-section … --auto", "build_all.py <OUT>"]),
    (r"capacity|ёмкост|емкост|часов|hours|срок|deadline", ["C5", "C6", "C7"],
     ["data/model.json", "data/plan-baseline.json", "data/gantt.json", "build/parts/strategy-1[04].md", "build/strategy-facts.md"],
     ["model.py <OUT>", "merge_proposals.py <OUT> --cap-now", "score.py <OUT>", "plan_baseline.py <OUT>", "assemble_strategy.py <OUT>"]),
    (r"design|дизайн|направлени|режим[ыа]? интерфейса|modes?\b|токен", ["C8", "C9"],
     ["design/directions.md", "mockups/tokens*.css", "mockups/concepts/*.html", "mockups/gallery.html", "design-refs/*.md"],
     ["render_brief.py concept-design --out <OUT> --auto (design.chosen)", "node shoot_mockups.mjs <OUT>", "link_mockups.py <OUT>"]),
    (r"monetiz|монетиз|цен[аы]|price|тариф|платеж|оплат", ["C6", "C7"],
     ["data/model.json", "build/model-params.json", "build/parts/strategy-08.md", "build/parts/strategy-12.md"],
     ["model.py <OUT>", "assemble_strategy.py <OUT>"]),
    (r"horizon|горизонт|видени", ["C6", "C7"], ["data/gantt.json", "data/plan-baseline.json", "build/parts/strategy-14.md"],
     ["plan_baseline.py <OUT>", "charts.py <OUT> --only gantt", "assemble_strategy.py <OUT>"]),
    (r"bet|ставк|north.?star|kill|критери[йи] отказа|anti|decision|решени", ["C7"],
     ["data/decisions.json", "build/strategy-facts.md", "build/parts/strategy-*.md"],
     ["decisions.py <OUT> --check", "facts_scaffold.py <OUT> --draft", "assemble_strategy.py <OUT>"]),
    (r"prototype|прототип", ["C8.5"], ["prototype/**/*"], ["render_brief.py prototype-core --out <OUT> --auto"]),
]
PID_RE = re.compile(r"\b(P\d{3,4})\b")


def files_mentioning(out, needles, globs=("build/parts/*.md", "research/*.md", "research/specs/*.md", "research/experiments/*.md",
                                           "mockups/concepts/*.html", "design-refs/*.md", "data/gantt.json", "data/kanban.json",
                                           "data/decisions.json")):
    hits = []
    for g in globs:
        for f in sorted(Path(out).glob(g)):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(n in text for n in needles):
                hits.append(f.relative_to(out).as_posix())
    return hits


def impact(out, what, keys=None):
    """→ {phases, files, commands, proposals} для смены решения."""
    out = Path(out)
    cfg = load_cfg(out)
    concept = cfg.get("mode") == "concept"
    text = " ".join([what or ""] + list(keys or []))
    phases, files, cmds = [], [], []
    for pat, phs, globs, cc in IMPACT:
        if re.search(pat, text, re.I):
            for p in phs:
                p = p if concept else p.lstrip("C")
                if p not in phases:
                    phases.append(p)
            for g in globs:
                for f in sorted(out.glob(g)):
                    rel = f.relative_to(out).as_posix()
                    if rel not in files:
                        files.append(rel)
            for c in cc:
                if c not in cmds:
                    cmds.append(c)
    pids = sorted(set(PID_RE.findall(text)))
    if pids:
        for p in ("C6", "C7", "C8") if concept else ("6", "7", "8"):
            if p not in phases:
                phases.append(p)
        for f in files_mentioning(out, pids):
            if f not in files:
                files.append(f)
        cmds += [c for c in ("правка — в build/overrides.json, затем merge_proposals.py <OUT>", "score.py <OUT>", "assemble_strategy.py <OUT>")
                 if c not in cmds]
    if not phases:                                     # свободный текст: части текста, где встречаются слова
        words = [w for w in re.findall(r"[\wёЁ-]{5,}", what or "")][:6]
        for f in files_mentioning(out, words):
            if f not in files:
                files.append(f)
        cmds.append("assemble_strategy.py <OUT>")
    cmds.append("build_all.py <OUT> --preview (посмотреть), затем build_all.py <OUT> --strict (сдача)")
    order = [r[0] for r in CONCEPT_PHASES] if concept else [str(r[0]) for r in PHASES]
    phases.sort(key=lambda p: order.index(p) if p in order else 99)
    return {"what": what, "keys": list(keys or []), "phases": phases, "files": files, "commands": cmds, "proposals": pids}


def reopen(out, phases):
    sp = status_path(out)
    if not sp.exists():
        return []
    s = sp.read_text(encoding="utf-8")
    done = []
    for p in phases:
        num = resolve_phase(s, p)
        if num and re.search(r"^- \[x\] %s\. " % re.escape(num), s, re.M):
            s = uncheck_phase(s, num)
            done.append(num)
    if done:
        s = s.rstrip("\n") + "\n- %s — смена решения: сняты отметки фаз %s (init_run.py --impact --reopen)\n" % (now_s(), ", ".join(done))
        sp.write_text(s, encoding="utf-8")
        cfg = load_cfg(out)
        target, _ = tasks_target(out, cfg)
        if target and target.exists():                 # снять отметки и в блоке TASKS.md (иначе синхронизация вернёт их)
            key = rel_display(out, cfg)
            text = target.read_text(encoding="utf-8")
            m = block_re(key).search(text)
            if m:
                blk = m.group(0)
                for n in done:
                    blk = uncheck_phase(blk, n)
                target.write_text(text[:m.start()] + blk + text[m.end():], encoding="utf-8")
    return done


OWNER_ROLES = {"base": "основа вопросов (выводы не копировать, расхождения — в fact-check)", "follow": "следовать",
               "ref": "справка", "competitor": "эталон-конкурент", "benchmark": "эталон-конкурент"}


def owner_materials(out):
    """FB-002: каркас build/owner-materials.md по sources.owner_docs[] → (путь, добавлено ссылок)."""
    cfg = load_cfg(out)
    docs = [d if isinstance(d, dict) else {"url": d} for d in ((cfg.get("sources") or {}).get("owner_docs") or []) if d]
    p = Path(out) / "build" / "owner-materials.md"
    text = p.read_text(encoding="utf-8") if p.exists() else (
        "# Материалы владельца\n\nПротокол (references/orchestration.md → «Материалы владельца»): каждую ссылку прочитать доступным "
        "инструментом (веб-загрузка; ссылка на артефакт claude.ai — инструмент чтения артефактов) и записать статус `read | blocked` "
        "с причиной; `not_attempted` в сдаче недопустим (build_all --strict). Прежнее исследование — основа вопросов: выводы не "
        "копировать, расхождения — в data/fact-check.json.\n\n")
    added = 0
    for d in docs:
        url = str(d.get("url") or "").strip()
        if not url or url in text:
            continue
        role = d.get("role") or d.get("kind") or "ref"
        text += ("## %s\n- Роль: %s — %s\n- Статус: %s\n- Инструмент: %s\n- Выжимка (5–10 строк): <заполнить>\n- Как используется: <заполнить>\n\n"
                 % (url, role, OWNER_ROLES.get(role, "справка"), d.get("status") or "not_attempted", d.get("tool") or "<веб / чтение артефакта>"))
        added += 1
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p, added


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--owner-materials", action="store_true", help="каркас build/owner-materials.md по sources.owner_docs[]")
    ap.add_argument("--status", nargs="?", const="__TABLE__", help="текст чекпоинта; без текста — таблица статуса с ETA")
    ap.add_argument("--status-json", action="store_true", help="таблица статуса в JSON")
    ap.add_argument("--done", help="номер фазы (0–9 или 5.5; в режиме идеи — C0…C9, C4.5, C5.5, C7.5, C8.5)")
    ap.add_argument("--force", action="store_true", help="с --done: отметить, даже если нет артефактов фазы")
    ap.add_argument("--require-artifacts", action="store_true", help="с --done: без артефактов — отказ (код 2)")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--sync", action="store_true", help="отметить фазы, артефакты которых уже есть")
    ap.add_argument("--no-sync", action="store_true", help="с --show: не отмечать фазы по артефактам")
    ap.add_argument("--tasks-file", help="чек-лист: TASKS.md (корень репозитория) | STRATEGY_TASKS.md | auto")
    ap.add_argument("--intervention", help="ручное вмешательство: «что | почему | файл»")
    ap.add_argument("--by", default="orchestrator", choices=("owner", "orchestrator", "agent"), help="кто вмешался (с --intervention/--impact)")
    ap.add_argument("--why")
    ap.add_argument("--file")
    ap.add_argument("--kind", help="brief | data-edit | file-edit | decision-change | other (по умолчанию — по файлу)")
    ap.add_argument("--impact", help="смена решения: что меняется (анализ влияния)")
    ap.add_argument("--keys", default="", help="с --impact: ключи run-config, P-id, темы через запятую")
    ap.add_argument("--reopen", action="store_true", help="с --impact: снять отметки затронутых фаз")
    ap.add_argument("--json", action="store_true", help="с --impact: вывод JSON")
    ap.add_argument("--relocate", metavar="NEW")
    ap.add_argument("--repo")
    ap.add_argument("--inside-repo", dest="inside", action="store_true", default=None)
    ap.add_argument("--no-inside-repo", dest="inside", action="store_false")
    ap.add_argument("--branch")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.relocate:
        rl = HERE / "relocate_run.py"
        if not rl.exists():
            print("нет relocate_run.py рядом со скриптом", file=sys.stderr)
            return 2
        cmd = [sys.executable, str(rl), a.out, a.relocate] + (["--repo", a.repo] if a.repo else []) + (["--branch", a.branch] if a.branch else []) \
            + (["--inside-repo"] if a.inside is True else ["--no-inside-repo"] if a.inside is False else []) + (["--dry-run"] if a.dry_run else [])
        return subprocess.call(cmd)
    table = a.status == "__TABLE__" or a.status_json
    acts = (a.status and not table) or a.done is not None or a.show or a.sync or table or a.intervention or a.impact or a.owner_materials
    if not status_path(a.out).exists() or not acts:
        init(a.out, a.tasks_file)
    elif a.tasks_file:
        cfg = load_cfg(a.out)
        cfg.setdefault("output", {})["tasks_file"] = a.tasks_file
        save_cfg(a.out, cfg)
        target = sync_tasks_file(a.out)
        print("Чек-лист: %s" % (target if target else "STRATEGY_TASKS.md"))
    if a.owner_materials:
        p, n = owner_materials(a.out)
        print("build/%s: добавлено ссылок %d — прочитать каждую и записать статус (read | blocked), выжимку и как используется" % (p.name, n))
    if a.intervention:
        rec = add_intervention(a.out, a.intervention, a.by, a.why, a.file, a.kind)
        print("вмешательство записано (%s, %s): %s → %s" % (rec["by"], rec["kind"], rec["what"], INTERVENTIONS))
    if a.impact:
        rep = impact(a.out, a.impact, [k.strip() for k in a.keys.split(",") if k.strip()])
        if a.reopen:
            rep["reopened"] = reopen(a.out, rep["phases"])
        add_intervention(a.out, "смена решения: %s" % a.impact, a.by, why="затронуты фазы %s" % (", ".join(rep["phases"]) or "—"),
                         kind="decision-change")
        if a.json:
            print(json.dumps(rep, ensure_ascii=False, indent=2))
        else:
            print("Смена решения: %s" % a.impact)
            print("Затронутые фазы: %s%s" % (", ".join(rep["phases"]) or "—", ("; сняты отметки: %s" % ", ".join(rep["reopened"])) if rep.get("reopened") else ""))
            print("Предложения: %s" % (", ".join(rep["proposals"]) or "—"))
            print("Файлы к правке/пересборке (%d):" % len(rep["files"]))
            for f in rep["files"][:40]:
                print("  - %s" % f)
            print("Команды по порядку:")
            for i, c in enumerate(rep["commands"], 1):
                print("  %d. %s" % (i, c))
            print("Решение владельца — в data/decisions.json (decisions.py) или run-config; отчёт об изменении — init_run.py --status \"…\"")
    if a.status and not table:
        add_status(a.out, a.status)
    if a.done is not None:
        code = mark_done(a.out, a.done, force=a.force, strict=True if a.require_artifacts else None)
        if code or not (a.show or table):
            return code
    if a.sync and not a.show:
        sync(a.out)
        if not table:
            return 0
    if table:
        st = status_table(a.out)
        print(json.dumps(st, ensure_ascii=False, indent=2) if a.status_json else "", end="")
        if not a.status_json:
            print_status_table(st)
        return 0
    if a.show:
        return show(a.out, do_sync=not a.no_sync)
    return 0


if __name__ == "__main__":
    sys.exit(main())
