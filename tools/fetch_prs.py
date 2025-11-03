import os, argparse, json, time, re
from datetime import datetime, timedelta, timezone
from dateutil import parser as dtp
import requests


def gh_get(url, params=None, token=None):
    """
    Обёртка над GET к GitHub REST API
    GitHub иногда возвращает 403 при исчерпании лимита.
    60 секунд на запрос — безопасный верх для редких «тяжёлых» эндпоинтов.
    """
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"

    r = requests.get(url, params=params or {}, headers=h, timeout=60)

    # Если 403 и текст про rate limit — дожидаемся конца окна и повторяем ровно один раз.
    if r.status_code == 403 and "rate limit" in r.text.lower():
        reset = r.headers.get("X-RateLimit-Reset")
        # ждём до конца окна +1 сек для надёжности, если заголовка нет — ждём 60с
        wait = max(0, int(reset) - int(time.time())) + 1 if reset else 60
        time.sleep(wait)
        r = requests.get(url, params=params or {}, headers=h, timeout=60)

    r.raise_for_status()  # пусть падает шумно и рано — проще отлаживать
    return r.json()


def iso_to_dt(x):
    """
    Преобразование ISO-8601 строки datetime.
    Возвращаем None, если поле пустое — код выше будет понимать это как «нет данных».
    """
    if not x:
        return None
    return dtp.parse(x)


def hours_between(a, b):
    """
    Разница во времени в часах между двумя datetime.
    Если любого из аргументов нет — возвращаем 0.0, чтобы не ломать расчёты.
    """
    if not a or not b:
        return 0.0
    return max(0.0, (b - a).total_seconds() / 3600.0)


def categorize(title):
    """
    Грубая категоризация PR по заголовку (fallback до LLM).
    Регулярки покрывают распространённые кейсы:
    - API/контракты, тесты, безопасность, зависимости, производительность.
    Если ничего не поймали — «Общее».
    """
    t = (title or "").lower()
    if re.search(r"\bapi|public|signature|contract|breaking|deprecat", t):
        return "API"
    if re.search(r"\btest|flaky|coverage|assert|ksp|kotlin", t):
        return "Тесты"
    if re.search(r"\bsecurity|secret|token|auth|permission|vuln", t):
        return "Безопасность"
    if re.search(r"\bdependenc|bump|gradle|plugin|version|update", t):
        return "Зависимости"
    if re.search(r"\bperf|performance|speed|optim", t):
        return "Производительность"
    return "Общее"


def sem_text(title, files, add, dele, score):
    """
    Короткое «техническое» пояснение для карточки PR.
    """
    return f"{title}. Файлов {files}, добавлено {add}, удалено {dele}. Индекс {round(score,2)}."


def main():
    """
    Основной сценарий:
    - читаем параметры;
    - инициализируем окно по дате (since_days) и лимит по количеству PR;
    - постранично забираем закрытые PR, фильтруем по merged (нас интересует то, что попало в релиз),
      и по дате merge (чтобы окно наблюдения было контролируемым);
    - считаем производные признаки, индекс и triage;
    - сохраняем dashboard.json, отсортированный по score.
    - since_days=180: полугодовое окно достаточно репрезентативно, но не слишком «тяжёлое»;
    - limit=250: чтобы не упираться в квоты и память.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)                 # формата owner/name
    ap.add_argument("--since_days", type=int, default=180)   # окно по времени для merged_at
    ap.add_argument("--limit", type=int, default=250)        # верхняя граница записей для демо
    ap.add_argument("--out", required=True)                  # путь к dashboard.json
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    owner, name = args.repo.split("/", 1)
    since_dt = datetime.now(timezone.utc) - timedelta(days=args.since_days)

    prs = []
    page = 1
    while len(prs) < args.limit:
        # Берём закрытые PR, сортируем по обновлению (свежее наверху) и ходим по страницам.
        lst = gh_get(
            f"https://api.github.com/repos/{owner}/{name}/pulls",
            {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 100, "page": page},
            token=token,
        )
        if not lst:
            break

        for item in lst:
            if len(prs) >= args.limit:
                break

            num = item["number"]

            # Подтягиваем полный объект PR (там есть additions/deletions/changed_files и даты).
            full = gh_get(f"https://api.github.com/repos/{owner}/{name}/pulls/{num}", token=token)

            # Работаем только с merged PR — это ближе к «реальному риску релиза».
            if not full.get("merged_at"):
                continue

            merged_at = iso_to_dt(full["merged_at"])
            # Отбрасываем то, что вышло за окно наблюдения — чтобы метрики сопоставлялись.
            if merged_at and merged_at < since_dt:
                continue

            created_at = iso_to_dt(full["created_at"])

            # Оценка triage: берём время до первого review; если ревью не было — до первого комментария.
            revs = gh_get(f"https://api.github.com/repos/{owner}/{name}/pulls/{num}/reviews", token=token)
            first_review = iso_to_dt(min([r.get("submitted_at") for r in revs], default=None))

            if first_review is None:
                ic = gh_get(f"https://api.github.com/repos/{owner}/{name}/issues/{num}/comments", token=token)
                first_comment = iso_to_dt(min([c.get("created_at") for c in ic], default=None))
                triage_dt = first_comment
            else:
                triage_dt = first_review

            triage = hours_between(created_at, triage_dt)

            # Базовые объёмы: строки и число файлов.
            additions = int(full.get("additions") or 0)
            deletions = int(full.get("deletions") or 0)
            files_changed = int(full.get("changed_files") or 0)

            # НОРМИРОВАНИЕ ФАКТОРОВ (0..1)
            # Выбираем простые min–max-пороговые шкалы, чтобы держать «типичный» PR в середине шкалы.
            # 2000 строк как «единица» для diff_norm
            diff_norm = min(1.0, (additions + deletions) / 2000.0)

            # 20 файлов как «единица» для spread_norm:
            # изменение в 20+ файлах почти всегда означает массовую правку.
            spread_norm = min(1.0, files_changed / 20.0)

            # «Горячесть» как прокси через число файлов (верхняя полка - 15)
            hot_norm = min(1.0, files_changed / 15.0)

            # Семантическая оценка на этом шаге — из правила, не LLM.
            # Делаем её зависимой от масштаба и распылённости поровну (0.5/0.5), чтобы
            # не перетягивать одеяло в сторону текста до подключения LLM.
            semScore = min(1.0, 0.5 * diff_norm + 0.5 * spread_norm)

            # --- ИНДЕКС ---
            # Фиксированные веса: размер (0.40), распылённость (0.30), горячесть (0.10), семантика (0.20).
            score = 0.40 * diff_norm + 0.30 * spread_norm + 0.10 * hot_norm + 0.20 * semScore

            prs.append({
                "number": num,
                "title": full.get("title") or "",
                "url": full.get("html_url"),
                "author": (full.get("user") or {}).get("login"),
                "created_at": full.get("created_at"),
                "merged_at": full.get("merged_at"),
                "lines_added": additions,
                "lines_deleted": deletions,
                "files_changed": files_changed,
                "diff_norm": round(diff_norm, 4),
                "spread_norm": round(spread_norm, 4),
                "hot_norm": round(hot_norm, 4),
                "semScore": round(semScore, 4),
                "score": round(score, 4),
                "triage": round(triage, 2),
                "problem": None,  # ретро-разметка инцидентов в демо отсутствует => KPI будут «н/д»
                "semCategory": categorize(full.get("title") or ""),
                "semText": sem_text(full.get("title") or "", files_changed, additions, deletions, score),
                "semOrigin": "rule",  # помечаем источник семантики (rule|llm)
            })

        page += 1

    # Готовим выход: сортировка по score облегчает отрисовку очереди на витрине.
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    data = {"prs": sorted(prs, key=lambda x: x["score"], reverse=True)}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()