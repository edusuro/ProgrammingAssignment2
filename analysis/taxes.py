"""
Federal + Georgia tax engine for the inherited-401(k) withdrawal analysis.

Statutory figures are tax-year 2026 (IRS Rev. Proc. 2025-32 / OBBBA amendments,
Georgia HB 463 flat rate). Later years are approximated by indexing the federal
figures at `inflation`; Georgia figures are NOT indexed because Georgia does not
index its standard deduction or exemptions.

Every hard-coded number is a statutory fact, not an assumption. Assumptions live
in inputs.py.
"""

from math import inf

# ---------------------------------------------------------------- federal ----
# (upper bound of bracket in taxable income, marginal rate)
FED_BRACKETS_2026 = {
    "single": [(12_400, .10), (50_400, .12), (105_700, .22), (201_775, .24),
               (256_225, .32), (640_600, .35), (inf, .37)],
    "mfj":    [(24_800, .10), (100_800, .12), (211_400, .22), (403_550, .24),
               (512_450, .32), (768_700, .35), (inf, .37)],
    "hoh":    [(17_700, .10), (67_450, .12), (105_700, .22), (201_750, .24),
               (256_200, .32), (640_600, .35), (inf, .37)],
}
FED_BRACKETS_2026["qss"] = FED_BRACKETS_2026["mfj"]          # QSS uses MFJ table

FED_STD_DEDUCTION_2026 = {"single": 16_100, "mfj": 32_200, "hoh": 24_150}
FED_STD_DEDUCTION_2026["qss"] = FED_STD_DEDUCTION_2026["mfj"]

CTC_PER_CHILD = 2_200
CTC_PHASEOUT_START = {"single": 200_000, "hoh": 200_000, "mfj": 400_000, "qss": 400_000}

SS_WAGE_BASE_2026 = 184_500
OASDI_RATE, MEDICARE_RATE, ADDL_MEDICARE_RATE = .062, .0145, .009
ADDL_MEDICARE_THRESHOLD = {"single": 200_000, "hoh": 200_000,
                           "mfj": 250_000, "qss": 200_000}

EARLY_WITHDRAWAL_PENALTY = .10
PENALTY_FREE_AGE = 59.5

# ---------------------------------------------------------------- georgia ----
GA_FLAT_RATE = .0499                      # HB 463, tax year 2026 onward
GA_STD_DEDUCTION = {"single": 12_000, "hoh": 12_000, "mfj": 24_000, "qss": 24_000}
GA_DEPENDENT_EXEMPTION = 4_000
GA_RETIREMENT_EXCLUSION = {62: 35_000, 65: 65_000}   # by age attained
GA_EXCLUSION_EARNED_INCOME_CAP = 4_000


def _index(amount, year, inflation, base_year=2026):
    return amount * (1 + inflation) ** (year - base_year)


def federal_income_tax(taxable_income, status, year=2026, inflation=0.0):
    """Ordinary federal income tax on `taxable_income` (already net of deductions)."""
    tax, lower = 0.0, 0.0
    for upper, rate in FED_BRACKETS_2026[status]:
        cap = upper if upper is inf else _index(upper, year, inflation)
        if taxable_income <= lower:
            break
        tax += (min(taxable_income, cap) - lower) * rate
        lower = cap
    return max(tax, 0.0)


def federal_marginal_rate(taxable_income, status, year=2026, inflation=0.0):
    lower = 0.0
    for upper, rate in FED_BRACKETS_2026[status]:
        cap = upper if upper is inf else _index(upper, year, inflation)
        if taxable_income <= cap:
            return rate
        lower = cap
    return FED_BRACKETS_2026[status][-1][1]


def bracket_ceiling(rate, status, year=2026, inflation=0.0):
    """Taxable income at the top of the given marginal rate band."""
    for upper, r in FED_BRACKETS_2026[status]:
        if r == rate:
            return upper if upper is inf else _index(upper, year, inflation)
    raise ValueError(f"no {rate} bracket for {status}")


def child_tax_credit(agi, n_children, status):
    if n_children <= 0:
        return 0.0
    credit = CTC_PER_CHILD * n_children
    over = max(0.0, agi - CTC_PHASEOUT_START[status])
    return max(0.0, credit - 50 * (over // 1_000))


def payroll_tax(wages, status, year=2026, inflation=0.0):
    """FICA. Retirement-plan distributions are NOT subject to this."""
    base = _index(SS_WAGE_BASE_2026, year, inflation)
    tax = min(wages, base) * OASDI_RATE + wages * MEDICARE_RATE
    tax += max(0.0, wages - ADDL_MEDICARE_THRESHOLD[status]) * ADDL_MEDICARE_RATE
    return tax


def georgia_retirement_exclusion(age, retirement_income, earned_income):
    if age < 62:
        return 0.0
    cap = GA_RETIREMENT_EXCLUSION[65] if age >= 65 else GA_RETIREMENT_EXCLUSION[62]
    eligible = retirement_income + min(earned_income, GA_EXCLUSION_EARNED_INCOME_CAP)
    return min(cap, eligible)


def georgia_tax(federal_agi, status, age, retirement_income, earned_income,
                n_dependents):
    excl = georgia_retirement_exclusion(age, retirement_income, earned_income)
    ga_taxable = (federal_agi
                  - excl
                  - GA_STD_DEDUCTION[status]
                  - GA_DEPENDENT_EXEMPTION * n_dependents)
    return max(0.0, ga_taxable) * GA_FLAT_RATE


def total_tax(*, wages, retirement_distribution, other_ordinary_income,
              qualified_dividends, ltcg, status, age, n_children,
              year=2026, inflation=0.0, penalty_applies=False,
              itemized_deductions=0.0):
    """
    Returns a dict of the full tax picture for one year.

    `penalty_applies` is True only if the money has been rolled into HER OWN IRA
    and she is under 59.5. Distributions from the decedent's plan or from an
    inherited (beneficiary) IRA are penalty-exempt under IRC 72(t)(2)(A)(ii).
    """
    ordinary = wages + retirement_distribution + other_ordinary_income
    agi = ordinary + qualified_dividends + ltcg

    deduction = max(_index(FED_STD_DEDUCTION_2026[status], year, inflation),
                    itemized_deductions)
    taxable = max(0.0, agi - deduction)

    # preferential-rate income sits on top of ordinary income
    pref = min(taxable, qualified_dividends + ltcg)
    ordinary_taxable = taxable - pref

    fed_ordinary = federal_income_tax(ordinary_taxable, status, year, inflation)
    # 0% / 15% LTCG: 15% is a fair approximation at these income levels
    fed_pref = pref * .15

    credits = child_tax_credit(agi, n_children, status)
    fed = max(0.0, fed_ordinary + fed_pref - credits)

    penalty = (retirement_distribution * EARLY_WITHDRAWAL_PENALTY
               if penalty_applies and age < PENALTY_FREE_AGE else 0.0)

    fica = payroll_tax(wages, status, year, inflation)
    ga = georgia_tax(agi, status, age, retirement_distribution, wages,
                     n_children)

    return {
        "agi": agi,
        "taxable_income": taxable,
        "federal": fed,
        "federal_before_credits": fed_ordinary + fed_pref,
        "credits": credits,
        "penalty": penalty,
        "fica": fica,
        "georgia": ga,
        "total": fed + penalty + fica + ga,
        "marginal_fed": federal_marginal_rate(ordinary_taxable, status, year,
                                              inflation),
    }
