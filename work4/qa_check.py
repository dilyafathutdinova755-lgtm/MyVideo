import json

WORK = "/home/user/MyVideo/work4"
plan = json.load(open(f"{WORK}/subtitle_plan.json"))

print("=== QA: cards ===")
ok = True
for c in plan["cards"]:
    dur = c["end"] - c["start"]
    flag = "OK" if dur <= 4.0 else "FAIL >4s"
    if dur > 4.0: ok = False
    print(f'{c["start"]:6.2f}-{c["end"]:6.2f} dur={dur:.2f} {flag}  ' + " / ".join(p[0] for p in c["parts"]))

print("\n=== QA: card overlaps ===")
cards = sorted(plan["cards"], key=lambda c: c["start"])
for a, b in zip(cards, cards[1:]):
    if b["start"] < a["end"]:
        print(f'OVERLAP: {a["start"]}-{a["end"]} vs {b["start"]}-{b["end"]}')
        ok = False
print("no overlaps" if ok else "")

print("\n=== QA: caption continuity ===")
caps = plan["captions"]
gap_found = False
for a, b in zip(caps, caps[1:]):
    if abs(a["end"] - b["start"]) > 0.001:
        print(f'GAP: {a["end"]} -> {b["start"]}')
        gap_found = True
if caps[0]["start"] != 0.0:
    print("caption does not start at 0:", caps[0]["start"])
    gap_found = True
if abs(caps[-1]["end"] - plan["total"]) > 0.05:
    print("caption does not reach end:", caps[-1]["end"], "vs", plan["total"])
    gap_found = True
print("continuous, no gaps" if not gap_found else "FAIL: gaps found")

print("\n=== QA: icon window ===")
ic = plan["icon"]
print(f'icon {ic["start"]:.2f} -> {ic["end"]:.2f} (total {plan["total"]:.2f}), holds to end: {abs(ic["end"]-plan["total"])<0.01}')
