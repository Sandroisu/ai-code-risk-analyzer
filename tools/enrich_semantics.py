import json, http.client, argparse, math
from urllib.parse import urlparse

def clamp01(x):
    try:
        v = float(x)
    except:
        return 0.0
    return 0.0 if v < 0 else 1.0 if v > 1 else v

def call_ollama(url, model, prompt):
    u = urlparse(url)
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "format": "json",
        "options": {"temperature": 0.1, "top_p": 0.9},
        "stream": False
    })
    c = http.client.HTTPConnection(u.hostname, u.port, timeout=600)
    c.request("POST", u.path, body=body, headers={"Content-Type": "application/json"})
    r = c.getresponse()
    d = r.read().decode("utf-8")
    c.close()
    o = json.loads(d)
    resp = o.get("response", "")
    try:
        return json.loads(resp)
    except:
        m = re.search(r"\{.*\}", resp, re.S)
        return json.loads(m.group(0)) if m else None

def build_prompt(pr):
    title = pr.get("title","")
    files = int(pr.get("files_changed") or 0)
    add = int(pr.get("lines_added") or 0)
    dele = int(pr.get("lines_deleted") or 0)
    score = float(pr.get("score") or 0.0)
    cats = "API, Тесты, Безопасность, Зависимости, Производительность, Общее"
    return (
        "Сформируй JSON {\"semText\":\"...\",\"semCategory\":\"...\",\"semScore\":...}. "
        "semCategory одна из: " + cats + ". "
        "semText: две короткие фразы на русском — что именно изменено; почему это может быть риск для релиза. "
        "Не повторяй заголовок дословно. Избегай общих фраз. Без маркированных списков. "
        "semScore от 0 до 1: 0.2–0.4 для незначительных правок, 0.5–0.7 для средних, 0.7–0.9 для изменений API/массовых миграций. "
        "Округляй semScore до двух знаков.\n"
        f"Заголовок: {title}\nФайлов: {files}\nДобавлено строк: {add}\nУдалено строк: {dele}\nИндекс: {score:.2f}\n"
    )

def enrich(pr, url, model):
    j = call_ollama(url, model, build_prompt(pr))
    if isinstance(j, dict) and {"semText","semCategory","semScore"} <= set(j.keys()):
        pr["semText"] = str(j["semText"])[:400]
        pr["semCategory"] = str(j["semCategory"])[:40]
        # аккуратно приводим к [0,1]
        try:
            s = float(j["semScore"])
        except:
            s = 0.0
        pr["semScore"] = 0.0 if s < 0 else 1.0 if s > 1 else s
        pr["semOrigin"] = "llm"
    else:
        pr["semOrigin"] = "rule"

    # <<< НОВОЕ: пересчитываем ИТОГОВЫЙ ИНДЕКС >>>
    dn = float(pr.get("diff_norm") or 0.0)
    sn = float(pr.get("spread_norm") or 0.0)
    hn = float(pr.get("hot_norm") or 0.0)
    ss = float(pr.get("semScore") or 0.0)
    pr["score"] = round(0.40*dn + 0.30*sn + 0.10*hn + 0.20*ss, 4)

    return pr

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ollama_url", default="http://127.0.0.1:11434/api/generate")
    ap.add_argument("--model", default="llama3.1:8b-instruct-q4_K_M")
    args = ap.parse_args()
    data = json.load(open(args.inp, "r", encoding="utf-8"))
    prs = data.get("prs") if isinstance(data, dict) else data
    out = [enrich(dict(pr), args.ollama_url, args.model) for pr in prs]
    out.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    if isinstance(data, dict):
        data["prs"] = out
        json.dump(data, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    else:
        json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(args.out)

if __name__ == "__main__":
    main()
