> TEST FIXTURE: generated from tests/stubweb.py (invented .test pages and a scripted model) to show the agents on a second, business-to-business concept. Not real research.

# Appendix: evidence, calculations and validation

## A. Idea brief (research-planning agent)

- founder statement: A scheduling app for independent coffee shops in Austin that helps owners build weekly staff rosters without spreadsheets. It is not a payroll system.
- product: scheduling app
- target customer: independent coffee shops
- problem: building weekly staff rosters takes hours
- customer job: build weekly staff rosters
- geography: Austin
- stage: idea
- payer: business
- business model: -
- network product: False
- venue: shop
- category: coffee shop staff scheduling software
- interpretation flags: planner restated product with 'marketplace', which the founder did not say; kept the founder's wording; planner proposed business model 'subscription marketplace commission' that the founder did not state; left open

## B. Assumptions map (most important first)

| ID | Hypothesis | Importance | Evidence | Questions |
|---|---|---|---|---|
| H-D1 | We believe that independent coffee shops in Austin experience 'building weekly staff rosters takes hours' often enough to want a dedicated solution. | 3 | mixed (1 supporting, 1 contradicting, 0 neutral) | Q-C1, Q-C2 |
| H-D2 | We believe that independent coffee shops would choose this over what they use today to build weekly staff rosters. | 3 | mixed (1 supporting, 1 contradicting, 0 neutral) | Q-C2, Q-K2 |
| H-V1 | We believe that businesses will pay for it (or that another payer will). | 3 | contradicted (0 supporting, 1 contradicting, 0 neutral) | Q-W1 |
| H-V2 | We believe that the reachable market in Austin is large enough to support the business. | 2 | weak (0 supporting, 0 contradicting, 1 neutral) | Q-M1 |
| H-V3 | We believe that early users can be reached at low cost through existing channels. | 2 | weak (0 supporting, 0 contradicting, 1 neutral) | Q-D1 |
| H-F1 | We believe that a small team can build the first version with standard, affordable components. | 1 | weak (0 supporting, 0 contradicting, 1 neutral) | Q-F1 |

## C. Research questions and findings

### Q-C1 Do independent coffee shops actually experience the problem 'building weekly staff rosters takes hours'? In what situations and how often?

- Status: answered; attempts: 1
- Query (seed): site:reddit.com build weekly staff rosters -> 3 results, 3 relevant
- Query (seed): independent coffee shops build weekly staff rosters forum -> 5 results, 5 relevant
- Query (seed): build weekly staff rosters -> 3 results, 3 relevant
- Query (seed): build weekly staff rosters easy independent coffee shops -> 5 results, 5 relevant
- Evidence packet: E3 (reddit.com), E1 (forum.coffeeowners.test), E5 (austinchronicle.test), E6 (blog.founderstories.test), E2 (rosterpal.test), E4 (shiftbrew.test)
- Q-C1-F1 [fact | partially_supported | finding | supports] As a cafe owner I spend about three hours every week building the staff schedule in a spreadsheet. - sources: E3; types: forum_community; flags: single website
- Q-C1-F2 [fact | partially_supported | finding | contradicts] We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing. - sources: E1; types: forum_community; flags: single website
- Q-C1-F3 [fact | partially_supported | off_question | neutral] Austin has more than 320 independent coffee shops, according to the 2026 city business directory. - sources: E5; types: blog_other; flags: statistic only from low-credibility pages (aggregators/blogs); single website
- Note: Q-C1-F3 does not address this question (customer); not used

### Q-C2 How do independent coffee shops currently build weekly staff rosters, and what is wrong with those ways?

- Status: answered; attempts: 1
- Query (seed): how do you build weekly staff rosters reddit -> 3 results, 3 relevant
- Query (seed): best way to build weekly staff rosters Austin -> 4 results, 4 relevant
- Query (seed): build weekly staff rosters works fine without an app -> 3 results, 3 relevant
- Evidence packet: E1 (forum.coffeeowners.test), E8 (meetup.com), E3 (reddit.com), E5 (austinchronicle.test), E6 (blog.founderstories.test), E2 (rosterpal.test)
- Q-C2-F1 [fact | partially_supported | finding | contradicts] We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing. - sources: E1; types: forum_community; flags: single website
- Q-C2-F2 [fact | partially_supported | off_question | neutral] A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. - sources: E8; types: forum_community; flags: single website
- Q-C2-F3 [fact | partially_supported | finding | supports] As a cafe owner I spend about three hours every week building the staff schedule in a spreadsheet. - sources: E3; types: forum_community; flags: single website
- Note: Q-C2-F2 does not address this question (customer); not used

### Q-W1 Is there evidence that independent coffee shops spend money to build weekly staff rosters? What do they say about paying?

- Status: answered; attempts: 1
- Query (seed): coffee shop staff scheduling worth paying for reddit -> 5 results, 5 relevant
- Query (seed): coffee shop staff scheduling subscription price review -> 5 results, 4 relevant
- Query (seed): coffee shop staff scheduling should be free -> 5 results, 5 relevant
- Evidence packet: E1 (forum.coffeeowners.test), E8 (meetup.com), E3 (reddit.com), E6 (blog.founderstories.test), E2 (rosterpal.test), E5 (austinchronicle.test)
- Q-W1-F1 [fact | partially_supported | finding | contradicts] We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing. - sources: E1; types: forum_community; flags: single website
- Q-W1-F2 [fact | partially_supported | off_question | neutral] A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. - sources: E8; types: forum_community; flags: single website
- Q-W1-F3 [fact | partially_supported | off_question | supports] As a cafe owner I spend about three hours every week building the staff schedule in a spreadsheet. - sources: E3; types: forum_community; flags: single website
- Note: Q-W1-F2 does not address this question (customer); not used
- Note: Q-W1-F3 does not address this question (customer); not used

### Q-R1 How do comparable products make money and at what prices?

- Status: answered; attempts: 1
- Query (seed): coffee shop staff scheduling pricing premium plan -> 5 results, 5 relevant
- Query (seed): RosterPal pricing -> 0 results, 0 relevant
- Query (seed): ShiftBrew pricing -> 1 results, 1 relevant
- Evidence packet: E2 (rosterpal.test), E4 (shiftbrew.test), E8 (meetup.com), E1 (forum.coffeeowners.test), E6 (blog.founderstories.test), E5 (austinchronicle.test)
- Q-R1-F1 [fact | partially_supported | finding | neutral] RosterPal is free for up to 10 employees. - sources: E2; types: official_vendor; flags: vendor's own claim: no independent source
- Q-R1-F2 [fact | partially_supported | finding | neutral] ShiftBrew scheduling costs $39 per month per location. - sources: E4; types: official_vendor; flags: vendor's own claim: no independent source
- Q-R1-F3 [fact | partially_supported | off_question | neutral] A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. - sources: E8; types: forum_community
- Note: Q-R1-F3 does not address this question (revenue); not used

### Q-M1 How many shops are there Austin, or how many shops and members, as a basis for a bottom-up market estimate?

- Status: answered; attempts: 1
- Query (seed): shops coffee shop staff scheduling Austin -> 5 results, 5 relevant
- Query (seed): number of independent coffee shops Austin -> 5 results, 5 relevant
- Query (seed): coffee shop staff scheduling Austin -> 5 results, 5 relevant
- Evidence packet: E2 (rosterpal.test), E5 (austinchronicle.test), E8 (meetup.com), E6 (blog.founderstories.test), E1 (forum.coffeeowners.test), E4 (shiftbrew.test)
- Q-M1-F1 [fact | partially_supported | broader_context | neutral] RosterPal is free for up to 10 employees. - sources: E2; types: official_vendor; flags: vendor's own claim: no independent source; single website
- Q-M1-F2 [fact | partially_supported | finding | neutral] Austin has more than 320 independent coffee shops, according to the 2026 city business directory. - sources: E5; types: blog_other; flags: statistic only from low-credibility pages (aggregators/blogs); single website
- Q-M1-F3 [fact | partially_supported | off_question | neutral] A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. - sources: E8; types: forum_community; flags: single website
- Note: Q-M1-F1 comes only from a company's own website; not independent evidence for this question
- Note: Q-M1-F1 is not about Austin; kept as context only
- Note: Q-M1-F3 does not address this question (market); not used

### Q-D1 Where do independent coffee shops Austin gather or look for this today (groups, clubs, venues, events, online communities)?

- Status: answered; attempts: 1
- Query (seed): independent coffee shops coffee shop staff scheduling group Austin -> 5 results, 5 relevant
- Query (seed): coffee shop staff scheduling club meetup Austin -> 5 results, 5 relevant
- Evidence packet: E8 (meetup.com), E1 (forum.coffeeowners.test), E2 (rosterpal.test), E3 (reddit.com), E5 (austinchronicle.test), E6 (blog.founderstories.test)
- Q-D1-F1 [fact | partially_supported | finding | neutral] A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. - sources: E8; types: forum_community
- Q-D1-F2 [fact | partially_supported | broader_context | contradicts] We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing. - sources: E1; types: forum_community
- Q-D1-F3 [fact | partially_supported | broader_context | neutral] RosterPal is free for up to 10 employees. - sources: E2; types: official_vendor; flags: vendor's own claim: no independent source
- Note: Q-D1-F2 does not address this question (distribution); not used
- Note: Q-D1-F2 is not about Austin; kept as context only
- Note: Q-D1-F3 does not address this question (distribution); not used
- Note: Q-D1-F3 is not about Austin; kept as context only

### Q-F1 Which technical components does the first version of 'scheduling app' need, and which can be bought or reused?

- Status: answered; attempts: 1
- Query (seed): scheduling app architecture backend -> 2 results, 1 relevant
- Query (seed): scheduling API service pricing -> 2 results, 2 relevant
- Evidence packet: E10 (devblog.test), E4 (shiftbrew.test), E6 (blog.founderstories.test), E2 (rosterpal.test), E3 (reddit.com), E1 (forum.coffeeowners.test)
- Q-F1-F1 [fact | partially_supported | finding | neutral] A shift scheduling backend needs a database of availability, a calendar API and push notification service; open source libraries handle recurring shifts. - sources: E10; types: blog_other
- Q-F1-F2 [fact | partially_supported | off_question | neutral] ShiftBrew scheduling costs $39 per month per location. - sources: E4; types: official_vendor; flags: vendor's own claim: no independent source
- Q-F1-F3 [fact | partially_supported | off_question | contradicts] Our coffee shop scheduling startup shut down because small cafes would not pay more than $10 a month and churned after the free trial. - sources: E6; types: blog_other; flags: statistic only from low-credibility pages (aggregators/blogs)
- Note: Q-F1-F2 does not address this question (feasibility); not used
- Note: Q-F1-F3 does not address this question (feasibility); not used

### Q-X1 Why have similar products failed or shut down?

- Status: answered; attempts: 1
- Query (seed): coffee shop staff scheduling startup shut down why -> 5 results, 5 relevant
- Query (seed): coffee shop staff scheduling app failed lessons -> 5 results, 5 relevant
- Evidence packet: E6 (blog.founderstories.test), E5 (austinchronicle.test), E8 (meetup.com), E1 (forum.coffeeowners.test), E3 (reddit.com), E2 (rosterpal.test)
- Q-X1-F1 [fact | partially_supported | finding | contradicts] Our coffee shop scheduling startup shut down because small cafes would not pay more than $10 a month and churned after the free trial. - sources: E6; types: blog_other; flags: statistic only from low-credibility pages (aggregators/blogs)
- Q-X1-F2 [fact | partially_supported | off_question | neutral] Austin has more than 320 independent coffee shops, according to the 2026 city business directory. - sources: E5; types: blog_other; flags: statistic only from low-credibility pages (aggregators/blogs)
- Q-X1-F3 [fact | partially_supported | off_question | neutral] A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. - sources: E8; types: forum_community
- Note: Q-X1-F2 does not address this question (risk); not used
- Note: Q-X1-F3 does not address this question (risk); not used

### Q-K2 What do users of RosterPal and ShiftBrew dislike or wish were different?

- Status: partly answered; attempts: 1
- Query (seed): RosterPal app reviews -> 1 results, 1 relevant
- Query (seed): ShiftBrew app reviews -> 1 results, 1 relevant
- Query (seed): RosterPal reddit -> 0 results, 0 relevant
- Evidence packet: E7 (apps.apple.com), E2 (rosterpal.test)
- Q-K2-F1 [fact | partially_supported | finding | supports] The shift swap feature keeps crashing and I wish it handled availability better for part-time baristas. - sources: E7; types: app_store; flags: vendor's own claim: no independent source
- Q-K2-F2 [fact | partially_supported | off_question | neutral] RosterPal is free for up to 10 employees. - sources: E2; types: official_vendor; flags: vendor's own claim: no independent source
- Note: Q-K2-F2 does not address this question (competition); not used

## D. Economics: assumptions, calculations and sensitivity

| Assumption | Value | Range | Basis | Uncertainty | Rationale | Sources |
|---|---|---|---|---|---|---|
| price_monthly | 39.0 $/paying user/month | 39.0 to 39.0 | competitor_price | high | median of what alternatives charge (ShiftBrew); this is NOT evidence that these customers will pay it | E4 |
| paying_share | 1.0 share of active accounts that pay | 1.0 to 1.0 | scenario_choice | medium | business accounts pay after a trial; trial-to-paid conversion is tested separately | - |
| payment_fee | 0.03 share of price | 0.02 to 0.05 | rule_of_thumb | low | card processing for web billing | - |
| variable_cost | 3.0 $/active account/month | 1.0 to 10.0 | rule_of_thumb | medium | hosting plus a little support time per account | - |
| fixed_monthly[solo_bootstrapped] | 150.0 $/month | 105.0 to 225.0 | scenario_choice | medium | design/no-code or own code, app-store and domain fees, low-cost hosting tier, basic tools | - |
| mvp_cash[solo_bootstrapped] | 1500.0 $ | 750.0 to 3000.0 | scenario_choice | high | design/no-code or own code, app-store and domain fees, low-cost hosting tier, basic tools | - |
| fixed_monthly[part_time_team] | 600.0 $/month | 420.0 to 900.0 | scenario_choice | medium | about 150-200 contractor hours for an MVP, plus hosting, tools and a small marketing test budget | - |
| mvp_cash[part_time_team] | 15000.0 $ | 7500.0 to 30000.0 | scenario_choice | high | about 150-200 contractor hours for an MVP, plus hosting, tools and a small marketing test budget | - |
| fixed_monthly[venture_backed] | 24000.0 $/month | 16800.0 to 36000.0 | scenario_choice | medium | two salaries with overhead (~$10k/month each), tools, hosting and paid acquisition tests | - |
| mvp_cash[venture_backed] | 40000.0 $ | 20000.0 to 80000.0 | scenario_choice | high | two salaries with overhead (~$10k/month each), tools, hosting and paid acquisition tests | - |

Formulas: contribution per paying user = price x (1 - payment fee) - variable cost per active user / paying share; break-even paying users = monthly fixed costs / contribution; break-even active users = break-even paying users / paying share; funding to milestone = MVP cash + monthly costs x (MVP months + 6) + experiment budget.

Sensitivity of break-even ACTIVE users (base scenario, monthly costs $150):

| Paying share | price $39 |
|---|---|
| 100% | 5 |

Multi-year projection: not produced: price and reachable-market inputs are not evidence-based.

## E. Cross-section checks (decision synthesis)

- X5 Evidence suggests customers may not pay (weight 5; hypotheses H-V1; evidence contradicted): 1 independent finding(s) indicate businesses will not pay for this (or that free options are good enough); the $39.00/month in the economics is what alternatives charge. -> Test payment before building; plan for a lower price, a different payer or a stronger reason to pay.
- X1 Evidence on the customer problem is mixed (weight 4; hypotheses H-D1; evidence mixed): 1 independent finding(s) support the problem and 1 contradict it. -> The problem may matter only to part of the segment; interviews must find out which independent coffee shops feel it and why the others do not.
- X2 Free alternatives set the price anchor (weight 4; hypotheses H-V1, H-D2; evidence contradicted): RosterPal, Online forums and community groups are free to use or download, at least in a basic version. -> A paid product must save owners more than the free option does; expect a free tier with paid features or a bundle with something they already pay for, and treat the price as unproven.
- X6 The local market is not the binding constraint (weight 2; hypotheses H-V2; evidence weak): About 320 shops were counted in Austin; break-even in the base scenario needs about 1.6% of them. -> Size is sufficient for a lean start; adoption and payment, not market size, decide the outcome.
- X7 Lean economics are small but reachable only with validated demand (weight 2; hypotheses H-V1, H-V2; evidence contradicted): In the solo founder, bootstrapped scenario, about 5 paying accounts (5 active) cover the $150 monthly costs; reaching the next milestone needs about $3,300. -> A salaried team multiplies the required volume (see the scenarios); stay lean until demand and payment are shown.

## F. Report checks

- Numbers checked in the memo: 64; untraced: none
- Contradictions with computed results: none
- Evidence mode: live

## G. Method

The research-planning agent restates the idea and builds an assumptions map (desirability, viability, feasibility; Strategyzer assumptions mapping). Each research question is answered from a small evidence packet (at most two items per website, preferred source types first) by one narrow extraction call; code validates every finding (support, source independence, geography, question fit). The synthesis rules, economics and experiments are deterministic. Frameworks: Y Combinator's idea-evaluation questions, Sequoia's business-plan outline, Strategyzer's assumptions mapping.

---

# Part 2: research-run evidence log (report-v3 appendix)

## Evidence and methodology appendix

For: Coffee Shop Staff Scheduling Software - Founder Decision Memo. Report schema report-v3; source run 2026-11-09 (adaptive-v2).

## A. Corrections applied to this report

None.

## B. Open questions and next actions

| Question | Why it matters | Not yet established | Next action | Who |
|---|---|---|---|---|
| Why someone would switch from RosterPal, ShiftBrew | Direct alternatives already address the same need; without a reason to switch, adoption stalls. | Whether their users are dissatisfied, and with what. | Ask 8-10 current users of these alternatives what fails for them; compare features side by side. | founder |
| Initial target segment | It decides channels, features and pricing. | Which sub-group feels the problem most and can be reached first. | Interview 10-15 people from that group in Austin; ask when the problem last happened and what they did. | founder |
| Willingness to pay for this product | Price and conversion decide whether the business can cover its costs. | What these customers would pay for this product, and how many would. | Run a pricing test: landing page with two price points and a pre-order or waitlist button. | founder |
| Current workaround | The workaround is the real competitor and sets the bar. | How people solve this today and how well it works. | Search community forums for how people currently solve it; confirm in interviews. | web research + founder |
| How often the problem occurs | A rare problem does not sustain an app habit. | Frequency and severity for the target group. | Ask in interviews: 'when did this last happen?' | founder |
| How to reach early users | Acquisition cost depends on a reachable channel. | Which channel brings sign-ups at what cost. | Test 2 channels (e.g. community posts, venue flyers) with a sign-up form; record cost per sign-up. | founder |
| Size of the reachable Austin market | Shows whether the launch area can support the business. | Missing inputs: Active local participants, Share with the problem, Share reachable in year 1… | Collect the missing inputs as listed in the market table (venue counts first). | web research + founder |
| Minimum user journey and architecture | Determines build cost, timeline and which risks matter. | A component list with responsibilities and build/buy choices was not produced. | Rerun the technical role (it now requires generic components), or sketch the journey: sign up -> set availability ->… | web research |

## C. Claims and support

Status comes from a lexical screen by code plus a fallible model check (recorded separately in the JSON). Lexical matches alone are at most 'partially supported'. Type: external fact, source-reported (a vendor about itself), assumption or proposal.

### Competitor

| Claim | Status | Type | Sources | Note |
|---|---|---|---|---|
| Search result for RosterPal: RosterPal - free staff scheduling for small teams | unsupported | source reported | E2 | model check: [mock] word overlap check |
| Search result for ShiftBrew: ShiftBrew pricing - plans for cafes | unsupported | source reported | E4 | model check: [mock] word overlap check |
| RosterPal pricing: unknown | explicit assumption | assumption |  | stated as an estimate or unknown |
| ShiftBrew pricing: unknown | explicit assumption | assumption |  | stated as an estimate or unknown |
| Scheduling pricing: unknown | explicit assumption | assumption |  | stated as an estimate or unknown |
| Austin pricing: unknown | explicit assumption | assumption |  | stated as an estimate or unknown |

### Customer

| Claim | Status | Type | Sources | Note |
|---|---|---|---|---|
| As a cafe owner I spend about three hours every week building the staff schedule in a spreadsheet. | partially supported | external fact | E3 | lexical match only (numbers and wording found); not semantically verified |
| We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing. | partially supported | external fact | E1 | lexical match only (numbers and wording found); not semantically verified |
| Austin has more than 320 independent coffee shops, according to the 2026 city business directory. | partially supported | source reported | E5 | lexical match only (numbers and wording found); not semantically verified |
| We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing. | partially supported | external fact | E1 | lexical match only (numbers and wording found); not semantically verified |
| A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. | partially supported | external fact | E8 | lexical match only (numbers and wording found); not semantically verified |
| As a cafe owner I spend about three hours every week building the staff schedule in a spreadsheet. | partially supported | external fact | E3 | lexical match only (numbers and wording found); not semantically verified |
| We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing. | partially supported | external fact | E1 | lexical match only (numbers and wording found); not semantically verified |
| A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. | partially supported | external fact | E8 | lexical match only (numbers and wording found); not semantically verified |
| As a cafe owner I spend about three hours every week building the staff schedule in a spreadsheet. | partially supported | external fact | E3 | lexical match only (numbers and wording found); not semantically verified |

### Revenue

| Claim | Status | Type | Sources | Note |
|---|---|---|---|---|
| RosterPal is free for up to 10 employees. | partially supported | source reported | E2 | lexical match only (numbers and wording found); not semantically verified |
| ShiftBrew scheduling costs $39 per month per location. | partially supported | source reported | E4 | lexical match only (numbers and wording found); not semantically verified |
| A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. | partially supported | external fact | E8 | lexical match only (numbers and wording found); not semantically verified |

### Market

| Claim | Status | Type | Sources | Note |
|---|---|---|---|---|
| RosterPal is free for up to 10 employees. | partially supported | source reported | E2 | lexical match only (numbers and wording found); not semantically verified |
| Austin has more than 320 independent coffee shops, according to the 2026 city business directory. | partially supported | source reported | E5 | lexical match only (numbers and wording found); not semantically verified |
| A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. | partially supported | external fact | E8 | lexical match only (numbers and wording found); not semantically verified |

### Distribution

| Claim | Status | Type | Sources | Note |
|---|---|---|---|---|
| A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. | partially supported | external fact | E8 | lexical match only (numbers and wording found); not semantically verified |
| We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing. | partially supported | external fact | E1 | lexical match only (numbers and wording found); not semantically verified |
| RosterPal is free for up to 10 employees. | partially supported | source reported | E2 | lexical match only (numbers and wording found); not semantically verified |

### Feasibility

| Claim | Status | Type | Sources | Note |
|---|---|---|---|---|
| A shift scheduling backend needs a database of availability, a calendar API and push notification service; | partially supported | external fact | E10 | lexical match only (numbers and wording found); not semantically verified |
| ShiftBrew scheduling costs $39 per month per location. | partially supported | source reported | E4 | lexical match only (numbers and wording found); not semantically verified |
| Our coffee shop scheduling startup shut down because small cafes would not pay more than $10 a month and churned after the free… | partially supported | external fact | E6 | lexical match only (numbers and wording found); not semantically verified |

### Risk

| Claim | Status | Type | Sources | Note |
|---|---|---|---|---|
| Our coffee shop scheduling startup shut down because small cafes would not pay more than $10 a month and churned after the free… | partially supported | external fact | E6 | lexical match only (numbers and wording found); not semantically verified |
| Austin has more than 320 independent coffee shops, according to the 2026 city business directory. | partially supported | source reported | E5 | lexical match only (numbers and wording found); not semantically verified |
| A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. | partially supported | external fact | E8 | lexical match only (numbers and wording found); not semantically verified |

### Competition

| Claim | Status | Type | Sources | Note |
|---|---|---|---|---|
| The shift swap feature keeps crashing and I wish it handled availability better for part-time baristas. | partially supported | source reported | E7 | lexical match only (numbers and wording found); not semantically verified |
| RosterPal is free for up to 10 employees. | partially supported | source reported | E2 | lexical match only (numbers and wording found); not semantically verified |

## D. Assumption register

| Assumption | Value | Basis | Status | Reason |
|---|---|---|---|---|
| market: Active local participants | missing | market input | missing | Ask venue operators for active-member counts; search for published local membership… |
| market: Share with the problem | missing | market input | missing | Short survey at 2-3 venues (founder). |
| market: Share reachable in year 1 | missing | market input | missing | Channel test with a sign-up form. |
| market: Paying share | missing | market input | missing | Pricing test (pre-order or waitlist with price). |
| market: Monthly price | missing | market input | missing | Pricing test; the model's price is an assumption. |

## E. Financial calculations

Price n/a/month, 0 new paying customers in year 1 growing 0%/yr, churn 0%/yr, CAC n/a, cost of revenue 0%.

| Year | Paying customers | Revenue | Operating result | Cumulative cash |
|---|---|---|---|---|

Team: . One-off startup costs: .

## F. Issues and review history


## G. Research history and budgets

- **competitor:** 5 searches (5 with relevant results), 2 pages read; stopped: no search or page-read budget left for this section
- Run budget used: 38 of 45 searches, 15 of 16 page reads.

## H. Sources

- **E1** [Scheduling staff at a small coffee shop - forum](https://forum.coffeeowners.test/t/42) *(relevant)*: "We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing."
- **E2** [RosterPal - free staff scheduling for small teams](https://rosterpal.test/) *(relevant)*: "RosterPal is free for up to 10 employees. RosterPal is a scheduling app for restaurants and coffee shops."
- **E3** [How do you schedule baristas? : r/barista](https://www.reddit.com/r/barista/comments/a1/schedule) *(relevant)*: "As a cafe owner I spend about three hours every week building the staff schedule in a spreadsheet. Shift swaps by text message are the worst part of scheduling baristas."
- **E4** [ShiftBrew pricing - plans for cafes](https://shiftbrew.test/pricing) *(weak)*: "ShiftBrew scheduling costs $39 per month per location. ShiftBrew helps cafes build shift schedules."
- **E5** [Austin coffee scene report](https://www.austinchronicle.test/food/coffee-2026) *(relevant)*: "Austin has more than 320 independent coffee shops, according to the 2026 city business directory."
- **E6** [Why our cafe scheduling startup shut down](https://blog.founderstories.test/cafe-shifts) *(relevant)*: "Our coffee shop scheduling startup shut down because small cafes would not pay more than $10 a month and churned after the free trial."
- **E7** [ShiftBrew reviews - App Store](https://apps.apple.com/us/app/shiftbrew/id1) *(irrelevant)*: "The shift swap feature keeps crashing and I wish it handled availability better for part-time baristas."
- **E8** [Austin Independent Coffee Owners Meetup](https://www.meetup.com/austin-coffee-owners/) *(relevant)*: "A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips."
- **E10** [Building a shift scheduling backend with a calendar API](https://devblog.test/shift-api) *(weak)*: "A shift scheduling backend needs a database of availability, a calendar API and push notification service; open source libraries handle recurring shifts."

10 sources were collected; 9 are cited above. All are in the JSON with relevance scores.

## I. Validation layers

| Layer | Result |
|---|---|
| Source credibility | 26 citations behind supported claims: forum community 13, official vendor 9, blog other 3, app store 1 |
| Independence | 38% of those citations come from the companies' own sites or app stores |
| Claim flags | 21 claims flagged (vendor-only, single website, low-credibility statistic, dated); 0 downgraded |
| Plausibility | 1 warning(s); ranges are heuristics, not benchmarks |
| Consistency | year-1 paying customers vs local participants: not checkable; modelled price vs willingness to pay: not checkable |
| Fact-checker reliability | passed all 1 control probes |
| Publication gate | passed (48 numbers checked) |

- Plausibility (warning): cac = None — zero acquisition cost. Even organic growth costs time or money.
- Consistency, year-1 paying customers vs local participants: **not checkable** — local participant count is unknown, so 0 year-1 paying customers cannot be checked against the market.
- Consistency, modelled price vs willingness to pay: **not checkable** — willingness to pay is unknown.

## J. Runtime and models

- Workflow: questions-v1; models: {'main': 'ScriptedSmallModel', 'fast': 'ScriptedSmallModel'}; elapsed: 0 s.
- Budget: 0 min; context 4096 tokens; reply ceiling 1600; review rounds 1.

