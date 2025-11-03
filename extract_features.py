
import json, os, sys, math, datetime, re
sev_w={"Critical":1.0,"Major":0.7,"Minor":0.4,"Info":0.2}
def load(path):
    with open(path,"r",encoding="utf-8") as f: return json.load(f)
def norm_minmax(vals):
    if not vals: return []
    mn=min(vals); mx=max(vals)
    return [(0 if mx==mn else (v-mn)/(mx-mn)) for v in vals]
def hot_count_for_pr(hot_map, files):
    s=0
    for f in files:
        s+=hot_map.get(f["path"],0)
    return s
def modules_touched(files):
    mods=set()
    for f in files:
        p=f["path"]
        parts=p.split("/")
        if len(parts)>1: mods.add(parts[0])
        else: mods.add("root")
    return len(mods)
def findings_for_pr(findings, pr_files_added):
    out=[]
    file_to_lines={f["path"]:set(f.get("added_lines",[])) for f in pr_files_added}
    for it in findings:
        p=it.get("file")
        if p in file_to_lines:
            if it.get("line",0)==0 or it.get("line",0) in file_to_lines[p]:
                out.append(it)
    return out
def retro_label(pr, issues, later_commits):
    n=pr["number"]
    words=("revert","hotfix","fix","regression")
    for c in later_commits:
        msg=(c.get("message") or "").lower()
        if any(w in msg for w in words): 
            return True,"commit"
    for iss in issues:
        body=(iss.get("body") or "")+" "+(iss.get("title") or "")
        body=body.lower()
        if f"#{n}" in body and any(w in body for w in words):
            return True,"issue"
    return False,"none"
def main():
    cfg=load("config.json")
    pr_en=load("data/raw/pr_enriched.json")
    hot=load("data/raw/hot_files_90d.json") if os.path.exists("data/raw/hot_files_90d.json") else {}
    det=findings_det=load("reports/detekt_findings.json") if os.path.exists("reports/detekt_findings.json") else []
    ktl=findings_kt=load("reports/ktlint_findings.json") if os.path.exists("reports/ktlint_findings.json") else []
    issues=load("data/raw/issues.json") if os.path.exists("data/raw/issues.json") else []
    out=[]
    ci_fails=[]; ci_dur=[]; sizes=[]; spreads=[]; sa_raw=[]; hots=[]
    for pr in pr_en:
        files=pr["files"]
        commits=pr["commits"]
        later=[c for c in commits if True]
        f_det=findings_for_pr(det, files)
        f_kt=findings_for_pr(ktl, files)
        f_all=f_det+f_kt
        sa=sum(sev_w.get(x.get("severity","Minor"),0.4) for x in f_all if x.get("is_new",True))
        size=sum(f["add"]+f["del"] for f in files)
        spread=modules_touched(files)
        hot_score=hot_count_for_pr(hot, files)
        ci_fail_ratio=pr["ci"]["failure"]/max(1,(pr["ci"]["success"]+pr["ci"]["failure"]))
        ci_fails.append(ci_fail_ratio); ci_dur.append(pr["ci"]["duration_avg_sec"]); sizes.append(size); spreads.append(spread); sa_raw.append(sa); hots.append(hot_score)
        out.append({"number":pr["number"],"title":pr["title"],"files":files,"ci":pr["ci"],"size":size,"spread":spread,"sa_raw":sa,"hot":hot_score,"commits":commits,"merged_at":pr.get("merged_at"),"created_at":pr["created_at"]})
    ci_fail_n=norm_minmax(ci_fails); ci_dur_n=norm_minmax(ci_dur); size_n=norm_minmax(sizes); spread_n=norm_minmax(spreads); sa_n=norm_minmax(sa_raw); hot_n=norm_minmax(hots)
    weights={"ci":0.25,"sa":0.25,"size":0.15,"spread":0.1,"hot":0.15,"sem":0.1}
    enriched=[]
    for i,pr in enumerate(out):
        ci_n=(ci_fail_n[i]+ci_dur_n[i])/2
        sem_score=0.0
        sem_cat="Общее"
        if pr["sa_raw"]>0.9*max(sa_raw): sem_cat,sem_score="Безопасность",0.8
        elif pr["spread"]>0.9*max(spreads): sem_cat,sem_score="API",0.6
        score=weights["ci"]*ci_n+weights["sa"]*sa_n[i]+weights["size"]*size_n[i]+weights["spread"]*spread_n[i]+weights["hot"]*hot_n[i]+weights["sem"]*sem_score
        enriched.append({"number":pr["number"],"title":pr["title"],"ciN":ci_n,"saN":sa_n[i],"sizeN":size_n[i],"spreadN":spread_n[i],"hotN":hot_n[i],"semN":sem_score,"score":score,"semCat":sem_cat,"sa_count":pr["sa_raw"]})
    scores=[e["score"] for e in enriched]
    scores_sorted=sorted(scores)
    q70=scores_sorted[int(len(scores)*0.7)] if scores else 0
    for e in enriched:
        e["zone"]="high" if e["score"]>=q70 else "mid"
    with open(cfg["output_json"],"w",encoding="utf-8") as f: json.dump({"prs":enriched},f,ensure_ascii=False,indent=2)
if __name__=="__main__":
    main()
