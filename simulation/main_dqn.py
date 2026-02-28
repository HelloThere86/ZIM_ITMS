import os
import sys
import traci
import numpy as np
from agent import Agent

# Setup SUMO
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

# --- CONFIGURATION ---
EPISODES = 50  # How many times to run the simulation
MAX_STEPS = 1000 # Steps per episode
BATCH_SIZE = 32

def get_state(tl_id):
    """
    State = [Queue N, Queue S, Queue E, Queue W]
    """
    n = traci.edge.getLastStepHaltingNumber("top0A0")
    s = traci.edge.getLastStepHaltingNumber("bottom0A0")
    e = traci.edge.getLastStepHaltingNumber("right0A0")
    w = traci.edge.getLastStepHaltingNumber("left0A0")
    return np.array([n, s, e, w])

def calculate_reward(old_wait, new_wait):
    """
    Reward = Change in total waiting time.
    If wait time goes DOWN, reward is POSITIVE.
    If wait time goes UP, reward is NEGATIVE.
    """
    return old_wait - new_wait

def run_simulation():
    # 4 Inputs (Queues), 2 Actions (NS Green=0, EW Green=1)
    agent = Agent(4, 2)
    tl_id = "A0"
    
    # Try to load existing brain if it exists
    if os.path.exists("dqn_traffic.pth"):
        agent.load("dqn_traffic.pth")
        print("Loaded existing AI brain.")

    for e in range(EPISODES):
        # Start SUMO without GUI for training (it's faster), use "sumo-gui" to watch
        traci.start(["sumo", "-c", "sim.sumocfg", "--no-step-log", "true", "--waiting-time-memory", "1000"])
        
        step = 0
        total_reward = 0
        
        # Inject our Zimbabwe 6-phase logic setup (helper function from before)
        # Note: Ideally we define this in XML, but for now we assume Phase 0=NS_G, Phase 2=EW_G
        
        state = get_state(tl_id)
        current_action = 0 # Start with NS Green
        time_in_phase = 0
        
        while step < MAX_STEPS:
            # 1. AI Chooses Action
            action = agent.act(state)
            
            # 2. Execute Action (Switch Light if needed)
            if action != current_action:
                # If we were NS Green(0) and AI wants EW Green(1)
                # In real MARL, we would cycle Yellow -> Red -> Green.
                # For simplicity in V1 Learning: We perform a "Teleport Switch" (Instant Phase Change)
                # Phase 0 = NS Green, Phase 2 = EW Green (In standard SUMO generated maps)
                target_phase = 0 if action == 0 else 2 
                traci.trafficlight.setPhase(tl_id, target_phase)
                current_action = action
                time_in_phase = 0
            
            # Step the simulation forward (e.g., 5 seconds)
            # AI doesn't decide every second, it decides every 5 seconds
            old_total_wait = 0
            for _ in range(5): 
                traci.simulationStep()
                for veh in traci.vehicle.getIDList():
                    old_total_wait += traci.vehicle.getAccumulatedWaitingTime(veh)
                step += 1
            
            # 3. Get New State & Reward
            next_state = get_state(tl_id)
            
            new_total_wait = 0
            for veh in traci.vehicle.getIDList():
                new_total_wait += traci.vehicle.getAccumulatedWaitingTime(veh)
            
            reward = calculate_reward(old_total_wait, new_total_wait)
            
            # 4. Learn
            agent.remember(state, action, reward, next_state, False)
            state = next_state
            total_reward += reward
            
            if len(agent.memory) > BATCH_SIZE:
                agent.replay(BATCH_SIZE)

        print(f"Episode: {e+1}/{EPISODES} | Score: {total_reward:.2f} | Epsilon: {agent.epsilon:.2f}")
        agent.save("dqn_traffic.pth")
        traci.close()

if __name__ == "__main__":
    run_simulation()