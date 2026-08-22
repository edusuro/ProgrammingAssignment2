# Inherited 401(k) withdrawal analysis

Analysis of financial options for a 52-year-old surviving spouse in Marietta,
Georgia with one dependent child and an inherited 401(k), weighing whether to
liquidate retirement assets to retire a 2–3% mortgage.

## Read this first

**[PRESSURE_TEST.md](PRESSURE_TEST.md)** — findings, corrections to the original
framing, model results, and a recommended sequence of actions.

**[INTAKE.md](INTAKE.md)** — the data checklist. Several items are time-sensitive
or irreversible.

## Files

| File | Contents |
|---|---|
| `taxes.py` | Federal + Georgia tax engine. **Statute only, no assumptions.** 2026 brackets and deductions (Rev. Proc. 2025-32 / OBBBA), Georgia 4.99% flat rate (HB 463), FICA, CTC, §72(t) penalty logic, Georgia retirement-income exclusion. |
| `inputs.py` | **Every assumption lives here.** All values are placeholders pending real data. |
| `model.py` | Year-by-year projection: mortgage amortization and recast, filing-status transitions, Social Security survivor benefits with the earnings test, and the five strategies. |
| `sensitivity.py` | Parameter sweeps and break-even solvers. |
| `results.txt` | Saved output of the current run. |

## Run it

```
cd analysis && python3 sensitivity.py      # full comparison + sensitivities
```

Standard library only, Python 3.11+.

## Headline result

Paying off the mortgage was **the worst of the five strategies in every one of
the 30+ parameter combinations tested.** It only becomes correct if the portfolio
returns less than 1.73%, or the mortgage rate is above 7.18%.

The best strategy — spending stepped-up taxable assets before 401(k) dollars —
was not in the original option set, and the largest single financial item
(Social Security survivor benefits) was missing from the analysis entirely.

## Caveats

The dollar figures are driven by placeholders and are meaningless until
`inputs.py` is filled in. Rankings and break-evens are the real output. This is
analysis, not financial or tax advice; the account-titling and NUA decisions are
irreversible and warrant professional review.
