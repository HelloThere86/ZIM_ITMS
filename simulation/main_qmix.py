import os
import sys
import random
from collections import deque
from typing import Dict, List

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import traci

from model import DQN
from plot_training import save_training_plots

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
# Training config (QMIX — final)
# =========================
SEED = 42
MAX_EPISODES = 500
MAX_STEPS = 3600

LOCAL_STATE_DIM = 9
ACTION_DIM = 2          # 0 = KEEP current phase, 1 = SWITCH to other phase
EMBED_DIM = 32

GAMMA = 0.990
LR_AGENT = 1e-3         # agent network learning rate
LR_MIXER = 5e-4         # mixer gets a more conservative rate
BATCH_SIZE = 64
BUFFER_SIZE = 50000
TARGET_UPDATE_EVERY = 10

EPSILON_START = 1.0
EPSILON_END = 0.05
EPSILON_DECAY = 0.990   # hits floor at ~ep 300

DECISION_INTERVAL = 5
MIN_GREEN = 8
YELLOW_TIME = 3

# Reward shaping
QUEUE_WEIGHT = 1.00
WAIT_WEIGHT  = 0.10
REWARD_SCALE = 10.0     # divide raw reward before clipping
REWARD_CLIP  = 5.0      # prevents Q-value explosion from gridlock spikes

MODEL_DIR = "checkpoints_qmix"
os.makedirs(MODEL_DIR, exist_ok=True)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)


# =========================
# Shared Replay Buffer
# One joint transition per decision step covering all agents simultaneously
# =========================
class SharedReplayBuffer:
    def __init__(self, capacity: int):
        self.buffer = deque(maxlen=capacity)

    def push(self, local_states, actions, global_reward,
             next_local_states, global_state, next_global_state, done):
        self.buffer.append((
            np.array(local_states,      dtype=np.float32),
            np.array(actions,           dtype=np.int64),
            float(global_reward),
            np.array(next_local_states, dtype=np.float32),
            np.array(global_state,      dtype=np.float32),
            np.array(next_global_state, dtype=np.float32),
            float(done),
        ))

    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, batch_size)
        (
            local_states_b, actions_b, rewards_b,
            next_local_states_b, global_states_b,
            next_global_states_b, dones_b,
        ) = zip(*batch)

        n_agents = len(local_states_b[0])

        agent_states = [
            torch.tensor(
                np.array([local_states_b[b][i] for b in range(batch_size)]),
                dtype=torch.float32, device=device,
            )
            for i in range(n_agents)
        ]
        agent_next_states = [
            torch.tensor(
                np.array([next_local_states_b[b][i] for b in range(batch_size)]),
                dtype=torch.float32, device=device,
            )
            for i in range(n_agents)
        ]

        actions            = torch.tensor(np.array(actions_b,            dtype=np.int64),   device=device)
        rewards            = torch.tensor(np.array(rewards_b,            dtype=np.float32), device=device)
        dones              = torch.tensor(np.array(dones_b,              dtype=np.float32), device=device)
        global_states      = torch.tensor(np.array(global_states_b,      dtype=np.float32), device=device)
        next_global_states = torch.tensor(np.array(next_global_states_b, dtype=np.float32), device=device)

        return (
            agent_states, actions, rewards,
            agent_next_states, global_states, next_global_states, dones,
        )

    def __len__(self):
        return len(self.buffer)


# =========================
# Hypernetwork
# Takes global state → produces mixing network weights.
# abs() on weight outputs enforces non-negativity (monotonicity constraint
# from Rashid et al. 2018).
# =========================
class HyperNetwork(nn.Module):
    def __init__(self, global_state_dim: int, n_agents: int, embed_dim: int):
        super().__init__()
        self.n_agents  = n_agents
        self.embed_dim = embed_dim

        self.hyper_w1 = nn.Sequential(
            nn.Linear(global_state_dim, embed_dim),
            nn.ReLU(),
            nn.Linear(embed_dim, n_agents * embed_dim),
        )
        self.hyper_b1 = nn.Linear(global_state_dim, embed_dim)

        self.hyper_w2 = nn.Sequential(
            nn.Linear(global_state_dim, embed_dim),
            nn.ReLU(),
            nn.Linear(embed_dim, embed_dim),
        )
        self.hyper_b2 = nn.Sequential(
            nn.Linear(global_state_dim, embed_dim),
            nn.ReLU(),
            nn.Linear(embed_dim, 1),
        )

    def forward(self, global_state: torch.Tensor):
        batch = global_state.shape[0]

        # abs() → non-negative weights → monotonicity guaranteed
        w1 = torch.abs(self.hyper_w1(global_state))
        w1 = w1.view(batch, self.n_agents, self.embed_dim)  # (batch, n_agents, embed_dim)
        b1 = self.hyper_b1(global_state).unsqueeze(1)       # (batch, 1, embed_dim)

        w2 = torch.abs(self.hyper_w2(global_state))
        w2 = w2.view(batch, self.embed_dim, 1)               # (batch, embed_dim, 1)
        b2 = self.hyper_b2(global_state)                     # (batch, 1)

        return w1, b1, w2, b2


# =========================
# Mixing Network
# Combines per-agent Q-values → Q_total using state-conditioned weights
# =========================
class MixingNetwork(nn.Module):
    def __init__(self, global_state_dim: int, n_agents: int, embed_dim: int):
        super().__init__()
        self.hyper = HyperNetwork(global_state_dim, n_agents, embed_dim)

    def forward(self, agent_qs: torch.Tensor, global_state: torch.Tensor) -> torch.Tensor:
        w1, b1, w2, b2 = self.hyper(global_state)
        x      = agent_qs.unsqueeze(1)                   # (batch, 1, n_agents)
        hidden = F.elu(torch.bmm(x, w1) + b1)            # (batch, 1, embed_dim)
        q_tot  = torch.bmm(hidden, w2) + b2.unsqueeze(1) # (batch, 1, 1)
        return q_tot.squeeze(-1).squeeze(-1)              # (batch,)


# =========================
# QMIX Agent
# Each agent owns its own DQN — same architecture as model.py throughout
# =========================
class QMIXAgent:
    def __init__(self, name: str):
        self.name       = name
        self.policy_net = DQN(LOCAL_STATE_DIM, ACTION_DIM).to(device)
        self.target_net = DQN(LOCAL_STATE_DIM, ACTION_DIM).to(device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()
        self.epsilon = EPSILON_START

    def select_action(self, local_state: np.ndarray, explore: bool = True) -> int:
        if explore and random.random() < self.epsilon:
            return random.randrange(ACTION_DIM)
        state_t = torch.tensor(local_state, dtype=torch.float32, device=device).unsqueeze(0)
        self.policy_net.eval()
        with torch.no_grad():
            action = int(torch.argmax(self.policy_net(state_t), dim=1).item())
        self.policy_net.train()
        return action

    def decay_epsilon(self):
        self.epsilon = max(EPSILON_END, self.epsilon * EPSILON_DECAY)

    def update_target(self):
        self.target_net.load_state_dict(self.policy_net.state_dict())

    def save(self, tag: str = ""):
        fname = f"{self.name}{('_' + tag) if tag else ''}.pth"
        torch.save(self.policy_net.state_dict(), os.path.join(MODEL_DIR, fname))

    def load(self, tag: str = ""):
        fname = f"{self.name}{('_' + tag) if tag else ''}.pth"
        path  = os.path.join(MODEL_DIR, fname)
        if not os.path.exists(path):
            raise FileNotFoundError(f"No model for {self.name}: {path}")
        self.policy_net.load_state_dict(torch.load(path, map_location=device))
        self.target_net.load_state_dict(self.policy_net.state_dict())


# =========================
# QMIX Trainer
# Owns the shared buffer, mixer, and the single joint training step
# =========================
class QMIXTrainer:
    def __init__(self, agents: Dict[str, QMIXAgent], n_agents: int):
        self.agents   = agents
        self.n_agents = n_agents
        global_state_dim = LOCAL_STATE_DIM * n_agents

        self.mixer        = MixingNetwork(global_state_dim, n_agents, EMBED_DIM).to(device)
        self.target_mixer = MixingNetwork(global_state_dim, n_agents, EMBED_DIM).to(device)
        self.target_mixer.load_state_dict(self.mixer.state_dict())
        self.target_mixer.eval()

        self.memory = SharedReplayBuffer(BUFFER_SIZE)

        # Separate learning rates for agents vs mixer
        agent_params = []
        for agent in self.agents.values():
            agent_params += list(agent.policy_net.parameters())
        self.optimizer = torch.optim.Adam([
            {"params": agent_params,                  "lr": LR_AGENT},
            {"params": list(self.mixer.parameters()), "lr": LR_MIXER},
        ])

    def store(self, local_states, actions, global_reward,
              next_local_states, global_state, next_global_state, done):
        self.memory.push(
            local_states, actions, global_reward,
            next_local_states, global_state, next_global_state, done,
        )

    def train_step(self):
        if len(self.memory) < BATCH_SIZE:
            return None

        (
            agent_states, actions, rewards,
            agent_next_states, global_states, next_global_states, dones,
        ) = self.memory.sample(BATCH_SIZE)

        agent_list = list(self.agents.values())

        # ---- Current Q-values ----------------------------------------
        agent_qs = []
        for i, agent in enumerate(agent_list):
            agent.policy_net.train()
            q_all = agent.policy_net(agent_states[i])
            q_a   = q_all.gather(1, actions[:, i].unsqueeze(1)).squeeze(1)
            agent_qs.append(q_a)

        q_total = self.mixer(torch.stack(agent_qs, dim=1), global_states)

        # ---- Target Q-values (double-DQN style) ----------------------
        with torch.no_grad():
            target_agent_qs = []
            for i, agent in enumerate(agent_list):
                # Greedy action from policy net
                agent.policy_net.eval()
                best_a = torch.argmax(
                    agent.policy_net(agent_next_states[i]), dim=1, keepdim=True
                )
                agent.policy_net.train()
                # Value from target net
                agent.target_net.eval()
                q_next = agent.target_net(agent_next_states[i]).gather(1, best_a).squeeze(1)
                target_agent_qs.append(q_next)

            q_total_next = self.target_mixer(
                torch.stack(target_agent_qs, dim=1), next_global_states
            )
            targets = rewards + GAMMA * q_total_next * (1.0 - dones)

        # ---- Loss & update -------------------------------------------
        loss = F.smooth_l1_loss(q_total, targets)
        self.optimizer.zero_grad()
        loss.backward()

        all_params = list(self.mixer.parameters())
        for agent in agent_list:
            all_params += list(agent.policy_net.parameters())
        torch.nn.utils.clip_grad_norm_(all_params, max_norm=5.0)

        self.optimizer.step()
        return float(loss.item())

    def update_targets(self):
        self.target_mixer.load_state_dict(self.mixer.state_dict())
        for agent in self.agents.values():
            agent.update_target()

    def save_mixer(self, tag: str = ""):
        fname = f"mixer{('_' + tag) if tag else ''}.pth"
        torch.save(self.mixer.state_dict(), os.path.join(MODEL_DIR, fname))

    def load_mixer(self, tag: str = ""):
        fname = f"mixer{('_' + tag) if tag else ''}.pth"
        path  = os.path.join(MODEL_DIR, fname)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Mixer not found: {path}")
        self.mixer.load_state_dict(torch.load(path, map_location=device))
        self.target_mixer.load_state_dict(self.mixer.state_dict())


# =========================
# Intersection Controller
# =========================
class IntersectionController:
    def __init__(self, tls_id: str, initialize_signals: bool = True):
        self.tls_id       = tls_id
        self.junction_pos = traci.junction.getPosition(tls_id)
        self.approaches   = self._group_incoming_lanes()
        self.green_states, self.yellow_states = self._extract_safe_states()
        self.current_phase = 0
        self.pending_phase = None
        self.yellow_timer  = 0
        self.green_timer   = 0
        self.last_action: int = 0

        if initialize_signals:
            self.set_green(0)

    def _non_internal_lanes(self):
        lanes = []
        for lane in traci.trafficlight.getControlledLanes(self.tls_id):
            if lane and not lane.startswith(":") and lane not in lanes:
                lanes.append(lane)
        return lanes

    def _lane_direction(self, lane_id):
        shape        = traci.lane.getShape(lane_id)
        end_x, end_y = shape[-1]
        jx, jy       = self.junction_pos
        dx, dy       = end_x - jx, end_y - jy
        if abs(dx) > abs(dy):
            return "east" if dx > 0 else "west"
        return "north" if dy > 0 else "south"

    def _group_incoming_lanes(self):
        groups = {"north": [], "south": [], "east": [], "west": []}
        for lane in self._non_internal_lanes():
            groups[self._lane_direction(lane)].append(lane)
        return groups

    def _extract_safe_states(self):
        logic      = traci.trafficlight.getAllProgramLogics(self.tls_id)[0]
        phases     = logic.phases
        links      = traci.trafficlight.getControlledLinks(self.tls_id)
        candidates = []

        for idx, phase in enumerate(phases):
            state = phase.state
            if "y" in state.lower(): continue
            if state.count("G") + state.count("g") == 0: continue

            ns_score, ew_score = 0, 0
            for link_idx, char in enumerate(state):
                if char not in ("G", "g"): continue
                if link_idx >= len(links) or not links[link_idx]: continue
                first_link = links[link_idx][0]
                if first_link is None: continue
                in_lane = first_link[0]
                if not in_lane or in_lane.startswith(":"): continue
                d = self._lane_direction(in_lane)
                if d in ("north", "south"): ns_score += 1
                else: ew_score += 1

            candidates.append({"idx": idx, "state": state,
                                "ns_score": ns_score, "ew_score": ew_score})

        if len(candidates) < 2:
            raise RuntimeError(f"Could not find two green phases for {self.tls_id}")

        ns_candidates = [c for c in candidates if c["ns_score"] >= c["ew_score"]]
        ew_candidates = [c for c in candidates if c["ew_score"] > c["ns_score"]]
        if not ns_candidates:
            ns_candidates = sorted(candidates, key=lambda x: x["ns_score"] - x["ew_score"], reverse=True)
        if not ew_candidates:
            ew_candidates = sorted(candidates, key=lambda x: x["ew_score"] - x["ns_score"], reverse=True)

        ns_phase, ew_phase = ns_candidates[0], ew_candidates[0]
        if ns_phase["idx"] == ew_phase["idx"]:
            others = [c for c in candidates if c["idx"] != ns_phase["idx"]]
            if not others:
                raise RuntimeError(f"Only one usable green phase for {self.tls_id}")
            ew_phase = others[0]

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
        self.yellow_timer  = 0
        self.green_timer   = 0

    def request_semantic_action(self, action: int):
        """0 = KEEP current phase, 1 = SWITCH to the other phase."""
        if self.yellow_timer > 0 or action == 0 or self.green_timer < MIN_GREEN:
            return
        traci.trafficlight.setRedYellowGreenState(
            self.tls_id, self.yellow_states[self.current_phase]
        )
        self.pending_phase = 1 - self.current_phase
        self.yellow_timer  = YELLOW_TIME

    def step_signal(self):
        if self.yellow_timer > 0:
            self.yellow_timer -= 1
            if self.yellow_timer == 0 and self.pending_phase is not None:
                self.set_green(self.pending_phase)
        else:
            self.green_timer += 1

    def _queue(self, lanes):
        return sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lanes)

    def _lane_vehicle_ids(self, lanes):
        vids = []
        for lane in lanes:
            vids.extend(traci.lane.getLastStepVehicleIDs(lane))
        return vids

    def _mean_wait_active(self, lanes) -> float:
        vids = self._lane_vehicle_ids(lanes)
        if not vids:
            return 0.0
        return float(np.mean([traci.vehicle.getWaitingTime(vid) for vid in vids]))

    def get_local_state(self) -> np.ndarray:
        return np.array([
            self._queue(self.approaches["north"]) / 20.0,
            self._queue(self.approaches["south"]) / 20.0,
            self._queue(self.approaches["east"])  / 20.0,
            self._queue(self.approaches["west"])  / 20.0,
            self._mean_wait_active(self.approaches["north"]) / 60.0,
            self._mean_wait_active(self.approaches["south"]) / 60.0,
            self._mean_wait_active(self.approaches["east"])  / 60.0,
            self._mean_wait_active(self.approaches["west"])  / 60.0,
            float(self.current_phase),
        ], dtype=np.float32)

    def get_local_score(self) -> float:
        total_queue = sum(self._queue(v) for v in self.approaches.values())
        mean_wait   = float(np.mean([
            self._mean_wait_active(v) for v in self.approaches.values()
        ]))
        return QUEUE_WEIGHT * total_queue + WAIT_WEIGHT * mean_wait

    def controlled_main_lanes(self):
        lanes = []
        for d_lanes in self.approaches.values():
            lanes.extend(d_lanes)
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


def bootstrap():
    start_sumo()
    tls_ids = discover_main_tls_ids()
    traci.close()
    if not tls_ids:
        raise RuntimeError("No main intersections found.")
    agents  = {tls_id: QMIXAgent(tls_id) for tls_id in tls_ids}
    trainer = QMIXTrainer(agents, n_agents=len(tls_ids))
    return tls_ids, agents, trainer


# =========================
# Episode runner
# =========================
def run_episode(agents, trainer, tls_ids, train=True, explore=True):
    start_sumo()
    controllers = [IntersectionController(tls_id, initialize_signals=True) for tls_id in tls_ids]
    agent_list  = [agents[tls_id] for tls_id in tls_ids]

    metric_lanes = []
    for ctrl in controllers:
        metric_lanes.extend(ctrl.controlled_main_lanes())

    # Per-vehicle mean wait — accurate, used for plots and best-model tracking
    per_vehicle_wait_steps: List[float] = []
    # Lane-sum wait — matches formula in individual_v2 and coop_v2
    # Used for the cross-algorithm comparison table in the dissertation
    lane_sum_wait_total = 0.0
    queue_history: List[float] = []
    total_arrived = 0
    total_loss: List[float] = []

    last_local_states = None
    last_global_state = None
    last_actions      = None
    last_global_score = None

    for step in range(MAX_STEPS):
        traci.simulationStep()
        for ctrl in controllers:
            ctrl.step_signal()

        no_more_vehicles = (
            traci.simulation.getMinExpectedNumber() == 0 and step > 300
        )

        if step % DECISION_INTERVAL == 0:
            local_states = [ctrl.get_local_state() for ctrl in controllers]
            local_scores = [ctrl.get_local_score() for ctrl in controllers]
            global_score = float(sum(local_scores))
            global_state = np.concatenate(local_states, axis=0)
            done_flag    = 1.0 if no_more_vehicles else 0.0

            if last_local_states is not None:
                raw_reward    = last_global_score - global_score
                # Normalise + clip to prevent Q-value explosion from gridlock spikes
                global_reward = float(
                    np.clip(raw_reward / REWARD_SCALE, -REWARD_CLIP, REWARD_CLIP)
                )
                trainer.store(
                    local_states=last_local_states,
                    actions=last_actions,
                    global_reward=global_reward,
                    next_local_states=local_states,
                    global_state=last_global_state,
                    next_global_state=global_state,
                    done=done_flag,
                )
                if train:
                    loss = trainer.train_step()
                    if loss is not None:
                        total_loss.append(loss)

            if not no_more_vehicles:
                actions = [
                    agent.select_action(local_states[i], explore=explore)
                    for i, agent in enumerate(agent_list)
                ]
                for i, ctrl in enumerate(controllers):
                    ctrl.request_semantic_action(actions[i])
                    ctrl.last_action = actions[i]
                last_actions = actions

            last_local_states = local_states
            last_global_state = global_state
            last_global_score = global_score

        # --- Metrics this step ---

        # Per-vehicle mean wait (accurate)
        all_vids = list(set(
            vid
            for lane in metric_lanes
            for vid in traci.lane.getLastStepVehicleIDs(lane)
        ))
        if all_vids:
            per_vehicle_wait_steps.append(
                float(np.mean([traci.vehicle.getWaitingTime(vid) for vid in all_vids]))
            )

        # Lane-sum wait (comparable to DQN files)
        lane_sum_wait_total += sum(
            traci.lane.getWaitingTime(lane) for lane in metric_lanes
        )
        queue_history.append(
            float(sum(traci.lane.getLastStepHaltingNumber(lane) for lane in metric_lanes))
        )
        total_arrived += traci.simulation.getArrivedNumber()

        if no_more_vehicles:
            break

    traci.close()
    steps_done = max(1, step + 1)

    return {
        # Primary metric for plots and best-model selection
        "mean_wait_per_step": float(np.mean(per_vehicle_wait_steps)) if per_vehicle_wait_steps else 0.0,
        # Comparable metric for dissertation four-way comparison table
        "avg_wait_per_step":  lane_sum_wait_total / steps_done,
        "avg_queue_per_step": float(np.mean(queue_history)) if queue_history else 0.0,
        "throughput":         int(total_arrived),
        "avg_loss":           float(np.mean(total_loss)) if total_loss else 0.0,
    }


# =========================
# Main training loop
# =========================
def main():
    tls_ids, agents, trainer = bootstrap()
    n = len(tls_ids)

    print(f"Detected intersections : {tls_ids}")
    print(f"Agents                 : {n}")
    print(f"Global state dim       : {LOCAL_STATE_DIM * n}  ({n} x {LOCAL_STATE_DIM})")
    print(f"Episodes               : {MAX_EPISODES}")
    print(f"Epsilon decay          : {EPSILON_DECAY}  (floor ~ep 300)")
    print(f"Reward scale / clip    : /{REWARD_SCALE}, clip ±{REWARD_CLIP}")
    print(f"Saving to              : {MODEL_DIR}\n")

    best_wait       = float("inf")
    epsilon_history = []
    loss_history    = []
    wait_history    = []   # per-vehicle mean — used for plots

    for episode in range(1, MAX_EPISODES + 1):
        metrics = run_episode(agents, trainer, tls_ids, train=True, explore=True)

        for agent in agents.values():
            agent.decay_epsilon()

        if episode % TARGET_UPDATE_EVERY == 0:
            trainer.update_targets()

        eps = list(agents.values())[0].epsilon
        epsilon_history.append(eps)
        loss_history.append(metrics["avg_loss"])
        wait_history.append(metrics["mean_wait_per_step"])

        current_wait = metrics["mean_wait_per_step"]
        if current_wait < best_wait:
            best_wait = current_wait
            print(f"🌍 New best — mean vehicle wait: {best_wait:.2f}s")
            for agent in agents.values():
                agent.save(tag="best")
            trainer.save_mixer(tag="best")

        if episode % 20 == 0:
            for agent in agents.values():
                agent.save()
            trainer.save_mixer()

        print(
            f"Episode {episode:03d} | "
            f"MeanWait: {metrics['mean_wait_per_step']:.2f}s | "
            f"AvgWait(cmp): {metrics['avg_wait_per_step']:.2f} | "
            f"Queue: {metrics['avg_queue_per_step']:.2f} | "
            f"Throughput: {metrics['throughput']} | "
            f"Loss: {metrics['avg_loss']:.4f} | "
            f"Eps: {eps:.3f}"
        )

    print("\nSaving training plots...")
    save_training_plots(
        epsilon_history=epsilon_history,
        loss_history=loss_history,
        wait_history=wait_history,
        label="qmix",
        out_dir=MODEL_DIR,
    )

    print(f"\n✅ QMIX training complete. Models and plots saved to '{MODEL_DIR}'.")


if __name__ == "__main__":
    main()