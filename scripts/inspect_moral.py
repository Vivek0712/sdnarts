import json, sys, statistics as st
items = {json.loads(l)["id"]: json.loads(l) for l in open("data/moral.jsonl")}
for path in sys.argv[1:]:
    rows = [json.loads(l) for l in open(path)]
    out = {}
    for r in rows:
        it = items[r["id"]]; a = r["answer"]; t = it["q"]["type"]
        if t == "noul":
            key = f"{it['family']}:{'good=yes' if it['good'] else 'good=no'}"
            out.setdefault(key, []).append(a["noul"])
        elif t == "choice":
            out.setdefault(f"{it['family']}:conf", []).append(a["confidence"])
            out.setdefault(f"{it['family']}:p_evil", []).append(r["p_evil"])
        else:
            out.setdefault(f"rating:{it['good']}", []).append(a["score"])
    print(path)
    for k, v in sorted(out.items()):
        print(f"   {k:22s} mean={st.mean(v):.2f} min={min(v):.2f} max={max(v):.2f} n={len(v)}")
