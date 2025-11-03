
import json, sys, os
def main():
    inp=sys.argv[1]; outp=sys.argv[2]
    if not os.path.exists(inp):
        with open(outp,"w",encoding="utf-8") as f: json.dump([],f)
        return
    arr=[]
    with open(inp,"r",encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                obj=json.loads(line)
                rule=obj.get("rule") or obj.get("ruleId") or "ktlint"
                severity=(obj.get("severity") or "Minor").title()
                arr.append({"tool":"ktlint","rule":rule,"severity":severity,"file":obj.get("file",""),"line":obj.get("line",0),"rid":f"{obj.get('file','')}:{rule}:{obj.get('line',0)}","is_new":True})
            except:
                continue
    with open(outp,"w",encoding="utf-8") as f: json.dump(arr,f,ensure_ascii=False,indent=2)
if __name__=="__main__":
    main()
