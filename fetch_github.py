
import os, sys, json, time, math, re, datetime, pathlib, requests
BASE="https://api.github.com"
HEADERS=lambda token: {"Accept":"application/vnd.github+json","Authorization":f"Bearer {token}","X-GitHub-Api-Version":"2022-11-28"}
def get(url, token, params=None):
    r=requests.get(url, headers=HEADERS(token), params=params, timeout=30)
    if r.status_code==403 and "rate limit" in r.text.lower():
        time.sleep(60)
        r=requests.get(url, headers=HEADERS(token), params=params, timeout=30)
    r.raise_for_status()
    return r.json()
def get_paged(url, token, params=None, limit=1000, list_key=None):
    items=[]; page=1
    while True:
        p=dict(params or {}); p.update({"per_page":100,"page":page})
        r=requests.get(url, headers=HEADERS(token), params=p, timeout=30)
        if r.status_code==403 and "rate limit" in r.text.lower():
            time.sleep(60)
            r=requests.get(url, headers=HEADERS(token), params=p, timeout=30)
        r.raise_for_status()
        payload=r.json()
        if isinstance(payload, dict):
            if list_key and list_key in payload:
                chunk=payload[list_key]
            elif "items" in payload:
                chunk=payload["items"]
            else:
                keys=[k for k,v in payload.items() if isinstance(v,list)]
                chunk=payload[keys[0]] if keys else []
        else:
            chunk=payload
        if not chunk: break
        items.extend(chunk)
        if len(chunk)<100 or len(items)>=limit: break
        page+=1
    return items
def parse_date(s):
    return datetime.datetime.strptime(s,"%Y-%m-%dT%H:%M:%SZ")
def read_config(path):
    with open(path,"r",encoding="utf-8") as f: return json.load(f)
def in_range(dt, start, end):
    return dt>=start and dt<=end
def list_prs(owner, repo, token, start, end, max_pr):
    url=f"{BASE}/repos/{owner}/{repo}/pulls"
    prs=[]; page=1
    while True:
        r=requests.get(url, headers=HEADERS(token), params={"state":"all","per_page":100,"page":page,"sort":"updated","direction":"desc"}, timeout=30)
        r.raise_for_status()
        chunk=r.json()
        if not chunk: break
        for pr in chunk:
            dt=parse_date(pr["created_at"])
            if dt < start and page>3:
                break
            prs.append(pr)
        if len(chunk)<100 or len(prs)>=max_pr:
            break
        page+=1
    filtered=[]
    for pr in prs:
        merged_at=pr.get("merged_at")
        created_at=parse_date(pr["created_at"])
        if merged_at:
            m=parse_date(merged_at)
            if in_range(m, start, end): filtered.append(pr)
        else:
            if in_range(created_at, start, end): filtered.append(pr)
    return filtered[:max_pr]
def list_files(owner, repo, num, token):
    url=f"{BASE}/repos/{owner}/{repo}/pulls/{num}/files"
    files=get_paged(url, token, {})
    out=[]
    for f in files:
        path=f["filename"]; add=f["additions"]; dele=f["deletions"]; patch=f.get("patch","")
        hunks=[]
        lines=patch.splitlines()
        add_line=None
        for line in lines:
            if line.startswith("@@"):
                m=re.search(r"\+(\d+)(?:,(\d+))?",line)
                if m:
                    start=int(m.group(1)); count=int(m.group(2) or "1"); add_line=start-1
            elif line.startswith("+") and not line.startswith("++"):
                if add_line is None: continue
                add_line+=1
                hunks.append(add_line)
            elif not line.startswith("-"):
                if add_line is not None: add_line+=1
        out.append({"path":path,"add":add,"del":dele,"added_lines":hunks})
    return out
def list_commits(owner, repo, num, token):
    url=f"{BASE}/repos/{owner}/{repo}/pulls/{num}/commits"
    commits=get_paged(url, token, {})
    return [{"sha":c["sha"],"date":c["commit"]["author"]["date"],"message":c["commit"]["message"]} for c in commits]
def list_actions_runs(owner, repo, token, limit=300):
    url=f"{BASE}/repos/{owner}/{repo}/actions/runs"
    runs=get_paged(url, token, {"event":"pull_request"}, limit=limit, list_key="workflow_runs")
    out=[]
    for r in runs:
        sha=r.get("head_sha")
        status=r.get("status")
        conclusion=r.get("conclusion")
        dur=None
        if r.get("run_started_at") and r.get("updated_at"):
            try:
                s=parse_date(r["run_started_at"]); e=parse_date(r["updated_at"]); dur=int((e-s).total_seconds())
            except:
                dur=None
        pr_nums=[pr.get("number") for pr in (r.get("pull_requests") or []) if pr.get("number") is not None]
        out.append({"id":r["id"],"head_sha":sha,"status":status,"conclusion":conclusion,"duration_sec":dur,"pr_numbers":pr_nums})
    return out
def aggregate_ci_for_pr(runs, pr_commits):
    shas=set([c["sha"] for c in pr_commits])
    rel=[r for r in runs if (r["head_sha"] in shas) or (len(r["pr_numbers"])>0)]
    if not rel: return {"success":0,"failure":0,"duration_avg_sec":0}
    succ=sum(1 for r in rel if r["conclusion"]=="success")
    fail=sum(1 for r in rel if r["conclusion"] in ["failure","timed_out","cancelled"])
    durs=[r["duration_sec"] for r in rel if r["duration_sec"]]
    davg=int(sum(durs)/len(durs)) if durs else 0
    return {"success":succ,"failure":fail,"duration_avg_sec":davg}
def compute_hot(files_history, cutoff_days=90):
    now=datetime.datetime.utcnow()
    cutoff=now-datetime.timedelta(days=cutoff_days)
    cnt={}
    for it in files_history:
        dt=parse_date(it["date"])
        if dt<cutoff: continue
        for p in it["paths"]:
            cnt[p]=cnt.get(p,0)+1
    return cnt
def main():
    cfg=read_config("config.json")
    token=os.getenv("GITHUB_TOKEN","").strip()
    if not token: 
        print("GITHUB_TOKEN not set"); sys.exit(1)
    owner,repo=cfg["repo"].split("/")
    start=datetime.datetime.strptime(cfg["date_from"],"%Y-%m-%d")
    end=datetime.datetime.strptime(cfg["date_to"],"%Y-%m-%d")+datetime.timedelta(days=1)-datetime.timedelta(seconds=1)
    os.makedirs("data/raw",exist_ok=True)
    prs=list_prs(owner,repo,token,start,end,cfg.get("max_pr",200))
    with open("data/raw/pr_list.json","w",encoding="utf-8") as f: json.dump(prs,f,ensure_ascii=False,indent=2)
    runs=list_actions_runs(owner,repo,token,limit=300)
    with open("data/raw/ci_runs.json","w",encoding="utf-8") as f: json.dump(runs,f,ensure_ascii=False,indent=2)
    files_hist=[]
    out=[]
    for pr in prs:
        num=pr["number"]
        files=list_files(owner,repo,num,token)
        commits=list_commits(owner,repo,num,token)
        ci=aggregate_ci_for_pr(runs, commits)
        out.append({"number":num,"title":pr["title"],"merged_at":pr.get("merged_at"),"created_at":pr["created_at"],"files":files,"commits":commits,"ci":ci})
        for c in commits:
            files_hist.append({"date":c["date"],"paths":[f["path"] for f in files]})
    with open("data/raw/pr_enriched.json","w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=2)
    hot=compute_hot(files_hist,90)
    with open("data/raw/hot_files_90d.json","w",encoding="utf-8") as f: json.dump(hot,f,ensure_ascii=False,indent=2)
if __name__=="__main__":
    main()
