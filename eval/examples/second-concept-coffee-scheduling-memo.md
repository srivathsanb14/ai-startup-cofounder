> TEST FIXTURE: generated from tests/stubweb.py (invented .test pages and a scripted model) to show the agents on a second, business-to-business concept. Not real research.

# Startup assessment: scheduling app

**The founder's idea (verbatim):** A scheduling app for independent coffee shops in Austin that helps owners build weekly staff rosters without spreadsheets. It is not a payroll system.

Read as: *scheduling app* for **independent coffee shops** in Austin; stage: **idea**; paying customer: **businesses**.
> Interpretation check: planner restated product with 'marketplace', which the founder did not say; kept the founder's wording.
> Interpretation check: planner proposed business model 'subscription marketplace commission' that the founder did not state; left open.
> Out of scope (founder): payroll system.

## 1. Recommendation: Validate first

**Why:** The decisive assumptions are not yet supported by independent evidence (H-D1: mixed, H-D2: mixed, H-V1: contradicted).

**Key findings and what they mean**

1. **Evidence suggests customers may not pay.** 1 independent finding(s) indicate businesses will not pay for this (or that free options are good enough); the $39.00/month in the economics is what alternatives charge. *Implication:* Test payment before building; plan for a lower price, a different payer or a stronger reason to pay.
2. **Evidence on the customer problem is mixed.** 1 independent finding(s) support the problem and 1 contradict it. *Implication:* The problem may matter only to part of the segment; interviews must find out which independent coffee shops feel it and why the others do not.
3. **Free alternatives set the price anchor.** RosterPal, Online forums and community groups are free to use or download, at least in a basic version. *Implication:* A paid product must save owners more than the free option does; expect a free tier with paid features or a bundle with something they already pay for, and treat the price as unproven.
4. **The local market is not the binding constraint.** About 320 shops were counted in Austin; break-even in the base scenario needs about 1.6% of them. *Implication:* Size is sufficient for a lean start; adoption and payment, not market size, decide the outcome.
5. **Lean economics are small but reachable only with validated demand.** In the solo founder, bootstrapped scenario, about 5 paying accounts (5 active) cover the $150 monthly costs; reaching the next milestone needs about $3,300. *Implication:* A salaried team multiplies the required volume (see the scenarios); stay lean until demand and payment are shown.

- **Proceed if** owners confirm the problem, keep using the manual service, and commit to a paid pilot at the tested price.
- **Modify if** they use the service but will not pay (try a lower price, a different buyer or a bundle) or only one type of business keeps using it.
- **Stop if** few owners describe the problem or keep using the service even when it is done for them.

## 2. Customer problem and evidence

*Is the problem real and frequent?* Evidence level: **mixed: independent evidence on both sides**.
- As a cafe owner I spend about three hours every week building the staff schedule in a spreadsheet. [[1]](https://www.reddit.com/r/barista/comments/a1/schedule)
- We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing. (contradicts the founder's assumption) [[2]](https://forum.coffeeowners.test/t/42)

*How do they solve it today?*
- We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing. (contradicts the founder's assumption) [[2]](https://forum.coffeeowners.test/t/42)
- As a cafe owner I spend about three hours every week building the staff schedule in a spreadsheet. [[1]](https://www.reddit.com/r/barista/comments/a1/schedule)

*Would they pay?* Evidence level: **contradicted by evidence**.
- We tried a scheduling app but went back to paper; for six staff a printed roster works fine and costs nothing. (contradicts the founder's assumption) [[2]](https://forum.coffeeowners.test/t/42)

## 3. Competitive landscape and differentiation

- **RosterPal** (direct); price: free (Q-R1-F1).
- **ShiftBrew** (direct); price: $39/month (Q-R1-F2).
- **Online forums and community groups** (substitute); price: free.

*What users of the alternatives dislike:*
- The shift swap feature keeps crashing and I wish it handled availability better for part-time baristas. [[3]](https://apps.apple.com/us/app/shiftbrew/id1)
- **So what:** see key finding 3 (free alternatives set the price anchor).

## 4. Market opportunity and distribution

- Counted in Austin: about 320 shops [[4]](https://www.austinchronicle.test/food/coffee-2026).
- Break-even in the base scenario needs 1.6% of that count as active users.

*Where to reach them first:*
- A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips. [[5]](https://www.meetup.com/austin-coffee-owners/)

## 5. Product feasibility and business economics

*Feasibility:*
- A shift scheduling backend needs a database of availability, a calendar API and push notification service; open source libraries handle recurring shifts. [[6]](https://devblog.test/shift-api)

*Economics (deterministic; assumptions and sources in Appendix D):* price $39/month per paying account (competitor price); contribution $35 per paying account per month after fees and variable costs.

| Scenario | MVP cash | Monthly costs | Break-even paying accounts | Funding to next milestone |
|---|---|---|---|---|
| Solo founder, bootstrapped | $1.5K | $150 | 5 | $3.3K |
| Part-time team with a contractor | $15.0K | $600 | 18 | $21.7K |
| Venture-backed team | $40.0K | $24.0K | 690 | $260.5K |

- Price is borrowed from competitors, not observed willingness to pay; break-even volumes are only as good as this price.
- Free alternative(s) exist (RosterPal, Online forums and community groups): the paid tier must offer something the free option does not.
- No multi-year projection is shown (price and reachable-market inputs are not evidence-based).

## 6. Most consequential risks

| Risk | Evidence today | Reduced by |
|---|---|---|
| Evidence suggests customers may not pay | contradicted by evidence | Experiment 3 |
| Evidence on the customer problem is mixed | mixed: independent evidence on both sides | Experiment 1 |
| Free alternatives set the price anchor | contradicted by evidence | Experiment 3 |
| The local market is not the binding constraint | only weak or indirect evidence | bottom-up count (Section 4) |

## 7. Validation experiments and next steps

**Experiment 1 - We believe that independent coffee shops in Austin experience 'building weekly staff rosters takes hours' often enough to want a dedicated solution.** (H-D1)

- Segment: independent coffee shops in Austin
- Method: Problem interviews: 12-15 conversations with the people who do this job at independent coffee shops in Austin about the LAST time they tried to build weekly staff rosters (past behaviour, not opinions about the idea).
- Metric: share who describe the problem in the last month without prompting, and what they did; **threshold:** at least 6 of 12 describe a recent, specific occurrence
- Cost and time: $0-150 (coffee/gift cards), 1-2 weeks
- If it passes: the problem is real and frequent: design the pilot around the situations they described. If it fails: the problem is rare or mild: change the problem or customer before building.
- Next step: run the participation pilot with the people who described the problem

**Experiment 2 - We believe that independent coffee shops would choose this over what they use today to build weekly staff rosters.** (H-D2)

- Segment: independent coffee shops in Austin
- Method: Concierge service: for 5 independent coffee shops in Austin, deliver the result by hand each week for 3 weeks (build weekly staff rosters), with no software.
- Metric: how many keep using the service each week, and time saved per week as they report it; **threshold:** at least 3 of 5 still use it in week 3 and report saving at least 1 hour a week
- Cost and time: $0 (founder time), 3 weeks
- If it passes: the job is worth outsourcing: automate exactly what you did by hand. If it fails: they return to their current way: the pain is too small or the switch too costly.
- Next step: build the smallest tool that replaces your manual work

**Experiment 3 - We believe that businesses will pay for it (or that another payer will).** (H-V1)

- Segment: independent coffee shops in Austin
- Method: Paid pilot offer to 10 independent coffee shops: a 30-day pilot at $39/month, with a signed letter of intent.
- Metric: number of businesses that sign up and pay or sign an LOI; **threshold:** at least 3 of 10 commit at the stated price
- Cost and time: $0-100, 2-3 weeks
- If it passes: a business will pay: confirm price and the buyer's budget owner. If it fails: no commitment: try a lower price, a different buyer, or a different job.
- Next step: convert pilots to paid accounts and measure usage

**Next 30 days:** run Experiment 1 first; start Experiment 2 only if it passes; do not build beyond a clickable prototype or a manual pilot before both pass. Experiment budget: about $600 (solo founder, bootstrapped scenario).

---

**Sources cited** (full evidence log, calculations and validation results are in the appendix)

1. [How do you schedule baristas? : r/barista](https://www.reddit.com/r/barista/comments/a1/schedule) (E3)
2. [Scheduling staff at a small coffee shop - forum](https://forum.coffeeowners.test/t/42) (E1)
3. [ShiftBrew reviews - App Store](https://apps.apple.com/us/app/shiftbrew/id1) (E7)
4. [Austin coffee scene report](https://www.austinchronicle.test/food/coffee-2026) (E5)
5. [Austin Independent Coffee Owners Meetup](https://www.meetup.com/austin-coffee-owners/) (E8)
6. [Building a shift scheduling backend with a calendar API](https://devblog.test/shift-api) (E10)
