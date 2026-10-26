"""python -m autoshorts {run|daemon|trends|make "키워드"}"""
import argparse, json
from . import pipeline, trends


def main():
    ap = argparse.ArgumentParser(prog="autoshorts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("trends", help="print ranked trending candidates")
    r = sub.add_parser("run", help="one cycle: pick rising keywords and make shorts")
    r.add_argument("-n", type=int, default=None, help="number of shorts (default AUTOSHORTS_TOPICS=2)")
    m = sub.add_parser("make", help="make one short for a given keyword")
    m.add_argument("keyword")
    d = sub.add_parser("daemon", help="run forever, one cycle every N hours")
    d.add_argument("--every", type=float, default=4.0)
    a = ap.parse_args()

    if a.cmd == "trends":
        for c in trends.candidates():
            print(f"{c['score']:5.2f}  {c['traffic']:>6}+  {c['age_h']:4.1f}h  curve={c['curve']}  {c['keyword']}")
    elif a.cmd == "run":
        res = pipeline.run_once(a.n)
        print(json.dumps([{k: x.get(k) for k in ("keyword", "status", "note", "out")} for x in res["results"]], ensure_ascii=False, indent=1))
    elif a.cmd == "make":
        cands = {c["keyword"]: c for c in trends.candidates()}
        item = cands.get(a.keyword) or {"keyword": a.keyword, "traffic": 0, "score": 0, "news": []}
        print(json.dumps(pipeline.make_short(item), ensure_ascii=False, indent=1))
    elif a.cmd == "daemon":
        pipeline.daemon(a.every)


if __name__ == "__main__":
    main()
