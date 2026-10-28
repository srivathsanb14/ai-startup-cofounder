# Financial model

Implemented in `startup_cofounder/finance.py`. The LLM supplies **assumptions only**; everything below is
computed in code, so results are consistent, reproducible and unit-tested (`tests/test_core.py`).

## Inputs (assumptions)

| Name | Meaning | Allowed range | Default |
|---|---|---|---|
| `arpu_monthly` | revenue per customer per month | 0 to 1,000,000 | 30 |
| `year1_new_customers` | customers acquired in year 1 | 0 to 10,000,000 | 200 |
| `growth_rate` | year-over-year growth in **new** customers acquired | -0.5 to 5.0 | 0.8 |
| `annual_churn` | share of customers lost per year | 0 to 0.95 | 0.2 |
| `cogs_pct` | cost of goods as a share of revenue | 0 to 0.95 | 0.2 |
| `cac` | cost to acquire one customer | 0 to 1,000,000 | 150 |
| `other_opex_annual` | rent, tools, legal, misc. per year | 0+ | 24,000 |
| `payroll_burden` | taxes/benefits on top of salary | 0 to 1 | 0.2 |
| `team[]` | `{role, count, annual_salary, start_year 1-5}` | | founder + engineer |
| `startup_costs[]` | `{item, amount}` one-off costs before year 1 | | legal 5k, MVP 30k |

`sanitize()` makes this safe for LLM output: it strips `$`, `,` and `%`, clamps to the ranges above, replaces
unparseable values with defaults, and converts rates given as `20` into `0.20`.

## Projection (5 years)

For year `y` (1-5):

```
new[1] = year1_new_customers;  new[y] = new[y-1] * (1 + growth_rate)
churned    = customers_start * annual_churn
customers_end = customers_start - churned + new
revenue    = arpu_monthly * 12 * (customers_start + customers_end) / 2     # average customers
cogs       = revenue * cogs_pct
marketing  = new * cac
payroll    = sum(count * salary for team members with start_year <= y) * (1 + payroll_burden)
other      = other_opex_annual
operating_profit = revenue - cogs - marketing - payroll - other
cumulative_cash  = -sum(startup_costs) + sum of operating_profit to date
```

Derived: **operating break-even year** (first year with positive operating profit), **cash payback year**
(first year cumulative cash >= 0), **peak funding need** (deepest cumulative deficit including startup costs).

## Unit economics

```
gross_margin_monthly = arpu_monthly * (1 - cogs_pct)
monthly_churn        = 1 - (1 - annual_churn) ^ (1/12)
lifetime_months      = min(1 / monthly_churn, 60)          # capped so ~0 churn does not give absurd LTV
LTV                  = gross_margin_monthly * lifetime_months
LTV/CAC              = LTV / cac
CAC payback (months) = cac / gross_margin_monthly
```

Rule of thumb used by the guardrail: **LTV/CAC >= 3** and **CAC payback <= 18 months**.

## Scenarios

| Scenario | Price | Year-1 new customers | Growth | Churn | CAC |
|---|---|---|---|---|---|
| Pessimistic | x0.85 | x0.5 | x0.6 | x1.4 | x1.4 |
| Base | x1 | x1 | x1 | x1 | x1 |
| Optimistic | x1.1 | x1.4 | x1.2 | x0.75 | x0.85 |

The report shows year-5 customers, revenue, operating profit, break-even and peak funding per scenario, and the
UI plots cumulative cash for all three.

## Sensitivity

For each of price, year-1 customers, growth, churn, COGS % and CAC, the model re-runs with that single
assumption 20% lower and 20% higher and reports the change in **year-5 operating profit**, sorted by swing
(tornado order). The top rows are the assumptions to validate first.

## Sanity checks (`sanity_flags`)

Plain-English warnings are added to the report and fed to the synthesizer when:

- LTV/CAC < 3
- CAC payback > 18 months, or gross margin per customer <= 0
- year-5 revenue exceeds 5% of the serviceable market (SAM)
- year-5 revenue per employee < $80k
- peak funding need > $2M (implies outside capital)
- no operating break-even within 5 years

## Limits

- It models a **subscription-style** business (recurring revenue per customer). Marketplaces, hardware or
  ad-supported businesses should be read as rough approximations (the agents are asked to map pricing to an
  equivalent per-customer monthly figure).
- No taxes, interest, working capital, seasonality or fundraising dilution.
- Hiring is a fixed schedule per role, not a function of revenue.
