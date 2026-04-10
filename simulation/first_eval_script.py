import os
import sys
from typing import Dict, List, Tuple

import numpy as np
import torch
import traci

from model import DQN

# =========================
# SUMO Setup
# =========================
if "SUMO_HOME" not in os.environ:
    raise EnvironmentError("SUMO_HOME is not set.")

SUMO_TOOLS = os.path.join(os.environ["SUMO_HOME"], "tools")
if SUMO_TOOLS not in sys.path:
    sys.path.append(SUMO_TOOLS)

SUMO_BINARY = "sumo"   # headless for fast evaluation
SUMO_CFG = "marl_sim.sumocfg"
MAX_STEPS = 3600
MIN_GREEN = 8
YELLOW_TIME = 3
DECISION_INTERVAL = 5

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# =========================
# Evaluation Config
# =========================
N_EVAL_RUNS = 5

INDEP_DIR = "checkpoints_marl_v2"
COOP_DIR = "checkpoints_coop_marl_v2"
QMIX_DIR = "checkpoints_qmix"  


# =========================
# Fixed Timer Injector
# =========================
def create_zimbabwe_program(tl_id: str):
    logics = traci.trafficlight.getAllProgramLogics(tl_id)
    current_logic = logics[0]

    ns_green_state = current_logic.phases[0].state
    ew_green_state = current_logic.phases[2].state

    def make_yellow(state: str) -> str:
        return state.replace("G", "y").replace("g", "y")

    def make_red(state: str) -> str:
        return "r" * len(state)

    phases = [
        traci.trafficlight.Phase(22, ns_green_state),
        traci.trafficlight.Phase(3, make_yellow(ns_green_state)),
        traci.trafficlight.Phase(1, make_red(ns_green_state)),
        traci.trafficlight.Phase(22, ew_green_state),
        traci.trafficlight.Phase(3, make_yellow(ew_green_state)),
        traci.trafficlight.Phase(1, make_red(ew_green_state)),
    ]

    new_logic = traci.trafficlight.Logic("custom_zim", 0, 0, phases)
    traci.trafficlight.setCompleteRedYellowGreenDefinition(tl_id, new_logic)


# =========================
# SUMO helpers
# =========================
def start_sumo():
    traci.start([SUMO_BINARY, "-c", SUMO_CFG, "--no-step-log", "true", "--quit-on-end", "true"])


def discover_main_tls_ids() -> List[str]:
    ids = []
    for tls_id in traci.trafficlight.getIDList():
        lanes = []
        for lane in traci.trafficlight.getControlledLanes(tls_id):
            if lane and not lane.startswith(":") and lane not in lanes:
                lanes.append(lane)
        if len(lanes) >= 4:
            ids.append(tls_id)
    return sorted(ids)


# =========================
# Universal Evaluation Controller
# =========================
class EvalController:
    def __init__(self, tls_id: str, initialize_signals: bool = True):
        self.tls_id = tls_id
        self.junction_pos = traci.junction.getPosition(tls_id)
        self.approaches = self._group_incoming_lanes()
        self.green_states, self.yellow_states = self._extract_safe_states()

        self.current_phase = 0
        self.pending_phase = None
        self.yellow_timer = 0
        self.green_timer = 0

        if initialize_signals:
            self.set_green(0)

    def _non_internal_lanes(self):
        lanes = []
        for lane in traci.trafficlight.getControlledLanes(self.tls_id):
            if lane and not lane.startswith(":") and lane not in lanes:
                lanes.append(lane)
        return lanes

    def _lane_direction(self, lane_id):
        shape = traci.lane.getShape(lane_id)
        end_x, end_y = shape[-1]
        jx, jy = self.junction_pos
        dx, dy = end_x - jx, end_y - jy
        if abs(dx) > abs(dy):
            return "east" if dx > 0 else "west"
        return "north" if dy > 0 else "south"

    def _group_incoming_lanes(self):
        groups = {"north": [], "south": [], "east": [], "west": []}
        for lane in self._non_internal_lanes():
            groups[self._lane_direction(lane)].append(lane)
        return groups

    def _extract_safe_states(self):
        logic = traci.trafficlight.getAllProgramLogics(self.tls_id)[0]
        phases = logic.phases
        links = traci.trafficlight.getControlledLinks(self.tls_id)
        candidates = []

        for idx, phase in enumerate(phases):
            state = phase.state
            if "y" in state.lower():
                continue
            if state.count("G") + state.count("g") == 0:
                continue

            ns_score, ew_score = 0, 0
            for link_idx, char in enumerate(state):
                if char not in ("G", "g"):
                    continue
                if link_idx >= len(links) or not links[link_idx]:
                    continue
                first_link = links[link_idx][0]
                if not first_link or not first_link[0] or first_link[0].startswith(":"):
                    continue
                d = self._lane_direction(first_link[0])
                if d in ("north", "south"):
                    ns_score += 1
                else:
                    ew_score += 1

            candidates.append(
                {"idx": idx, "state": state, "ns_score": ns_score, "ew_score": ew_score}
            )

        if len(candidates) < 2:
            raise RuntimeError(f"Could not find two green phases for {self.tls_id}")

        ns_phase = sorted(
            candidates, key=lambda x: x["ns_score"] - x["ew_score"], reverse=True
        )[0]
        ew_candidates = [c for c in candidates if c["idx"] != ns_phase["idx"]]
        ew_phase = sorted(
            ew_candidates, key=lambda x: x["ew_score"] - x["ns_score"], reverse=True
        )[0]

        def next_yellow(phase_idx):
            nxt = phases[(phase_idx + 1) % len(phases)].state
            return nxt if "y" in nxt.lower() else phases[phase_idx].state

        return (
            [ns_phase["state"], ew_phase["state"]],
            [next_yellow(ns_phase["idx"]), next_yellow(ew_phase["idx"])],
        )

    def set_green(self, phase_idx: int):
        traci.trafficlight.setRedYellowGreenState(self.tls_id, self.green_states[phase_idx])
        self.current_phase = phase_idx
        self.pending_phase = None
        self.yellow_timer = 0
        self.green_timer = 0

    def request_absolute_action(self, action: int):
        """For independent and cooperative v2: action is absolute phase index."""
        if self.yellow_timer > 0:
            return
        if action == self.current_phase:
            return
        if self.green_timer < MIN_GREEN:
            return

        traci.trafficlight.setRedYellowGreenState(self.tls_id, self.yellow_states[self.current_phase])
        self.pending_phase = action
        self.yellow_timer = YELLOW_TIME

    def request_semantic_action(self, action: int):
        """For QMIX final: 0 = keep, 1 = switch."""
        if self.yellow_timer > 0:
            return
        if action == 0:
            return
        if self.green_timer < MIN_GREEN:
            return

        self.pending_phase = 1 - self.current_phase
        traci.trafficlight.setRedYellowGreenState(self.tls_id, self.yellow_states[self.current_phase])
        self.yellow_timer = YELLOW_TIME

    def step_signal(self):
        if self.yellow_timer > 0:
            self.yellow_timer -= 1
            if self.yellow_timer == 0 and self.pending_phase is not None:
                self.set_green(self.pending_phase)
        else:
            self.green_timer += 1

    def _queue(self, lanes):
        return sum(traci.lane.getLastStepHaltingNumber(l) for l in lanes)

    def _waiting_sum(self, lanes):
        return sum(traci.lane.getWaitingTime(l) for l in lanes)

    def _waiting_mean(self, lanes):
        vids = [vid for lane in lanes for vid in traci.lane.getLastStepVehicleIDs(lane)]
        if not vids:
            return 0.0
        return float(np.mean([traci.vehicle.getWaitingTime(vid) for vid in vids]))

    def get_state_v2(self):
        return np.array([
            self._queue(self.approaches["north"]) / 20.0,
            self._queue(self.approaches["south"]) / 20.0,
            self._queue(self.approaches["east"]) / 20.0,
            self._queue(self.approaches["west"]) / 20.0,
            self._waiting_sum(self.approaches["north"]) / 100.0,
            self._waiting_sum(self.approaches["south"]) / 100.0,
            self._waiting_sum(self.approaches["east"]) / 100.0,
            self._waiting_sum(self.approaches["west"]) / 100.0,
            float(self.current_phase),
        ], dtype=np.float32)

    def get_state_qmix(self):
        return np.array([
            self._queue(self.approaches["north"]) / 20.0,
            self._queue(self.approaches["south"]) / 20.0,
            self._queue(self.approaches["east"]) / 20.0,
            self._queue(self.approaches["west"]) / 20.0,
            self._waiting_mean(self.approaches["north"]) / 60.0,
            self._waiting_mean(self.approaches["south"]) / 60.0,
            self._waiting_mean(self.approaches["east"]) / 60.0,
            self._waiting_mean(self.approaches["west"]) / 60.0,
            float(self.current_phase),
        ], dtype=np.float32)

    def controlled_main_lanes(self):
        return [lane for approaches in self.approaches.values() for lane in approaches]


# =========================
# Model loading
# =========================
def load_agent(model_dir: str, tls_id: str, state_dim: int) -> DQN:
    net = DQN(state_dim, 2).to(device)
    path = os.path.join(model_dir, f"{tls_id}_best.pth")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing checkpoint: {path}")
    net.load_state_dict(torch.load(path, map_location=device))
    net.eval()
    return net


# =========================
# Single evaluation run
# =========================
def evaluate_once(mode: str) -> Dict[str, float]:
    start_sumo()

    tls_ids = discover_main_tls_ids()

    if mode == "fixed":
        for tls_id in tls_ids:
            create_zimbabwe_program(tls_id)
        controllers = []
    else:
        controllers = [EvalController(tls_id, initialize_signals=True) for tls_id in tls_ids]

    metric_lanes = []
    if mode == "fixed":
        # Build metric lanes directly from traffic lights
        for tls_id in tls_ids:
            lanes = []
            for lane in traci.trafficlight.getControlledLanes(tls_id):
                if lane and not lane.startswith(":") and lane not in lanes:
                    lanes.append(lane)
            metric_lanes.extend(lanes)
    else:
        for ctrl in controllers:
            metric_lanes.extend(ctrl.controlled_main_lanes())

    agents = {}
    if mode == "indep":
        agents = {tid: load_agent(INDEP_DIR, tid, state_dim=9) for tid in tls_ids}
    elif mode == "coop":
        agents = {tid: load_agent(COOP_DIR, tid, state_dim=18) for tid in tls_ids}
    elif mode == "qmix":
        agents = {tid: load_agent(QMIX_DIR, tid, state_dim=9) for tid in tls_ids}

    lane_sum_wait_total = 0.0
    queue_total = 0.0
    throughput = 0
    steps_done = 0

    with torch.no_grad():
        for step in range(MAX_STEPS):
            traci.simulationStep()
            steps_done = step + 1

            if mode != "fixed":
                for ctrl in controllers:
                    ctrl.step_signal()

            if mode != "fixed" and step % DECISION_INTERVAL == 0:
                if mode == "indep":
                    for ctrl in controllers:
                        state_t = torch.tensor(
                            ctrl.get_state_v2(), dtype=torch.float32, device=device
                        ).unsqueeze(0)
                        action = int(torch.argmax(agents[ctrl.tls_id](state_t), dim=1).item())
                        ctrl.request_absolute_action(action)

                elif mode == "coop":
                    local_states = {ctrl.tls_id: ctrl.get_state_v2() for ctrl in controllers}
                    for i, ctrl in enumerate(controllers):
                        neighbor_id = tls_ids[(i + 1) % len(tls_ids)]
                        coop_state = np.concatenate(
                            (local_states[ctrl.tls_id], local_states[neighbor_id])
                        )
                        state_t = torch.tensor(
                            coop_state, dtype=torch.float32, device=device
                        ).unsqueeze(0)
                        action = int(torch.argmax(agents[ctrl.tls_id](state_t), dim=1).item())
                        ctrl.request_absolute_action(action)

                elif mode == "qmix":
                    for ctrl in controllers:
                        state_t = torch.tensor(
                            ctrl.get_state_qmix(), dtype=torch.float32, device=device
                        ).unsqueeze(0)
                        action = int(torch.argmax(agents[ctrl.tls_id](state_t), dim=1).item())
                        ctrl.request_semantic_action(action)

            lane_sum_wait_total += sum(traci.lane.getWaitingTime(lane) for lane in metric_lanes)
            queue_total += sum(traci.lane.getLastStepHaltingNumber(lane) for lane in metric_lanes)
            throughput += traci.simulation.getArrivedNumber()

            if traci.simulation.getMinExpectedNumber() == 0 and step > 300:
                break

    traci.close()

    return {
        "avg_wait_per_step": lane_sum_wait_total / max(1, steps_done),
        "avg_queue_per_step": queue_total / max(1, steps_done),
        "throughput": float(throughput),
        "steps_done": float(steps_done),
    }


# =========================
# Multi-run evaluator
# =========================
def evaluate_mode(mode: str, n_runs: int = N_EVAL_RUNS) -> Dict[str, float]:
    waits = []
    queues = []
    throughputs = []

    for run_idx in range(1, n_runs + 1):
        print(f"  Run {run_idx}/{n_runs}...")
        metrics = evaluate_once(mode)
        waits.append(metrics["avg_wait_per_step"])
        queues.append(metrics["avg_queue_per_step"])
        throughputs.append(metrics["throughput"])

    return {
        "wait_mean": float(np.mean(waits)),
        "wait_std": float(np.std(waits)),
        "queue_mean": float(np.mean(queues)),
        "queue_std": float(np.std(queues)),
        "throughput_mean": float(np.mean(throughputs)),
        "throughput_std": float(np.std(throughputs)),
    }


# =========================
# Report helpers
# =========================
def print_report_row(name: str, metrics: Dict[str, float]):
    print(
        f"| {name:<27} | "
        f"{metrics['wait_mean']:>9.2f} ± {metrics['wait_std']:<8.2f} | "
        f"{metrics['queue_mean']:>9.2f} ± {metrics['queue_std']:<8.2f} | "
        f"{metrics['throughput_mean']:>9.2f} ± {metrics['throughput_std']:<8.2f} |"
    )


# =========================
# Main
# =========================
if __name__ == "__main__":
    print("=" * 86)
    print(" FINAL DISSERTATION COMPARISON (Multi-Run Deterministic Evaluation) ")
    print("=" * 86)

    print("\nRunning Fixed Timer baseline...")
    fixed_metrics = evaluate_mode("fixed")

    print("\nRunning Independent MARL v2...")
    indep_metrics = evaluate_mode("indep")

    print("\nRunning Cooperative MARL v2...")
    coop_metrics = evaluate_mode("coop")

    print("\nRunning QMIX...")
    qmix_metrics = evaluate_mode("qmix")

    print("\n" + "=" * 122)
    print("| Model Architecture           | Avg Wait / Step (s)      | Avg Queue / Step         | Throughput             |")
    print("|" + "-" * 120 + "|")
    print_report_row("1. Fixed Timer (Baseline)", fixed_metrics)
    print_report_row("2. Independent MARL v2", indep_metrics)
    print_report_row("3. Cooperative MARL v2", coop_metrics)
    print_report_row("4. QMIX (CTDE)", qmix_metrics)
    print("=" * 122)

    print("\nUse these mean ± std results in the dissertation, not single-run values.")