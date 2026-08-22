"""Generates the inline SVG for the ten-year projection charts."""
import json

D = json.load(open("projection.json"))
YEARS = [r["y"] for r in D[0]["rows"]]
SHORT = ["Cash out now", "Cash out 2027", "Draw as needed",
         "Bracket-fill + bank", "Bracket-fill + prepay"]

def chart(key, ymin, ymax, ticks, height, fmt, plot_r=536,
          end_labels=True, payoff=False, dashed=()):
    L, R, T, B = 58, plot_r, 22, height - 40
    W = 720
    def X(i): return L + (R - L) * i / (len(YEARS) - 1)
    def Y(v): return B - (B - T) * (v - ymin) / (ymax - ymin)

    o = [f'<svg viewBox="0 0 {W} {height}" role="img" class="chart" '
         f'preserveAspectRatio="xMidYMid meet">']
    for t in ticks:                                        # recessive grid
        o.append(f'<line class="grid" x1="{L}" x2="{R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/>')
        o.append(f'<text class="ytick" x="{L-10}" y="{Y(t)+4:.1f}">{fmt(t)}</text>')
    for i, y in enumerate(YEARS):
        if i % 2 == 0 or i == len(YEARS) - 1:
            o.append(f'<text class="xtick" x="{X(i):.1f}" y="{B+20}">{y}</text>')

    ends = []
    for si, s in enumerate(D):
        pts = " ".join(f"{X(i):.1f},{Y(r[key]):.1f}" for i, r in enumerate(s["rows"]))
        dash = ' stroke-dasharray="7 5"' if si in dashed else ''
        o.append(f'<polyline class="ln s{si+1}" points="{pts}"{dash}/>')
        last = s["rows"][-1][key]
        if end_labels:
            o.append(f'<circle class="dot s{si+1}" cx="{X(len(YEARS)-1):.1f}" '
                     f'cy="{Y(last):.1f}" r="4.5"/>')
            ends.append([Y(last), si, last])
        if payoff:
            # mark the year the balance first reaches zero -- the readout that
            # matters here is WHEN it is gone, not that every line ends at $0
            z = next((j for j, r in enumerate(s["rows"]) if r[key] <= 0.5), None)
            if z is not None:
                o.append(f'<circle class="dot s{si+1}" cx="{X(z):.1f}" '
                         f'cy="{Y(0):.1f}" r="4.5"/>')
                o.append(f'<text class="paid s{si+1}" x="{X(z):.1f}" '
                         f'y="{Y(0)-13:.1f}">{YEARS[z]}</text>')

    ends.sort()                                            # de-collide labels
    for k in range(1, len(ends)):
        if ends[k][0] - ends[k-1][0] < 15:
            ends[k][0] = ends[k-1][0] + 15
    for yy, si, val in ends:
        o.append(f'<text class="endlbl s{si+1}" x="{R+9}" y="{yy+4:.1f}">{fmt(val)}</text>')

    for i in range(len(YEARS)):                            # hover targets
        o.append(f'<rect class="hit" data-i="{i}" x="{X(i)-((R-L)/(len(YEARS)-1))/2:.1f}" '
                 f'y="{T}" width="{(R-L)/(len(YEARS)-1):.1f}" height="{B-T}"/>')
    o.append(f'<line class="cross" x1="0" x2="0" y1="{T}" y2="{B}" style="opacity:0"/>')
    o.append('</svg>')
    return "\n".join(o)

k = lambda v: f"${v/1000:,.0f}K"
print(chart("net", 400_000, 820_000, [400_000, 500_000, 600_000, 700_000, 800_000], 330, k))
print("<!--SPLIT-->")
# scenarios 3 and 4 have identical loan paths (neither prepays), so 4 is dashed
# on top of 3 -- otherwise one series is simply invisible.
print(chart("loan", 0, 175_000, [0, 50_000, 100_000, 150_000], 250, k,
            plot_r=610, end_labels=False, payoff=True, dashed=(3,)))
