"""
Ten-year projection, 2026-2035, across five ways of funding the mortgage.

New in this version, at the client's suggestion: a strategy that takes the
year's withdrawal at the START of the year, pays the tax, and puts EVERY
remaining dollar straight against the mortgage principal before the monthly
payments run. That kills interest earlier and shortens the loan.

Convention shared by all scenarios so they compare fairly:
  - 2026's mortgage payments come from salary. That is affordable only because
    his $80k also landed in 2026; from 2027 she is on her $86k alone.
  - If a scenario has no mortgage in 2026, it is credited with that freed salary.
  - Once the mortgage is gone, no further withdrawals are taken.
  - Leftover cash goes to a taxable side pot earning the market return less a
    50bp drag; sales are taxed at 15% on the gain.
"""

import taxes
from inputs import DEFAULT
from model import filing_status

INP = DEFAULT
YEARS = list(range(2026, 2036))


class Loan:
    def __init__(self, balance, annual_rate, months):
        self.balance, self.r, self.n = float(balance), annual_rate/12, months
        self.payment = self.balance*self.r/(1-(1+self.r)**-self.n)

    def prepay(self, amount):
        """Principal reduction. Payment stays the same, so the TERM shortens."""
        applied = min(amount, self.balance)
        self.balance -= applied
        return applied

    def run_year(self):
        paid = 0.0
        for _ in range(12):
            if self.balance <= 0.005:
                break
            i = self.balance * self.r
            p = min(self.payment, self.balance + i)
            self.balance = max(0.0, self.balance + i - p)
            paid += p
        return paid


def context(year):
    i = year - 2026
    st, kids = filing_status(year, INP)
    return (st, kids, INP.her_salary * (1 + INP.salary_growth) ** i,
            INP.decedent_wages_2026 if year == 2026 else 0.0)


def tax_on(w, year):
    st, kids, wages, his = context(year)
    a = dict(wages=wages, other_ordinary_income=his, qualified_dividends=0, ltcg=0,
             status=st, age=52 + (year-2026), n_children=kids, year=year,
             inflation=INP.inflation)
    return (taxes.total_tax(retirement_distribution=w, **a)["total"]
            - taxes.total_tax(retirement_distribution=0, **a)["total"])


def gross_up(net, year):
    lo, hi = 0.0, net*4 + 50_000
    for _ in range(150):
        m = (lo+hi)/2
        if m - tax_on(m, year) < net: lo = m
        else: hi = m
    return hi


def room_at_12(year):
    st, kids, wages, his = context(year)
    std = taxes._index(taxes.FED_STD_DEDUCTION_2026[st], year, INP.inflation)
    return max(0.0, taxes.bracket_ceiling(.12, st, year, INP.inflation)
               - max(0.0, wages + his - std))


def project(name, *, payoff_year=None, prepay=False, bracket_fill=False):
    loan = Loan(INP.mortgage_balance, INP.mortgage_rate, INP.mortgage_months_remaining)
    k401, side, basis, tax_paid = INP.inherited_401k_traditional, 0.0, 0.0, 0.0
    rows, payoff_done = [], None

    for year in YEARS:
        salary_covers = (year == 2026)

        # ---- decide the withdrawal ----------------------------------------
        # Spend banked cash before pulling more from the 401(k) -- otherwise a
        # bracket-fill strategy pays 27% on new withdrawals while sitting on a
        # side pot, which defeats the entire point of filling the bracket.
        side_cash = side * (1 - (1 - basis/side)*.15) if side > 0 else 0.0

        if loan.balance <= 0.005:
            w = 0.0
        elif payoff_year == year:
            w = gross_up(max(0.0, loan.balance - side_cash), year)
        elif salary_covers:
            w = 0.0
        else:
            need = loan.balance if loan.balance < loan.payment*12 else loan.payment*12
            w = gross_up(max(0.0, need - side_cash), year)
            if bracket_fill and room_at_12(year) > 0:
                # deliberately take the cheap dollars while the 12% bracket is
                # open, but never more than the loan will ever need
                w = min(max(w, room_at_12(year)), gross_up(loan.balance, year))
        w = min(w, k401)

        t = tax_on(w, year)
        tax_paid += t
        k401 -= w
        cash = w - t

        # ---- service the loan ----------------------------------------------
        if payoff_year == year:
            cash -= loan.prepay(loan.balance)
        elif loan.balance > 0.005:
            if prepay:
                # everything beyond this year's scheduled payments goes to
                # principal FIRST, before any interest accrues on it
                lump = max(0.0, cash - loan.payment*12)
                cash -= loan.prepay(lump)
            paid = loan.run_year()
            cash -= 0.0 if salary_covers else paid
        if salary_covers and loan.balance <= 0.005 and payoff_year == 2026:
            cash += loan.payment*12          # freed salary, credited for fairness

        # ---- top up from the side pot if short ------------------------------
        if cash < -0.005 and side > 0:
            take = min(-cash, side)
            gain = take * (1 - basis/side)
            basis -= take - gain; side -= take
            tax_paid += gain*.15
            cash += take - gain*.15

        side += max(0.0, cash); basis += max(0.0, cash)
        k401 *= (1 + INP.expected_return)
        side *= (1 + INP.expected_return - .005)
        if loan.balance <= 0.005 and payoff_done is None:
            payoff_done = year

        rows.append(dict(year=year, w=w, tax=t, loan=loan.balance, k401=k401,
                         side=side, total=k401 + side - loan.balance))

    return dict(name=name, rows=rows, tax=tax_paid, payoff=payoff_done,
                final=rows[-1]["total"], k401=rows[-1]["k401"],
                side=rows[-1]["side"])


SCEN = [
    project("1. Cash out now (2026)", payoff_year=2026),
    project("2. Cash out in 2027", payoff_year=2027),
    project("3. Draw only what's needed, from 2027"),
    project("4. Fill the 12% bracket 2027-28, bank the surplus", bracket_fill=True),
    project("5. Fill the 12% bracket 2027-28, prepay the mortgage",
            bracket_fill=True, prepay=True),
]

print(f"Mortgage ${INP.mortgage_balance:,.0f} at {INP.mortgage_rate:.2%} "
      f"(P&I ${Loan(INP.mortgage_balance, INP.mortgage_rate, 120).payment:,.2f}/mo) "
      f"| 401(k) ${INP.inherited_401k_traditional:,.0f} | return "
      f"{INP.expected_return:.0%} | salary ${INP.her_salary:,.0f} +3%/yr\n")

best = max(s["final"] for s in SCEN)
print(f"{'scenario':52} {'total tax':>10} {'paid off':>9} {'401(k) 2035':>12} "
      f"{'side pot':>10} {'NET 2035':>11} {'vs best':>10}")
print("-"*120)
for s in SCEN:
    d = s["final"] - best
    print(f"{s['name']:52} {s['tax']:>10,.0f} {str(s['payoff']):>9} "
          f"{s['k401']:>12,.0f} {s['side']:>10,.0f} {s['final']:>11,.0f} "
          f"{'  <-- best' if d==0 else f'{d:>+10,.0f}'}")

print("\n\nYEAR BY YEAR -- net position (401k + side pot - mortgage)")
print(f"{'year':>5} " + " ".join(f"{s['name'].split('.')[0]:>12}" for s in SCEN))
print("-"*70)
for i, y in enumerate(YEARS):
    print(f"{y:>5} " + " ".join(f"{s['rows'][i]['total']:>12,.0f}" for s in SCEN))

print("\n\nMORTGAGE BALANCE")
print(f"{'year':>5} " + " ".join(f"{s['name'].split('.')[0]:>12}" for s in SCEN))
print("-"*70)
for i, y in enumerate(YEARS):
    print(f"{y:>5} " + " ".join(f"{s['rows'][i]['loan']:>12,.0f}" for s in SCEN))

print("\n\nWITHDRAWALS")
print(f"{'year':>5} " + " ".join(f"{s['name'].split('.')[0]:>12}" for s in SCEN))
print("-"*70)
for i, y in enumerate(YEARS):
    print(f"{y:>5} " + " ".join(f"{s['rows'][i]['w']:>12,.0f}" for s in SCEN))
