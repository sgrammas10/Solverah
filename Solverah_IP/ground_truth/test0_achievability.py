"""Test 0 - achievability gate. A displayed percentage must be reachable at the displayed n."""
def check(n, shown):
    ach = sorted({round(k*100/n, 6) for k in range(n+1)})
    ok = any(round(v) == shown for v in ach)
    below = max([v for v in ach if v <= shown], default=0.0)
    above = min([v for v in ach if v >= shown], default=100.0)
    return ok, below, above, 100/n

CASES = [
    ("P-03", "Trader",                  32, 86),
    ("P-03", "Software Developer",      64, 91),
    ("P-03", "Quantitative Researcher", 11, 81),
    ("P-03", "Junior Trader",           16, 24),
    ("P-04", "Creative Director",       28, 89),
    ("P-04", "(title @ n=24)",          24, 53),
]
print(f"{'Pkt':<6}{'Title':<26}{'n':>4}{'shown':>7}{'step':>8}   nearest achievable   verdict")
print("-"*84)
fails = 0
for pkt, title, n, shown in CASES:
    ok, lo, hi, step = check(n, shown)
    fails += (not ok)
    print(f"{pkt:<6}{title:<26}{n:>4}{shown:>6}%{step:>7.2f}pp   "
          f"{lo:>6.2f}% / {hi:<6.2f}%   {'ok' if ok else 'FAIL'}")
print(f"\n{fails}/{len(CASES)} displayed percentages are unreachable at their stated n.")
print("Systematic failure => the % and the review count use different denominators.")
print("Consequence: differences between these rates have no defined sample size.")
