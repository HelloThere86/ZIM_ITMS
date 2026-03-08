import os
import sys
import traci
import numpy as np
from agent import Agent

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

# --- ADVANCED CONFIGURATION ---
EPISODES = 200
MAX_STEPS = 2000
BATCH_SIZE = 64
YELLOW_TIME = 3
ALL_RED_TIME = 1

def create_zimbabwe_program(tl_id):
    """Injects 6-phase logic"""
    # (Same injection code as before - keeping it concise here)
    logics = traci.trafficlight.getAllProgramLogics(tl_id)
    current_logic = logics[0]
    ns_green = current_logic.phases[0].state
    ew_green = current_logic.phases[2].state
    
    def yel(s): return s.replace("G", "y").replace("g", "y")
    def red(s): return "r" * len(s)

    phases = [
        traci.trafficlight.Phase(999, ns_green),      # 0: NS Green (AI holds this)
        traci.trafficlight.Phase(3, yel(ns_green)),   # 1: NS Yellow
        traci.trafficlight.Phase(1, red(ns_green)),   # 2: All Red
        traci.trafficlight.Phase(999, ew_green),      # 3: EW Green (AI holds this)
        traci.trafficlight.Phase(3, yel(ew_green)),   # 4: EW Yellow
        traci.trafficlight.Phase(1, red(ew_green))    # 5: All Red
    ]
    
    new_logic = traci.trafficlight.Logic("ai_zim_logic", 0, 0, phases)
    traci.trafficlight.setCompleteRedYellowGreenDefinition(tl_id, new_logic)

def get_state(tl_id):
    """
    9 INPUTS:
    [Queue N, S, E, W, WaitTime N, S, E, W, CurrentPhase]
    """
    lanes = ["top0A0_0", "top0A0_1", "bottom0A0_0", "bottom0A0_1", 
             "right0A0_0", "right0A0_1", "left0A0_0", "left0A0_1"]
    
    # Aggregating by direction
    q_n = traci.edge.getLastStepHaltingNumber("top0A0")
    q_s = traci.edge.getLastStepHaltingNumber("bottom0A0")
    q_e = traci.edge.getLastStepHaltingNumber("right0A0")
    q_w = traci.edge.getLastStepHaltingNumber("left0A0")
    
    # Waiting Time (Accumulated for all cars on the edge)
    w_n = traci.edge.getWaitingTime("top0A0")
    w_s = traci.edge.getWaitingTime("bottom0A0")
    w_e = traci.edge.getWaitingTime("right0A0")
    w_w = traci.edge.getWaitingTime("left0A0")
    
    phase = traci.trafficlight.getPhase(tl_id)
    
    # Normalize inputs (dividing by large numbers to keep inputs between 0-1 approx)
    state = np.array([
        q_n/50, q_s/50, q_e/50, q_w/50,
        w_n/1000, w_s/1000, w_e/1000, w_w/1000,
        phase/5
    ])
    return state

def calculate_reward(q_old, q_new, w_old, w_new):
    """
    Compound Reward:
    1. Minimize Queues (Penalty)
    2. Minimize Wait Time (Penalty)
    3. Bonus for reducing queue/wait from previous step
    """
    total_q = sum(q_new)
    total_w = sum(w_new)
    
    # Base Penalty
    reward = -(total_q * 0.5) - (total_w * 0.01)
    
    # Improvement Bonus
    if sum(q_new) < sum(q_old):
        reward += 5
    
    return reward

def run_simulation():
    # 9 Inputs, 2 Actions (0=Keep/Switch to NS, 1=Keep/Switch to EW)
    agent = Agent(9, 2)
    tl_id = "A0"
    best_score = -float('inf')

    # Load checkpoint if exists
    if os.path.exists("dqn_traffic_best.pth"):
        agent.load("dqn_traffic_best.pth")
        print("Loaded BEST model.")

    for e in range(EPISODES):
        traci.start(["sumo", "-c", "sim.sumocfg", "--no-step-log", "true", "--waiting-time-memory", "1000"])
        create_zimbabwe_program(tl_id)
        traci.trafficlight.setPhase(tl_id, 0) # Start NS Green
        
        step = 0
        total_reward = 0
        current_phase_idx = 0 # 0=NS Green, 1=EW Green (Logic index, not SUMO index)
        
        # Initial State
        state = get_state(tl_id)
        
        while step < MAX_STEPS:
            # 1. AI Action
            action = agent.act(state) 
            # Action 0 = Want NS Green (SUMO Phase 0)
            # Action 1 = Want EW Green (SUMO Phase 3)
            
            # 2. Execute Transition
            # If AI wants phase 0, but we are at phase 3, we must transition 3->4->5->0
            current_sumo_phase = traci.trafficlight.getPhase(tl_id)
            
            target_sumo_phase = 0 if action == 0 else 3
            
            if current_sumo_phase == target_sumo_phase:
                # Already in correct phase, just hold it
                # Step forward 5 seconds
                for _ in range(5):
                    traci.simulationStep()
                    step += 1
            else:
                # WE NEED TO SWITCH
                # If we are at 0 (NS Green) and want 3 (EW Green):
                # Go 0 -> 1 (Yellow) -> 2 (Red) -> 3 (Green)
                
                # Trigger Yellow (Next phase)
                traci.trafficlight.setPhase(tl_id, current_sumo_phase + 1)
                
                # Wait for Yellow duration
                for _ in range(YELLOW_TIME):
                    traci.simulationStep()
                    step += 1
                    
                # Trigger Red (Next phase)
                traci.trafficlight.setPhase(tl_id, current_sumo_phase + 2)
                
                # Wait for Red duration
                for _ in range(ALL_RED_TIME):
                    traci.simulationStep()
                    step += 1
                    
                # Finally set Target Green
                traci.trafficlight.setPhase(tl_id, target_sumo_phase)
            
            # 3. Get New State & Reward
            next_state = get_state(tl_id)
            
            # Raw data for reward calc
            q_prev = state[0:4] * 50
            w_prev = state[4:8] * 1000
            q_curr = next_state[0:4] * 50
            w_curr = next_state[4:8] * 1000
            
            reward = calculate_reward(q_prev, q_curr, w_prev, w_curr)
            
            # 4. Remember & Train
            agent.remember(state, action, reward, next_state, False)
            state = next_state
            total_reward += reward
            
            if len(agent.memory) > BATCH_SIZE:
                agent.replay(BATCH_SIZE)

        print(f"Episode: {e+1}/{EPISODES} | Score: {total_reward:.2f} | Epsilon: {agent.epsilon:.2f}")
        
        # Save Best Model
        if total_reward > best_score:
            best_score = total_reward
            agent.save("dqn_traffic_best.pth")
            print("💾 New Best Score! Model Saved.")
            
        # Regular Checkpoint
        if (e+1) % 50 == 0:
            agent.save(f"dqn_checkpoint_{e+1}.pth")

        traci.close()

if __name__ == "__main__":
    run_simulation()