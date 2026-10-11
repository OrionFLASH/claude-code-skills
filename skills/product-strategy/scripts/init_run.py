#!/usr/bin/env python3
"""Создаёт папку прогона <OUT> по run-config: подпапки, build/STATUS.md с чек-листом фаз, .gitignore для node-модулей.

  init_run.py <OUT>                  по <OUT>/build/run-config.json (его пишет intake.py)
  init_run.py <OUT> --status "фаза 3 готова: …"   дописать строку в STATUS.md (чекпоинт)
  init_run.py <OUT> --done 3         отметить фазу 3 выполненной; проверяет обязательные артефакты фазы (PHASE_ARTIFACTS):
                                     без них — предупреждение и пометка «без артефактов» в STATUS.md; с --require-artifacts
                                     (или run-config tools.strict_phases: true) — отказ (код 2), пока не будет --force
  init_run.py <OUT> --show           фазы по чек-листу и по артефактам, следующая фаза по факту, последние чекпоинты;
                                     фазы, чьи артефакты уже есть, отмечаются автоматически (--no-sync — только показать)
  init_run.py <OUT> --sync           только отметить фазы по артефактам
  init_run.py <OUT> --relocate <NEW> [--repo R] [--inside-repo|--no-inside-repo] [--branch B] [--dry-run]
                                     перенос папки прогона: пути в файлах заменяются (relocate_run.py), run-config обновляется;
                                     дальше `build_all.py <NEW>` и `check_gitignore.py <NEW>`
Строки --status и записи в STATUS.md хранятся без абсолютных путей: <OUT> → путь от корня репозитория (или «<OUT>»),
домашняя папка → «~».
Чек-лист задач прогона — STRATEGY_TASKS.md (не TASKS.md: в корне репозитория пользователя свой TASKS.md).
Режим идеи (run-config mode: concept, references/concept-mode.md) — фазы C0…C9 и C5.5; `--done 3` и `--done C3` равносильны.
Внешний продукт (product.mode: external, references/external-product.md) — фазы 0–9 с текстами фаз 1–3 «без кода» (store_stats,
app_scan, сайт, трекер); repo_scan/repo_facts — строками «—» в разделе «Не применяется».

Только стандартная библиотека.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

DIRS = ["build/briefs", "research/specs", "research/experiments", "data", "charts/flows", "mockups/current", "mockups/concepts",
        "design-refs", "competitors/shots", "deliverables"]
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
    ("C5", "Реестр решений (≥ proposals_min): генерация → merge_proposals → check_registry"),
    ("C5.5", "Аудит предпосылок: юрлицо, домен, прототип, первые пользователи, аккаунты платформ (gap_audit.py)"),
    ("C6", "Оценка: score, validate_scores, typesafe_eval, model, charts"),
    ("C7", "Текст концепции по references/concept-outline.md, спеки MVP, эксперименты, Гант, Kanban"),
    ("C8", "Дизайн: язык дизайна, макеты ключевых экранов, референсы аналогов"),
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
    "C5": [("data/proposals.json", None)],
    "C5.5": [("research/gap-audit.md", None)],
    "C6": [("data/scores.json", None)],
    "C7": [("research/strategy.md", None), ("data/gantt.json", None)],
    "C8": [("mockups/tokens.css", None)],
    "C9": [("deliverables/index.html", None), ("deliverables/REPORT.md", None)],
}
PHASE_SWITCH = {"5.5": "phases.gap_audit", "C5.5": "phases.gap_audit"}     # фаза выключена выбором владельца


def load_cfg(out):
    try:
        return json.loads((Path(out) / "build" / "run-config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def cfg_get(cfg, dotted, default=True):
    cur = cfg
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def artifact_ok(path):
    """Файл есть и не пустой (JSON — разбирается и не пустой контейнер)."""
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            return data not in ([], {}, None, "")
        return bool(path.read_text(encoding="utf-8", errors="replace").strip())
    except (OSError, json.JSONDecodeError):
        return False


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
    return miss


def phase_disabled(cfg, phase):
    key = PHASE_SWITCH.get(str(phase))
    return bool(key) and cfg_get(cfg, key, True) is False


def rel_display(out, cfg=None):
    """<OUT> для записей: путь от корня репозитория (run-config repo.path или git), иначе «<OUT>»."""
    out = Path(out).resolve()
    cfg = cfg if cfg is not None else load_cfg(out)
    repo = (cfg.get("repo") or {}).get("path")
    cands = [Path(repo).expanduser().resolve()] if repo else []
    p = out
    while p != p.parent:
        if (p / ".git").exists():
            cands.append(p)
            break
        p = p.parent
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


def init(out):
    out = Path(out).resolve()
    cfgp = out / "build" / "run-config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8")) if cfgp.exists() else {}
    for d in DIRS:
        (out / d).mkdir(parents=True, exist_ok=True)
    gi = out / ".gitignore"
    if not gi.exists():
        gi.write_text("!build/\n!data/\n!deliverables/\nbuild/node/\nnode_modules/\n*.tmp\n", encoding="utf-8")   # «!» переопределяют корневые правила (build/)
    else:
        lines = gi.read_text(encoding="utf-8").splitlines()
        add = [x for x in ("build/node/", "node_modules/") if x not in lines]
        if add:
            gi.write_text("\n".join(lines + add) + "\n", encoding="utf-8")
    concept = cfg.get("mode") == "concept"
    external = not concept and (cfg.get("product") or {}).get("mode") == "external"
    sp = status_path(out)
    if not sp.exists():
        s = cfg.get("strategy", {})
        head = ["# STATUS — %s %s" % ("концепция" if concept else "стратегия", cfg.get("product", {}).get("name", out.name)), "",
                "Создано: %s. Глубина: %s, предложений ≥ %s, горизонт %s мес + %s г." % (
                    datetime.now().strftime("%Y-%m-%d %H:%M"), s.get("depth", "?"), s.get("proposals_min", "?"),
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
    tp = out / "STRATEGY_TASKS.md"
    if not tp.exists():
        tp.write_text("# STRATEGY_TASKS — чек-лист прогона %s\n\nФазы — в build/STATUS.md; здесь — найденные по дороге задачи.\n\n"
                      "- [ ] %s по build/STATUS.md\n\n## Где остановился\n\n—\n" % (("концепции", "фазы C0–C9") if concept else ("стратегии", "фаза 0–9")),
                      encoding="utf-8")
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
        f.write("- %s — %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M"), sanitize(out, text.strip())))
    return 0


PHASE_LINE = re.compile(r"^- \[( |x)\] (C?[\d.]+)\. (.*)$", re.M)


def phases_in(s):
    """[(номер, отмечена, текст)] из STATUS.md."""
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
    s2 = re.sub(r"^- \[ \] %s\. " % re.escape(n), "- [x] %s. " % n, s, count=1, flags=re.M)
    return s2


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
        return 1 if not re.search(r"^- \[x\] %s\. " % re.escape(num), s, re.M) else 0
    if miss:
        print("ВНИМАНИЕ: фаза %s отмечена без артефактов: %s" % (num, ", ".join(miss)), file=sys.stderr)
        s2 = s2.rstrip("\n") + "\n- %s — фаза %s отмечена%s без артефактов: %s\n" % (
            datetime.now().strftime("%Y-%m-%d %H:%M"), num, " с --force" if force else "", ", ".join(miss))
    sp.write_text(s2, encoding="utf-8")
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


def sync(out, quiet=False):
    """Отмечает фазы, все обязательные артефакты которых есть → список номеров."""
    rows, _ = phase_report(out)
    todo = [r["num"] for r in rows if not r["checked"] and r["by_artifacts"]]
    if todo:
        sp = status_path(out)
        s = sp.read_text(encoding="utf-8")
        for n in todo:
            s = check_phase(s, n)
        s = s.rstrip("\n") + "\n- %s — по артефактам отмечены фазы: %s (init_run.py)\n" % (datetime.now().strftime("%Y-%m-%d %H:%M"), ", ".join(todo))
        sp.write_text(s, encoding="utf-8")
        if not quiet:
            print("по артефактам отмечены фазы: %s" % ", ".join(todo))
    return todo


def show(out, do_sync=True):
    if do_sync:
        sync(out)
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
    s = status_path(out).read_text(encoding="utf-8")
    cps = re.findall(r"^- \d{4}-\d\d-\d\d .*$", s, re.M)
    for c in cps[-5:]:
        print(c)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--status")
    ap.add_argument("--done", help="номер фазы (0–9 или 5.5; в режиме идеи — C0…C9, C5.5)")
    ap.add_argument("--force", action="store_true", help="с --done: отметить, даже если нет артефактов фазы")
    ap.add_argument("--require-artifacts", action="store_true", help="с --done: без артефактов — отказ (код 2)")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--sync", action="store_true", help="отметить фазы, артефакты которых уже есть")
    ap.add_argument("--no-sync", action="store_true", help="с --show: не отмечать фазы по артефактам")
    ap.add_argument("--relocate", metavar="NEW")
    ap.add_argument("--repo")
    ap.add_argument("--inside-repo", dest="inside", action="store_true", default=None)
    ap.add_argument("--no-inside-repo", dest="inside", action="store_false")
    ap.add_argument("--branch")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.relocate:
        import subprocess
        rl = Path(__file__).resolve().parent / "relocate_run.py"
        if not rl.exists():
            print("нет relocate_run.py рядом со скриптом", file=sys.stderr)
            return 2
        cmd = [sys.executable, str(rl), a.out, a.relocate] + (["--repo", a.repo] if a.repo else []) + (["--branch", a.branch] if a.branch else []) \
            + (["--inside-repo"] if a.inside is True else ["--no-inside-repo"] if a.inside is False else []) + (["--dry-run"] if a.dry_run else [])
        return subprocess.call(cmd)
    if not status_path(a.out).exists() or not (a.status or a.done is not None or a.show or a.sync):
        init(a.out)
    if a.status:
        add_status(a.out, a.status)
    if a.done is not None:
        code = mark_done(a.out, a.done, force=a.force, strict=True if a.require_artifacts else None)
        if code or not a.show:
            return code
    if a.sync and not a.show:
        sync(a.out)
        return 0
    if a.show:
        return show(a.out, do_sync=not a.no_sync)
    return 0


if __name__ == "__main__":
    sys.exit(main())
