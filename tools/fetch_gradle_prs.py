import os, sys, argparse, json, time, math, re
from datetime import datetime, timedelta, timezone
from dateutil import parser as dtp
import requests

def gh_get(url, params=None, token=None):
    h = {"Accept": "application/vnd.github+json"}
    if token: h["Authorization"] = f"Bearer {token}"
    r = requests.get(url, params=params or {}, headers=h, timeout=60)
    if r.status_code == 403 and "rate limit" in r.text.lower():
        reset = r.headers.get("X-RateLimit-Reset")
        wait = max(0, int(reset) - int(time.time())) + 1 if reset else 60
        time.sleep(wait)
        r = requests.get(url, params=params or {}, headers=h, timeout=60)
    r.raise_for_status()
    return r.json()

def iso_to_dt(x):
    if not x: return None
    return dtp.parse(x)

def hours_between(a, b):
    if not a or not b: return 0.0
    return max(0.0, (b - a).total_seconds() / 3600.0)

def categorize(title):
    t = title.lower()
    if re.search(r"\bapi|public|signature|contract|breaking|deprecat", t): return "API"
    if re.search(r"\btest|flaky|coverage|assert|ksp|kotlin", t): return "Тесты"
    if re.search(r"\bsecurity|secret|token|auth|permission|vuln", t): return "Безопасность"
    if re.search(r"\bdependenc|bump|gradle|plugin|version|update", t): return "Зависимости"
    if re.search(r"\bperf|performance|speed|optim", t): return "Производительность"
    return "Общее"

def build_sem_text(title, files, add, dele, score):
    return f"{title}. Файлов {files}, добавлено {add}, удалено {dele}. Индекс {round(score,2)}."

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--since_days", type=int, default=90)
    ap.add_argument("--limit", type=int, default=250)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    owner, name = args.repo.split("/", 1)
    since_dt = datetime.now(timezone.utc) - timedelta(days=args.since_days)

    prs = []
    page = 1
    while len(prs) < args.limit:
        lst = gh_get(f"https://api.github.com/repos/{owner}/{name}/pulls", {
            "state": "closed", "sort": "updated", "direction": "desc", "per_page": 100, "page": page
        }, token=token)
        if not lst: break
        for item in lst:
            if len(prs) >= args.limit: break
            num = item["number"]
            full = gh_get(f"https://api.github.com/repos/{owner}/{name}/pulls/{num}", token=token)
            if not full.get("merged_at"): continue
            merged_at = iso_to_dt(full["merged_at"])
            if merged_at and merged_at < since_dt: continue
            created_at = iso_to_dt(full["created_at"])
            author = (full.get("user") or {}).get("login")
            title = full.get("title") or ""
            additions = int(full.get("additions") or 0)
            deletions = int(full.get("deletions") or 0)
            files_changed = int(full.get("changed_files") or 0)

            triage = 0.0
            revs = gh_get(f"https://api.github.com/repos/{owner}/{name}/pulls/{num}/reviews", token=token)
            first_review = iso_to_dt(min([r.get("submitted_at") for r in revs], default=None))
            if first_review is None:
                ic = gh_get(f"https://api.github.com/repos/{owner}/{name}/issues/{num}/comments", token=token)
                first_comment = iso_to_dt(min([c.get("created_at") for c in ic], default=None))
                triage_dt = first_comment
            else:
                triage_dt = first_review
            triage = hours_between(created_at, triage_dt)

            diff_size = additions + deletions
            diff_norm = min(1.0, diff_size / 2000.0)
            spread_norm = min(1.0, files_changed / 20.0)
            hot_norm = min(1.0, files_changed / 15.0)
            semScore = min(1.0, 0.5 * diff_norm + 0.5 * spread_norm)
            score = 0.40 * diff_norm + 0.30 * spread_norm + 0.10 * hot_norm + 0.20 * semScore

            semCategory = categorize(title)
            semText = build_sem_text(title, files_changed, additions, deletions, score)

            prs.append({
                "number": num,
                "title": title,
                "url": full.get("html_url"),
                "author": author,
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
                "problem": None,
                "semCategory": semCategory,
                "semText": semText
            })
        page += 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    data = {"prs": sorted(prs, key=lambda x: x["score"], reverse=True)}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
