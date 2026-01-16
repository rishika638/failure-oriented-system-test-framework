# Failure-Oriented System Test Framework

### Why I built this

Most projects I had done earlier were about making things work in ideal conditions.  
But while reading about real outages and production issues, I noticed that systems usually don’t fail by completely crashing. Instead, they stay “up” but become slow, unstable, or unreliable.

This project started from that curiosity — to understand **what actually happens when systems are stressed**, and how to observe that behavior properly.

---

### What this project is

This is a small system test framework built on Linux that intentionally injects failures into a running service and studies how the system behaves from the **client’s point of view**.

The focus is not on building features, but on:
- breaking assumptions
- measuring impact
- and checking whether the system recovers correctly

Failures are injected at the **operating system and network level**, not simulated inside application code.

---

### Main parts of the project

**1. Target system**

A simple HTTP service with predictable behavior and clean startup/shutdown handling.  
It acts as a controlled system under test so that changes in behavior can be clearly attributed to injected faults.

**2. Traffic generator**

A client-side load generator that sends requests at a fixed rate and measures:
- request latency
- errors
- tail behavior (p50, p95, p99)

One important learning here was that **server logs can be misleading under stress**, while **client-side timestamps reflect what users actually experience**. All latency measurements are therefore taken on the client side.

**3. Failure injection**

Network failures are injected using Linux `tc` and `netem`, allowing latency to be added and removed explicitly.  
This makes the failure realistic and reversible, similar to real production issues.

---

### Experiments performed

- Measured baseline latency under steady load
- Injected network latency and observed degradation
- Identified a real testing mistake where using `localhost` bypassed the injected fault
- Fixed this by routing traffic through the actual network interface (`eth0`)
- Verified that system behavior returned close to baseline after fault removal

---

### Key learnings

- Latency-related failures are subtle because systems remain “up” while performance degrades
- Tail latency degrades much more than median latency under stress
- Fault injection must match the actual traffic path to produce valid results
- Measuring recovery is often more important than observing failure alone

---

### Current state

Implemented:
- Target HTTP service
- Client-side traffic generator
- OS-level latency injection using `netem`
- Recovery validation after fault removal

Planned (future work):
- Packet loss injection
- Process crash and restart scenarios
- Pass/fail assertions
- Scenario-based test definitions

---

### Final note

This project represents a shift in how I think about systems — from making demos work to understanding how systems behave when things go wrong.  
The emphasis is on **observation, reasoning, and recovery**, not on feature count.
