#!/usr/bin/env python3
"""Создаёт папку прогона <OUT> по run-config: подпапки, build/STATUS.md с чек-листом фаз, .gitignore для node-модулей.

  init_run.py <OUT>                  по <OUT>/build/run-config.json (его пишет intake.py)
  init_run.py <OUT> --status "фаза 3 готова: …"   дописать строку в STATUS.md (чекпоинт)
  init_run.py <OUT> --done 3         отметить фазу 3 выполненной в чек-листе
  init_run.py <OUT> --show           первый открытый пункт и последние чекпоинты (продолжение после обрыва)
  init_run.py <OUT> --relocate <NEW> [--repo R] [--inside-repo|--no-inside-repo] [--branch B] [--dry-run]
                                     перенос папки прогона: пути в файлах заменяются (relocate_run.py), run-config обновляется;
                                     дальше `build_all.py <NEW>` и `check_gitignore.py <NEW>`
Чек-лист задач прогона — STRATEGY_TASKS.md (не TASKS.md: в корне репозитория пользователя свой TASKS.md).

Только стандартная библиотека.
"""
import argparse
import json
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
        gi.write_text("!build/\n!data/\n!deliverables/\nbuild/node/\n*.tmp\n", encoding="utf-8")   # «!» переопределяют корневые правила (build/)
    sp = status_path(out)
    if not sp.exists():
        s = cfg.get("strategy", {})
        head = ["# STATUS — стратегия %s" % cfg.get("product", {}).get("name", out.name), "",
                "Создано: %s. Глубина: %s, предложений ≥ %s, горизонт %s мес + %s г." % (
                    datetime.now().strftime("%Y-%m-%d %H:%M"), s.get("depth", "?"), s.get("proposals_min", "?"),
                    s.get("horizon_months", "?"), s.get("vision_years", "?")), "", "## Фазы"]
        head += ["- [ ] %s. %s" % (n, t) for n, t in PHASES]
        head += ["", "## Чекпоинты", ""]
        sp.write_text("\n".join(head), encoding="utf-8")
    tp = out / "STRATEGY_TASKS.md"
    if not tp.exists():
        tp.write_text("# STRATEGY_TASKS — чек-лист прогона стратегии\n\nФазы — в build/STATUS.md; здесь — найденные по дороге задачи.\n\n"
                      "- [ ] фаза 0–9 по build/STATUS.md\n\n## Где остановился\n\n—\n", encoding="utf-8")
    if cfg and not (cfg.get("output") or {}).get("inside_repo", True):
        print("ВНИМАНИЕ: результат лежит ВНЕ репозитория (в git проекта не попадёт). Если нужна папка внутри репозитория: "
              "init_run.py %s --relocate <repo>/strategy/<дата> --repo <repo> --inside-repo" % out, file=sys.stderr)
    print("OUT=%s" % out)
    return 0


def add_status(out, text):
    sp = status_path(out)
    with sp.open("a", encoding="utf-8") as f:
        f.write("- %s — %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M"), text.strip()))
    return 0


def mark_done(out, n):
    sp = status_path(out)
    s = sp.read_text(encoding="utf-8")
    n = str(n)
    s2 = re.sub(r"^- \[ \] %s\. " % re.escape(n), "- [x] %s. " % n, s, count=1, flags=re.M)
    sp.write_text(s2, encoding="utf-8")
    return 0 if s2 != s else 1


def show(out):
    s = status_path(out).read_text(encoding="utf-8")
    m = re.search(r"^- \[ \] ([\d.]+\. .*)$", s, re.M)
    print("Следующая фаза: %s" % (m.group(1) if m else "все фазы отмечены"))
    cps = re.findall(r"^- \d{4}-\d\d-\d\d .*$", s, re.M)
    for c in cps[-5:]:
        print(c)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--status")
    ap.add_argument("--done", help="номер фазы (0–9 или 5.5)")
    ap.add_argument("--show", action="store_true")
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
    if not status_path(a.out).exists() or not (a.status or a.done is not None or a.show):
        init(a.out)
    if a.status:
        add_status(a.out, a.status)
    if a.done is not None:
        return mark_done(a.out, a.done)
    if a.show:
        return show(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
