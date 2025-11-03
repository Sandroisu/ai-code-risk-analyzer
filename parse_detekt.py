
import json, sys, os, xml.etree.ElementTree as ET
def load_baseline(path):
    if not os.path.exists(path): return set()
    root=ET.parse(path).getroot()
    res=set()
    for i in root.findall(".//ID"):
        res.add(i.text.strip() if i.text else "")
    return res
def parse_detekt_xml(path):
    if not os.path.exists(path): return []
    tree=ET.parse(path); root=tree.getroot()
    out=[]
    for f in root.findall(".//file"):
        name=f.get("name")
        for err in f.findall("error"):
            rule=err.get("source") or err.get("rule")
            severity=err.get("severity","Minor").title()
            line=int(err.get("line","0"))
            rid=err.get("id") or f"{name}:{rule}:{line}"
            out.append({"tool":"detekt","rule":rule,"severity":severity,"file":name,"line":line,"rid":rid})
    return out
def main():
    detekt=sys.argv[1]
    baseline=sys.argv[2]
    out_path=sys.argv[3]
    bl=load_baseline(baseline)
    findings=parse_detekt_xml(detekt)
    for it in findings:
        it["is_new"]=it["rid"] not in bl
    with open(out_path,"w",encoding="utf-8") as f: json.dump(findings,f,ensure_ascii=False,indent=2)
if __name__=="__main__":
    main()
