"""Pure-Python Mann-Kendall trend test and Sen's slope estimator.

No third-party dependencies, so results are reproducible on a clean machine.
Reference for the estimator: Sen (1968); test statistic: Mann (1945), Kendall (1975).
"""
import csv
import math


def mann_kendall(xs):
    n = len(xs)
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            d = xs[j] - xs[i]
            s += (d > 0) - (d < 0)

    # Tie correction for the variance of S.
    counts = {}
    for v in xs:
        counts[v] = counts.get(v, 0) + 1
    tie_term = sum(c * (c - 1) * (2 * c + 5) for c in counts.values() if c > 1)

    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var_s <= 0:
        return {"n": n, "S": s, "Z": 0.0, "p": 1.0}

    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0

    # Two-sided p-value from the standard normal distribution.
    p = math.erfc(abs(z) / math.sqrt(2))
    return {"n": n, "S": s, "Z": z, "p": p}


def sens_slope(xs, ts=None):
    if ts is None:
        ts = list(range(len(xs)))
    slopes = []
    for i in range(len(xs) - 1):
        for j in range(i + 1, len(xs)):
            dt = ts[j] - ts[i]
            if dt:
                slopes.append((xs[j] - xs[i]) / dt)
    if not slopes:
        return None
    slopes.sort()
    m = len(slopes)
    return slopes[m // 2] if m % 2 else 0.5 * (slopes[m // 2 - 1] + slopes[m // 2])


def read_power_monthly(path):
    """Parse NASA POWER monthly CSV into {parameter: {year: {month: value}}}."""
    out = {}
    with open(path) as fh:
        for line in fh:
            parts = line.strip().split(",")
            if len(parts) < 15 or not parts[1].isdigit():
                continue
            param = parts[0]
            year = int(parts[1])
            months = {}
            for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                   "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]):
                raw = parts[2 + i]
                try:
                    v = float(raw)
                except ValueError:
                    continue
                if v != -999:
                    months[m] = v
            out.setdefault(param, {})[year] = months
    return out


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "power-2003-2024-monthly.csv"
    data = read_power_monthly(path)

    for param, years in data.items():
        annual = [(y, sum(m.values()) / len(m)) for y, m in sorted(years.items()) if len(m) == 12]
        if len(annual) < 10:
            print(f"{param}: insufficient complete years ({len(annual)})")
            continue
        xs = [v for _, v in annual]
        ts = [y for y, _ in annual]
        mk = mann_kendall(xs)
        slope = sens_slope(xs, ts)
        print(f"\n{param} annual mean, {ts[0]}-{ts[-1]}, n={mk['n']}")
        print(f"  first {xs[0]:.3f}  last {xs[-1]:.3f}")
        print(f"  Sen's slope {slope:+.5f} per year")
        print(f"  Mann-Kendall S={mk['S']} Z={mk['Z']:+.3f} p={mk['p']:.4f} "
              f"-> {'significant at 0.05' if mk['p'] < 0.05 else 'not significant at 0.05'}")
