import os
import sys
import random
from collections import deque

import numpy as np
import torch
import torch.nn.functional as F
import traci

from model import DQN

# =========================
# SUMO setup
# =========================
if "SUMO_HOME" not in os.environ:
    raise EnvironmentError("SUMO_HOME is not set. Add SUMO_HOME to your environment variables.")

SUMO_TOOLS = os.path.join(os.environ["SUMO_HOME"], "tools")
if SUMO_TOOLS not in sys.path:
    sys.path.append(SUMO_TOOLS)

USE_GUI = False
SUMO_BINARY = "sumo-gui" if USE_GUI else "sumo"
SUMO_CFG = "marl_sim.sumocfg"

# =========================
# Training config
# =========================
SEED = 42
MAX_EPISODES = 200
MAX_STEPS = 3600

STATE_DIM = 9
ACTION_DIM = 2

GAMMA = 0.99
LR = 1e-3
BATCH_SIZE = 64
BUFFER_SIZE = 50000
TARGET_UPDATE_EVERY = 10

EPSILON_START = 1.0
EPSILON_END = 0.05
EPSILON_DECAY = 0.995

DECISION_INTERVAL = 5   # seconds between decisions
MIN_GREEN = 8           # minimum green hold before switching
YELLOW_TIME = 3         # yellow transition duration

MODEL_DIR = "checkpoints_marl"
os.makedirs(MODEL_DIR, exist_ok=True)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

# =========================
# Replay Buffer
# =========================
class ReplayBuffer:
    def __init__(self, capacity):
        self.buffer = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, done):
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size):
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            np.array(states, dtype=np.float32),
            np.array(actions, dtype=np.int64),
            np.array(rewards, dtype=np.float32),
            np.array(next_states, dtype=np.float32),
            np.array(dones, dtype=np.float32),
        )

    def __len__(self):
        return len(self.buffer)

# =========================
# DQN Agent
# =========================
class DQNAgent:
    def __init__(self, name):
        self.name = name
        self.policy_net = DQN(STATE_DIM, ACTION_DIM).to(device)
        self.target_net = DQN(STATE_DIM, ACTION_DIM).to(device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        self.optimizer = torch.optim.Adam(self.policy_net.parameters(), lr=LR)
        self.memory = ReplayBuffer(BUFFER_SIZE)

        self.epsilon = EPSILON_START

    def select_action(self, state, explore=True):
        if explore and random.random() < self.epsilon:
            return random.randrange(ACTION_DIM)

        state_tensor = torch.tensor(state, dtype=torch.float32, device=device).unsqueeze(0)

        # Important because your DQN uses BatchNorm1d
        self.policy_net.eval()
        with torch.no_grad():
            q_values = self.policy_net(state_tensor)
            action = int(torch.argmax(q_values, dim=1).item())
        self.policy_net.train()

        return action

    def store(self, state, action, reward, next_state, done):
        self.memory.push(state, action, reward, next_state, done)

    def train_step(self):
        if len(self.memory) < BATCH_SIZE:
            return None

        states, actions, rewards, next_states, dones = self.memory.sample(BATCH_SIZE)

        states = torch.tensor(states, dtype=torch.float32, device=device)
        actions = torch.tensor(actions, dtype=torch.int64, device=device).unsqueeze(1)
        rewards = torch.tensor(rewards, dtype=torch.float32, device=device)
        next_states = torch.tensor(next_states, dtype=torch.float32, device=device)
        dones = torch.tensor(dones, dtype=torch.float32, device=device)

        q_values = self.policy_net(states).gather(1, actions).squeeze(1)

        with torch.no_grad():
            next_q_values = self.target_net(next_states).max(1)[0]
            targets = rewards + GAMMA * next_q_values * (1.0 - dones)

        loss = F.smooth_l1_loss(q_values, targets)

        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), max_norm=5.0)
        self.optimizer.step()

        return loss.item()

    def update_target(self):
        self.target_net.load_state_dict(self.policy_net.state_dict())

    def decay_epsilon(self):
        self.epsilon = max(EPSILON_END, self.epsilon * EPSILON_DECAY)

    def save(self):
        torch.save(self.policy_net.state_dict(), os.path.join(MODEL_DIR, f"{self.name}.pth"))

    def load(self):
        path = os.path.join(MODEL_DIR, f"{self.name}.pth")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model not found for {self.name}: {path}")
        self.policy_net.load_state_dict(torch.load(path, map_location=device))
        self.target_net.load_state_dict(self.policy_net.state_dict())

# =========================
# Intersection Controller
# =========================
class IntersectionController:
    def __init__(self, tls_id, initialize_signals=True):
        self.tls_id = tls_id
        self.junction_pos = traci.junction.getPosition(tls_id)

        self.approaches = self._group_incoming_lanes()
        self.green_states, self.yellow_states = self._extract_safe_states()

        self.current_action = 0
        self.pending_action = None
        self.yellow_timer = 0
        self.green_timer = 0

        self.last_state = None
        self.last_action = None
        self.last_score = None

        if initialize_signals:
            self.set_green(0)

    def _non_internal_lanes(self):
        lanes = []
        for lane in traci.trafficlight.getControlledLanes(self.tls_id):
            if lane and not lane.startswith(":") and lane not in lanes:
                lanes.append(lane)
        return lanes

    def is_main_intersection(self):
        # Fringe lights in your current net only control 1-2 lanes.
        return len(self._non_internal_lanes()) >= 4

    def _lane_direction(self, lane_id):
        shape = traci.lane.getShape(lane_id)
        end_x, end_y = shape[-1]
        jx, jy = self.junction_pos
        dx = end_x - jx
        dy = end_y - jy

        if abs(dx) > abs(dy):
            return "east" if dx > 0 else "west"
        return "north" if dy > 0 else "south"

    def _group_incoming_lanes(self):
        groups = {"north": [], "south": [], "east": [], "west": []}
        for lane in self._non_internal_lanes():
            groups[self._lane_direction(lane)].append(lane)
        return groups

    def _extract_safe_states(self):
        """
        Uses the existing SUMO signal program so we keep safe link-level states.
        This avoids inventing unsafe G/r strings.
        """
        logic = traci.trafficlight.getAllProgramLogics(self.tls_id)[0]
        phases = logic.phases
        links = traci.trafficlight.getControlledLinks(self.tls_id)

        candidates = []

        for idx, phase in enumerate(phases):
            state = phase.state
            if "y" in state.lower():
                continue

            green_count = state.count("G") + state.count("g")
            if green_count == 0:
                continue

            ns_score = 0
            ew_score = 0

            for link_idx, char in enumerate(state):
                if char not in ("G", "g"):
                    continue
                if link_idx >= len(links) or not links[link_idx]:
                    continue

                first_link = links[link_idx][0]
                if first_link is None:
                    continue

                in_lane = first_link[0]
                if not in_lane or in_lane.startswith(":"):
                    continue

                d = self._lane_direction(in_lane)
                if d in ("north", "south"):
                    ns_score += 1
                else:
                    ew_score += 1

            candidates.append({
                "idx": idx,
                "state": state,
                "ns_score": ns_score,
                "ew_score": ew_score,
                "green_count": green_count
            })

        if len(candidates) < 2:
            raise RuntimeError(f"Could not extract two green phases for {self.tls_id}")

        ns_candidates = [c for c in candidates if c["ns_score"] >= c["ew_score"]]
        ew_candidates = [c for c in candidates if c["ew_score"] > c["ns_score"]]

        if not ns_candidates:
            ns_candidates = sorted(candidates, key=lambda x: x["ns_score"] - x["ew_score"], reverse=True)
        if not ew_candidates:
            ew_candidates = sorted(candidates, key=lambda x: x["ew_score"] - x["ns_score"], reverse=True)

        ns_phase = ns_candidates[0]
        ew_phase = ew_candidates[0]

        if ns_phase["idx"] == ew_phase["idx"]:
            others = [c for c in candidates if c["idx"] != ns_phase["idx"]]
            if not others:
                raise RuntimeError(f"Only one usable green phase found for {self.tls_id}")
            ew_phase = others[0]

        def next_yellow(phase_idx):
            next_idx = (phase_idx + 1) % len(phases)
            next_state = phases[next_idx].state
            if "y" in next_state.lower():
                return next_state
            return phases[phase_idx].state

        green_states = [ns_phase["state"], ew_phase["state"]]
        yellow_states = [next_yellow(ns_phase["idx"]), next_yellow(ew_phase["idx"])]

        return green_states, yellow_states

    def set_green(self, action):
        traci.trafficlight.setRedYellowGreenState(self.tls_id, self.green_states[action])
        self.current_action = action
        self.pending_action = None
        self.yellow_timer = 0
        self.green_timer = 0

    def request_action(self, action):
        if self.yellow_timer > 0:
            return

        if action == self.current_action:
            return

        if self.green_timer < MIN_GREEN:
            return

        traci.trafficlight.setRedYellowGreenState(self.tls_id, self.yellow_states[self.current_action])
        self.pending_action = action
        self.yellow_timer = YELLOW_TIME

    def step_signal(self):
        if self.yellow_timer > 0:
            self.yellow_timer -= 1
            if self.yellow_timer == 0 and self.pending_action is not None:
                self.set_green(self.pending_action)
        else:
            self.green_timer += 1

    def _queue(self, lanes):
        return sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lanes)

    def _waiting(self, lanes):
        return sum(traci.lane.getWaitingTime(lane) for lane in lanes)

    def get_state(self):
        q_n = self._queue(self.approaches["north"])
        q_s = self._queue(self.approaches["south"])
        q_e = self._queue(self.approaches["east"])
        q_w = self._queue(self.approaches["west"])

        w_n = self._waiting(self.approaches["north"])
        w_s = self._waiting(self.approaches["south"])
        w_e = self._waiting(self.approaches["east"])
        w_w = self._waiting(self.approaches["west"])

        return np.array([
            q_n / 20.0,
            q_s / 20.0,
            q_e / 20.0,
            q_w / 20.0,
            w_n / 100.0,
            w_s / 100.0,
            w_e / 100.0,
            w_w / 100.0,
            float(self.current_action)
        ], dtype=np.float32)

    def get_score(self):
        total_queue = sum(self._queue(v) for v in self.approaches.values())
        total_wait = sum(self._waiting(v) for v in self.approaches.values())
        return total_queue + 0.05 * total_wait

    def controlled_main_lanes(self):
        lanes = []
        for direction_lanes in self.approaches.values():
            lanes.extend(direction_lanes)
        return lanes

# =========================
# SUMO helpers
# =========================
def start_sumo():
    traci.start([SUMO_BINARY, "-c", SUMO_CFG, "--no-step-log", "true", "--quit-on-end", "true"])

def discover_main_tls_ids():
    ids = []
    for tls_id in traci.trafficlight.getIDList():
        lanes = []
        for lane in traci.trafficlight.getControlledLanes(tls_id):
            if lane and not lane.startswith(":") and lane not in lanes:
                lanes.append(lane)
        if len(lanes) >= 4:
            ids.append(tls_id)
    return sorted(ids)

def bootstrap_agents():
    start_sumo()
    tls_ids = discover_main_tls_ids()
    traci.close()

    if not tls_ids:
        raise RuntimeError("No main intersections found. Check your SUMO network.")

    agents = {tls_id: DQNAgent(tls_id) for tls_id in tls_ids}
    return tls_ids, agents

# =========================
# Episode runner
# =========================
def run_episode(agents, train=True, explore=True):
    start_sumo()
    controllers = [IntersectionController(tls_id, initialize_signals=train or explore) for tls_id in sorted(agents.keys())]

    metrics_lanes = []
    for ctrl in controllers:
        metrics_lanes.extend(ctrl.controlled_main_lanes())

    total_wait = 0.0
    total_queue = 0.0
    total_arrived = 0
    total_loss = []

    for step in range(MAX_STEPS):
        traci.simulationStep()

        for ctrl in controllers:
            ctrl.step_signal()

        if step % DECISION_INTERVAL == 0:
            for ctrl in controllers:
                agent = agents[ctrl.tls_id]
                state = ctrl.get_state()
                score = ctrl.get_score()

                if ctrl.last_state is not None:
                    reward = ctrl.last_score - score
                    agent.store(ctrl.last_state, ctrl.last_action, reward, state, 0.0)
                    if train:
                        loss = agent.train_step()
                        if loss is not None:
                            total_loss.append(loss)

                action = agent.select_action(state, explore=explore)
                ctrl.request_action(action)

                ctrl.last_state = state
                ctrl.last_action = action
                ctrl.last_score = score

        total_wait += sum(traci.lane.getWaitingTime(lane) for lane in metrics_lanes)
        total_queue += sum(traci.lane.getLastStepHaltingNumber(lane) for lane in metrics_lanes)
        total_arrived += traci.simulation.getArrivedNumber()

        if traci.simulation.getMinExpectedNumber() == 0 and step > 300:
            break

    traci.close()

    steps_done = max(1, step + 1)
    return {
        "avg_wait_per_step": total_wait / steps_done,
        "avg_queue_per_step": total_queue / steps_done,
        "throughput": total_arrived,
        "avg_loss": float(np.mean(total_loss)) if total_loss else 0.0
    }

# =========================
# Main training loop
# =========================
def main():
    tls_ids, agents = bootstrap_agents()

    print(f"Detected main intersections: {tls_ids}")
    
    best_wait = float('inf') # Track the lowest waiting time

    for episode in range(1, MAX_EPISODES + 1):
        metrics = run_episode(agents, train=True, explore=True)

        for agent in agents.values():
            agent.decay_epsilon()

        if episode % TARGET_UPDATE_EVERY == 0:
            for agent in agents.values():
                agent.update_target()

        # --- SAVE THE BEST MODEL ---
        current_wait = metrics['avg_wait_per_step']
        if current_wait < best_wait:
            best_wait = current_wait
            print(f"💾 New Best Score! Avg Wait dropped to: {best_wait:.2f}")
            for agent in agents.values():
                # Save with the _best suffix
                best_path = os.path.join(MODEL_DIR, f"{agent.name}_best.pth")
                torch.save(agent.policy_net.state_dict(), best_path)

        if episode % 20 == 0:
            for agent in agents.values():
                agent.save()

        print(
            f"Episode {episode:03d} | "
            f"Wait: {metrics['avg_wait_per_step']:.2f} | "
            f"Queue: {metrics['avg_queue_per_step']:.2f} | "
            f"Throughput: {metrics['throughput']} | "
            f"Loss: {metrics['avg_loss']:.4f} | "
            f"Eps: {list(agents.values())[0].epsilon:.3f}"
        )

    print("Training complete. The best models are saved as '_best.pth'.")

if __name__ == "__main__":
    main()