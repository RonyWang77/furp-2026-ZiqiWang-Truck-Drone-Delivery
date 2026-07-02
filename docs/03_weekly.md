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
