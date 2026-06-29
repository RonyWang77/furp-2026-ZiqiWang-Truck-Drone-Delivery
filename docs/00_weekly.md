# Weekly Progress Log

> Update this file **every week**. Add a new entry at the top for each week.
> This is the first thing we check during review. Keep it honest and specific — it also feeds your attendance record (Rule 1).

**How to use:** copy the *Week template* block below for each new week. Newest week goes at the top.

<!-- =================  YOUR ENTRIES BELOW  ================= -->
## Week template — copy me

### Week N — YYYY-MM-DD

**Attended this week's meeting:** Yes / No (if No, did you email leave? Yes / No)

**Progress this week**
- _What did you actually do / finish?_

**Challenges & blockers**
- _What got in the way? What are you stuck on?_

**Next steps**
- _What will you do next week?_

**Hours spent (optional):** _e.g. 6h_

**Links (optional):** _commits, notebooks, docs, datasets..._

---

### Week 3 — 2026-06-22

**Attended this week's meeting:** Yes 

**Progress this week**
- This week, I studied the official PyVRP tutorial and learned its basic modeling workflow for VRP, CVRP, and VRPTW problems. I also downloaded the official PyVRP repository locally and successfully ran simple examples, preparing it for later use as one of the reproduction methods.
- I successfully configured an independent conda environment for the POMO repository. The official POMO code was downloaded and its existing TSP and CVRP examples were successfully executed locally. During this process, I resolved issues related to Python versions, PyTorch, CUDA compatibility, PowerShell execution policy, and conda environment management.
- I read a classic E-VRPTW paper and studied the additional complexity of electric vehicle routing compared with traditional VRP, including time windows, battery capacity, charging stations, energy consumption, and charging time. Based on this, I built a reproduction module and conducted preliminary experiments using OR-Tools, GA, PyVRP, and POMO.
- Experiments were conducted on Solomon R101, C101, and RC101 instances with different customer sizes, including 10, 25, and 50 customers. The results were evaluated from multiple perspectives, including routes, total distance, runtime, number of vehicles, customer coverage, time-window violation, battery violation, and overall feasibility. Here are the results: <img width="1264" height="498" alt="image" src="https://github.com/user-attachments/assets/fb2ea412-68e8-4a4e-b4f3-e63f1f441d69" />


**Challenges & blockers**
- The main challenge this week was that although OR-Tools, GA, PyVRP, and POMO can all generate routes, their original forms cannot directly solve the full E-VRPTW problem.
- E-VRPTW is not only a standard VRP or VRPTW. It also requires considering time windows, battery consumption, charging station visits, charging time, and customer coverage at the same time. Without precise problem modeling and constraint-specific algorithm optimization, it is difficult to obtain feasible routes satisfying all these requirements.

**Next steps**
- Next week, I plan to further study the mathematical modeling of E-VRPTW and translate the constraints in the paper into more accurate executable models. The focus will include charging station insertion, battery state updates, time-window handling, and unified feasibility evaluation.
- At the same time, I will continue improving the adapters for OR-Tools, GA, and PyVRP so that they can better handle electric vehicle routing problems with special constraints. POMO will remain a reference learning-based method, and I will further explore whether it can be extended to E-VRPTW. I will also continue reading and reproducing other related papers.

**Hours spent (optional):** 

**Links (optional):** 
- PyVRP Official Documentation
- POMO Official Repository
- Schneider, M., Stenger, A., & Goeke, D. (2014). The Electric Vehicle-Routing Problem with Time Windows and Recharging Stations.

---


### Week 2 — 2026-06-15

**Attended this week's meeting:** Yes 

**Progress this week**
- Downloaded and configured the open-source project py-ga-VRPTW to build the experimental environment for solving VRPTW problems using Genetic Algorithm (GA).

- Installed the core module gavrptw.core into the Python virtual environment as a local editable package, enabling direct import and further algorithm development.

- Downloaded and organized the Solomon VRPTW Benchmark dataset locally.

- Established the Solomon dataset as a shared benchmark data source for future experiments with GA, OR-Tools, and other VRP optimization algorithms.

- Studied the Electric truck-based robot delivery problem with nonlinear charging (ETRD-NL).
Understood the collaborative delivery mechanism between electric trucks and delivery robots.
Learned the influence of battery constraints, charging strategies, and nonlinear charging processes on routing optimization problems.

- Small-scale implementation of ETRD-NL algorithms (Dataset: Solomon R101, 
Customers: 8, Charging stations: 4). Implemented three solution approaches: truck_only_tsp,ortools and GA. Implemented four charging strategies:
LFC (Linear Full Charging),
LPC (Linear Partial Charging),
NFC (Nonlinear Full Charging) and
NPC (Nonlinear Partial Charging)

- ortools result: <img width="674" height="247" alt="image" src="https://github.com/user-attachments/assets/750c13f6-0942-43b7-b521-59552c410d99" />
 
- GA result: <img width="687" height="266" alt="image" src="https://github.com/user-attachments/assets/ca3987f8-6185-4efc-9e3f-e61c49504505" />

- Experiment summary: <img width="686" height="629" alt="image" src="https://github.com/user-attachments/assets/7c1965e3-453e-4687-bb67-8ce4a41be205" />



**Challenges & blockers**
- Small instances can verify algorithm correctness, but larger experiments are required to evaluate performance and scalability.
- The current GA framework mainly focuses on standard VRP/VRPTW problems and is limited under E condition

**Next steps**
- Continue studying additional optimization algorithms for VRP problems and compare their advantages and limitations in VRP/VRPTW applications

**Hours spent (optional):** 

**Links (optional):** open-source project py-ga-VRPTW, Electric truck-based robot delivery problem with nonlinear charging

---


### Week 1 — 2026-06-08

**Attended this week's meeting:** Yes 

**Progress this week**
- Set up repository from the FURP template.
- Created a virtual environment in VS Code and installed OR-Tools.
- Understood the core concepts (solver, variables, constraints, objective function) and the role of the routing model.
- Ran four official examples and understood their logic
  1.Linear programming example (GLOP)
  2.First TSP example (pre‑defined distance matrix)
  3.Second TSP example (Euclidean distance from coordinates)
  4.Basic VRP example (multiple vehicles, distance dimension & global span cost coefficient)
  All examples executed correctly and produced expected outputs.

**Challenges & blockers**
- I understand that the overall task is to reproduce results from published VRP papers (likely          involving truck‑drone coordinated delivery). However, I am still unsure this understanding is         correct or not. I am also unsure how to integrate the learned OR‑Tools techniques into a complete     research pipeline.

**Next steps**
- Continue studying more complex VRP variants (e.g., with time windows, capacity constraints, or        pickup & delivery) using OR‑Tools.

**Hours spent (optional):**

**Links (optional):Google official OR-Tools guidance
