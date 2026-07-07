## Week template — copy me

### Week 4 — 2026-06-29

**Attended this week's meeting:** Yes 

**Progress this week**
##Step 1: Feasibility-First Improvement for E-VRPTW Reproduction
This week’s work continued from last week’s E-VRPTW reproduction experiments. Last week, the basic framework for calling OR-Tools, GA, PyVRP, and POMO was completed, but the results showed low feasibility. Many generated routes could cover customers, but violated time window, battery, or charging constraints.

Therefore, the focus this week shifted from “generating routes using different algorithms” to “generating feasible routes under complex constraints.” A feasibility-first repair mechanism was added, and ALNS was introduced as a new method for handling complex routing constraints.


**Challenges & blockers**
- _What got in the way? What are you stuck on?_

**Next steps**
- _What will you do next week?_

**Hours spent (optional):** _e.g. 6h_

**Links (optional):** _commits, notebooks, docs, datasets..._
