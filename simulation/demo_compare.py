"""
demo_compare.py — Supervisor Demo: Fixed-Time vs Cooperative MARL

Runs two back-to-back SUMO-GUI simulations so the lecturers can watch:
  1. The fixed-time (Zimbabwe 22s-3s-1s cycle) controller
  2. The trained Cooperative MARL v2 controller

Live stats are printed to the console every PRINT_EVERY steps so you can
narrate what is happening while the simulation plays.  A final comparison
table is printed at the end.

Usage:
    python demo_compare.py
"""

import os
import sys
import time
import random

import numpy as np
import torch
import traci

# ── SUMO path setup ────────────────────────────────────────────────────────────
if "SUMO_HOME" not in os.environ:
    sys.exit("❌  SUMO_HOME is not set.  Add it to your environment variables.")

SUMO_TOOLS = os.path.join(os.environ["SUMO_HOME"], "tools")
if SUMO_TOOLS not in sys.path:
    sys.path.append(SUMO_TOOLS)

# ── Local imports ──────────────────────────────────────────────────────────────
from model import DQN
from main_coop_marl_v2 import (
    IntersectionController,
    build_coop_states,
    LOCAL_STATE_DIM,
    ACTION_DIM,
    DECISION_INTERVAL,
    MIN_GREEN,
    YELLOW_TIME,
)

# ==============================================================================
# DEMO CONFIGURATION — edit these if needed
# ==============================================================================
SUMO_CFG        = "demo_sim.sumocfg"   # separate config, not the training one
CHECKPOINT_DIR  = "D:/ZIM_ITMS/simulation/checkpoints_coop_marl_v2"  # where your trained checkpoints are saved

# How many simulated steps to run per demo (1200 = 20 simulated minutes)
DEMO_STEPS      = 1200

# Print live stats to console every N steps
PRINT_EVERY     = 100

# Fixed-time phase durations (seconds) — must match your fixed_timer script
NS_GREEN_TIME   = 22
EW_GREEN_TIME   = 22
YELLOW_TIME_FT  = 3
ALL_RED_TIME    = 1

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ==============================================================================
# HELPERS — shared between both runs
# ==============================================================================
def banner(title: str, width: int = 60):
    """Print a clearly visible section banner."""
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def start_sumo():
    """Launch SUMO-GUI with the demo config."""
    traci.start([
        "sumo-gui",
        "-c", SUMO_CFG,
        "--no-step-log", "true",
        "--quit-on-end",  "true",
    ])


def discover_main_tls_ids():
    """Return sorted list of traffic light IDs that control ≥4 lanes."""
    ids = []
    for tls_id in traci.trafficlight.getIDList():
        lanes = [
            l for l in traci.trafficlight.getControlledLanes(tls_id)
            if l and not l.startswith(":")
        ]
        if len(set(lanes)) >= 4:
            ids.append(tls_id)
    return sorted(ids)


def collect_all_lanes(tls_ids):
    """Collect all non-internal lanes controlled by the given intersections."""
    lanes = []
    for tls_id in tls_ids:
        for lane in traci.trafficlight.getControlledLanes(tls_id):
            if lane and not lane.startswith(":") and lane not in lanes:
                lanes.append(lane)
    return lanes


def live_stats_header():
    print(f"\n{'Step':>6}  {'Avg Wait/s':>10}  {'Queued':>8}  {'Arrived':>9}")
    print("-" * 40)


def print_live_stats(step, total_wait, total_queue, total_arrived, steps_so_far):
    s = max(1, steps_so_far)
    print(
        f"{step:>6}  "
        f"{total_wait / s:>10.2f}  "
        f"{total_queue / s:>8.2f}  "
        f"{total_arrived:>9}"
    )


# ==============================================================================
# RUN 1 — FIXED-TIME (Zimbabwe 22-3-1 cycle)
# ==============================================================================
def inject_fixed_time_program(tls_id):
    """
    Replace SUMO's default program with a Zimbabwean 22s NS / 22s EW cycle
    identical to the fixed_timer.py baseline.
    """
    logics        = traci.trafficlight.getAllProgramLogics(tls_id)
    current_logic = logics[0]
    ns_green      = current_logic.phases[0].state
    ew_green      = current_logic.phases[2].state

    def yellow(state):
        return state.replace("G", "y").replace("g", "y")

    def all_red(state):
        return "r" * len(state)

    phases = [
        traci.trafficlight.Phase(NS_GREEN_TIME,  ns_green),
        traci.trafficlight.Phase(YELLOW_TIME_FT, yellow(ns_green)),
        traci.trafficlight.Phase(ALL_RED_TIME,   all_red(ns_green)),
        traci.trafficlight.Phase(EW_GREEN_TIME,  ew_green),
        traci.trafficlight.Phase(YELLOW_TIME_FT, yellow(ew_green)),
        traci.trafficlight.Phase(ALL_RED_TIME,   all_red(ew_green)),
    ]
    new_logic = traci.trafficlight.Logic("demo_fixed", 0, 0, phases)
    traci.trafficlight.setCompleteRedYellowGreenDefinition(tls_id, new_logic)
    print(f"  ✅  Fixed-time program injected into {tls_id}")


def run_fixed_time() -> dict:
    banner("RUN 1 of 2 — FIXED-TIME CONTROLLER (22s / 22s cycle)")
    print(
        "  Watch the traffic lights cycle at fixed intervals regardless\n"
        "  of how many vehicles are waiting in each direction.\n"
    )

    start_sumo()

    tls_ids = discover_main_tls_ids()
    print(f"  Intersections detected: {tls_ids}")

    for tls_id in tls_ids:
        inject_fixed_time_program(tls_id)

    all_lanes = collect_all_lanes(tls_ids)

    total_wait    = 0.0
    total_queue   = 0.0
    total_arrived = 0

    live_stats_header()

    for step in range(DEMO_STEPS):
        traci.simulationStep()

        step_wait  = sum(traci.lane.getWaitingTime(l)           for l in all_lanes)
        step_queue = sum(traci.lane.getLastStepHaltingNumber(l) for l in all_lanes)
        arrived    = traci.simulation.getArrivedNumber()

        total_wait    += step_wait
        total_queue   += step_queue
        total_arrived += arrived

        if (step + 1) % PRINT_EVERY == 0:
            print_live_stats(step + 1, total_wait, total_queue, total_arrived, step + 1)

        if traci.simulation.getMinExpectedNumber() == 0 and step > 300:
            print(f"  ℹ️  All vehicles cleared at step {step + 1}.")
            break

    traci.close()
    steps_done = max(1, step + 1)

    return {
        "avg_wait_per_step":  total_wait  / steps_done,
        "avg_queue_per_step": total_queue / steps_done,
        "throughput":         total_arrived,
        "steps":              steps_done,
    }


# ==============================================================================
# RUN 2 — TRAINED COOPERATIVE MARL v2
# ==============================================================================
def load_marl_agents(tls_ids: list) -> dict:
    """
    Load saved DQN weights for each intersection.
    Checkpoint filenames: {tls_id}_best.pth  (e.g. A0_best.pth, B0_best.pth)
    """
    state_dim = 2 * LOCAL_STATE_DIM   # local state + neighbour state
    agents    = {}

    for tls_id in tls_ids:
        net = DQN(state_dim, ACTION_DIM).to(device)
        # Put network in eval mode — no dropout, no batch-norm running-mean update
        net.eval()

        ckpt_path = os.path.join(CHECKPOINT_DIR, f"{tls_id}_best.pth")
        if not os.path.exists(ckpt_path):
            raise FileNotFoundError(
                f"Checkpoint not found: {ckpt_path}\n"
                f"Expected files: A0_best.pth, B0_best.pth in '{CHECKPOINT_DIR}'"
            )

        net.load_state_dict(torch.load(ckpt_path, map_location=device))
        agents[tls_id] = net
        print(f"  ✅  Loaded checkpoint: {ckpt_path}")

    return agents


def select_action(net, state: np.ndarray) -> int:
    """Greedy action selection — no exploration during demo."""
    with torch.no_grad():
        t = torch.tensor(state, dtype=torch.float32, device=device).unsqueeze(0)
        return int(torch.argmax(net(t), dim=1).item())


def run_marl() -> dict:
    banner("RUN 2 of 2 — COOPERATIVE MARL v2 (TRAINED)")
    print(
        "  Now watch the same intersection network controlled by the\n"
        "  trained MARL agents.  Each agent sees its own queue/wait\n"
        "  state AND its neighbour's state, then decides when to switch\n"
        "  the phase to minimise the global congestion.\n"
    )

    start_sumo()

    tls_ids = discover_main_tls_ids()
    print(f"  Intersections detected: {tls_ids}")

    agents      = load_marl_agents(tls_ids)
    controllers = {
        tls_id: IntersectionController(tls_id, initialize_signals=True)
        for tls_id in tls_ids
    }

    all_lanes = []
    for ctrl in controllers.values():
        all_lanes.extend(ctrl.controlled_main_lanes())

    total_wait    = 0.0
    total_queue   = 0.0
    total_arrived = 0

    live_stats_header()

    for step in range(DEMO_STEPS):
        traci.simulationStep()

        # Advance yellow-phase timers every step
        for ctrl in controllers.values():
            ctrl.step_signal()

        # Agent decisions every DECISION_INTERVAL steps
        if step % DECISION_INTERVAL == 0:
            local_states = {
                tls_id: ctrl.get_local_state()
                for tls_id, ctrl in controllers.items()
            }
            coop_states = build_coop_states(tls_ids, local_states)

            for tls_id, ctrl in controllers.items():
                state  = coop_states[tls_id]
                action = select_action(agents[tls_id], state)
                ctrl.request_action(action)
                ctrl.last_action = action

        step_wait  = sum(traci.lane.getWaitingTime(l)           for l in all_lanes)
        step_queue = sum(traci.lane.getLastStepHaltingNumber(l) for l in all_lanes)
        arrived    = traci.simulation.getArrivedNumber()

        total_wait    += step_wait
        total_queue   += step_queue
        total_arrived += arrived

        if (step + 1) % PRINT_EVERY == 0:
            print_live_stats(step + 1, total_wait, total_queue, total_arrived, step + 1)

        if traci.simulation.getMinExpectedNumber() == 0 and step > 300:
            print(f"  ℹ️  All vehicles cleared at step {step + 1}.")
            break

    traci.close()
    steps_done = max(1, step + 1)

    return {
        "avg_wait_per_step":  total_wait  / steps_done,
        "avg_queue_per_step": total_queue / steps_done,
        "throughput":         total_arrived,
        "steps":              steps_done,
    }


# ==============================================================================
# FINAL COMPARISON TABLE
# ==============================================================================
def print_comparison(fixed: dict, marl: dict):
    banner("RESULTS — Fixed-Time vs Cooperative MARL v2")

    def pct(baseline, improved):
        if baseline < 1e-9:
            return 0.0
        return (baseline - improved) / baseline * 100

    wait_imp  = pct(fixed["avg_wait_per_step"],  marl["avg_wait_per_step"])
    queue_imp = pct(fixed["avg_queue_per_step"], marl["avg_queue_per_step"])
    thru_gain = marl["throughput"] - fixed["throughput"]

    col = 24
    w   = 52

    print(f"\n  {'Metric':<{col}}  {'Fixed-Time':>10}  {'MARL v2':>10}  {'Improvement':>12}")
    print("  " + "-" * (w - 2))
    print(f"  {'Avg wait / step (s)':<{col}}  {fixed['avg_wait_per_step']:>10.2f}  {marl['avg_wait_per_step']:>10.2f}  {wait_imp:>+11.1f}%")
    print(f"  {'Avg queue / step (veh)':<{col}}  {fixed['avg_queue_per_step']:>10.2f}  {marl['avg_queue_per_step']:>10.2f}  {queue_imp:>+11.1f}%")
    print(f"  {'Total throughput (veh)':<{col}}  {fixed['throughput']:>10}  {marl['throughput']:>10}  {thru_gain:>+11}")
    print(f"  {'Steps completed':<{col}}  {fixed['steps']:>10}  {marl['steps']:>10}")
    print("  " + "-" * (w - 2))

    print("\n  SUMMARY")
    if wait_imp > 0:
        print(f"  ✅  MARL reduced average waiting time by {wait_imp:.1f}%")
    else:
        print(f"  ⚠️  MARL increased waiting time by {abs(wait_imp):.1f}%  (check checkpoints)")

    if queue_imp > 0:
        print(f"  ✅  MARL reduced average queue length by {queue_imp:.1f}%")

    if thru_gain > 0:
        print(f"  ✅  MARL moved {thru_gain} more vehicles through the network")
    elif thru_gain == 0:
        print(f"  ➡️   Throughput unchanged (both cleared the same number of vehicles)")
    else:
        print(f"  ⚠️  MARL moved {abs(thru_gain)} fewer vehicles (check route demand)")

    print()


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def main():
    banner("SUPERVISOR DEMO — Cooperative MARL Traffic Optimisation", width=60)
    print(
        "\n  This demo runs two back-to-back SUMO-GUI simulations:\n"
        "\n"
        "  1. Fixed-time controller  — standard 22s/22s cycle\n"
        "  2. Cooperative MARL v2   — trained DQN agents\n"
        "\n"
        "  Watch the SUMO-GUI window.  Live stats will print here\n"
        f"  every {PRINT_EVERY} steps.  Close the GUI window to end each run.\n"
    )

    # ── Fixed-time run ─────────────────────────────────────────────────────────
    input("  👉  Press ENTER to start the FIXED-TIME run...")
    fixed_results = run_fixed_time()

    # ── Pause for explanation ──────────────────────────────────────────────────
    banner("PAUSE — Fixed-Time run complete")
    print(
        f"  Avg wait/step : {fixed_results['avg_wait_per_step']:.2f} s\n"
        f"  Avg queue/step: {fixed_results['avg_queue_per_step']:.2f} vehicles\n"
        f"  Throughput    : {fixed_results['throughput']} vehicles\n"
        "\n"
        "  Note how the traffic lights switched at fixed intervals even\n"
        "  when one direction had no vehicles waiting.  This causes\n"
        "  unnecessary delay and queue build-up on the busier approaches.\n"
    )
    input("  👉  Press ENTER when you are ready to start the MARL run...")

    # ── MARL run ───────────────────────────────────────────────────────────────
    marl_results = run_marl()

    # ── Final comparison ───────────────────────────────────────────────────────
    print_comparison(fixed_results, marl_results)


if __name__ == "__main__":
    main()
