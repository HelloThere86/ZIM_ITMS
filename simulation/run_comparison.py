import os
import sys
import traci
import numpy as np
from agent import Agent

# Ensure SUMO is found
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

# Constants
MAX_STEPS = 2000
TL_ID = "A0"

def create_zimbabwe_program(tl_id):
    """
    Injects 6-phase logic (Green -> Yellow -> Red) into the traffic light.
    This is SHARED by both the Fixed Timer and the AI so the comparison is fair.
    """
    logics = traci.trafficlight.getAllProgramLogics(tl_id)
    current_logic = logics[0]
    ns_green = current_logic.phases[0].state
    ew_green = current_logic.phases[2].state
    
    def yel(s): return s.replace("G", "y").replace("g", "y")
    def red(s): return "r" * len(s)

    phases = [
        traci.trafficlight.Phase(999, ns_green),      # 0: NS Green
        traci.trafficlight.Phase(3, yel(ns_green)),   # 1: NS Yellow
        traci.trafficlight.Phase(1, red(ns_green)),   # 2: All Red
        traci.trafficlight.Phase(999, ew_green),      # 3: EW Green
        traci.trafficlight.Phase(3, yel(ew_green)),   # 4: EW Yellow
        traci.trafficlight.Phase(1, red(ew_green))    # 5: All Red
    ]
    
    new_logic = traci.trafficlight.Logic("zim_logic", 0, 0, phases)
    traci.trafficlight.setCompleteRedYellowGreenDefinition(tl_id, new_logic)

def get_state(tl_id):
    """Same state function as training"""
    q_n = traci.edge.getLastStepHaltingNumber("top0A0")
    q_s = traci.edge.getLastStepHaltingNumber("bottom0A0")
    q_e = traci.edge.getLastStepHaltingNumber("right0A0")
    q_w = traci.edge.getLastStepHaltingNumber("left0A0")
    
    w_n = traci.edge.getWaitingTime("top0A0")
    w_s = traci.edge.getWaitingTime("bottom0A0")
    w_e = traci.edge.getWaitingTime("right0A0")
    w_w = traci.edge.getWaitingTime("left0A0")
    
    phase = traci.trafficlight.getPhase(tl_id)
    
    return np.array([
        q_n/50, q_s/50, q_e/50, q_w/50,
        w_n/1000, w_s/1000, w_e/1000, w_w/1000,
        phase/5
    ])

def run_fixed_timer():
    """Runs the simulation with the dumb 22s timer"""
    print(">>> RUNNING OLD SYSTEM (Fixed Timer)...")
    traci.start(["sumo", "-c", "sim.sumocfg", "--no-step-log", "true", "--waiting-time-memory", "1000"])
    
    # 1. INJECT THE LOGIC (Fixes the Phase 4 Error)
    create_zimbabwe_program(TL_ID)
    
    step = 0
    total_wait = 0
    phase_timer = 0
    phase_idx = 0
    
    # 0:NS_G, 1:NS_Y, 2:AllRed, 3:EW_G, 4:EW_Y, 5:AllRed
    durations = [22, 3, 1, 22, 3, 1]
    
    # Force start at phase 0
    traci.trafficlight.setPhase(TL_ID, 0)
    
    while step < MAX_STEPS:
        traci.simulationStep()
        
        # Accumulate Wait Time
        for veh in traci.vehicle.getIDList():
            total_wait += traci.vehicle.getAccumulatedWaitingTime(veh)
            
        # Timer Logic
        phase_timer += 1
        if phase_timer >= durations[phase_idx]:
            phase_idx = (phase_idx + 1) % 6
            traci.trafficlight.setPhase(TL_ID, phase_idx) 
            phase_timer = 0
            
        step += 1
        
    traci.close()
    return total_wait

def run_ai_agent():
    """Runs the simulation with your TRAINED AI"""
    print(">>> RUNNING NEW SYSTEM (AI Agent)...")
    
    # Initialize Agent
    agent = Agent(9, 2)
    
    # LOAD THE BRAIN
    if os.path.exists("dqn_traffic_best.pth"):
        agent.load("dqn_traffic_best.pth")
        print("   Loaded 'dqn_traffic_best.pth'")
    else:
        print("   ERROR: No brain file found! Please run main_dqn.py first.")

    agent.epsilon = 0.0 # Turn off exploration
    
    traci.start(["sumo", "-c", "sim.sumocfg", "--no-step-log", "true", "--waiting-time-memory", "1000"])
    
    # 1. INJECT THE LOGIC
    create_zimbabwe_program(TL_ID)
    traci.trafficlight.setPhase(TL_ID, 0)

    step = 0
    total_wait = 0
    state = get_state(TL_ID)
    
    YELLOW_TIME = 3
    ALL_RED_TIME = 1
    
    while step < MAX_STEPS:
        action = agent.act(state)
        
        current_sumo_phase = traci.trafficlight.getPhase(TL_ID)
        target_sumo_phase = 0 if action == 0 else 3
        
        if current_sumo_phase != target_sumo_phase:
            # Transition: Yellow -> Red -> Green
            traci.trafficlight.setPhase(TL_ID, current_sumo_phase + 1)
            for _ in range(YELLOW_TIME):
                traci.simulationStep()
                step += 1
            traci.trafficlight.setPhase(TL_ID, current_sumo_phase + 2)
            for _ in range(ALL_RED_TIME):
                traci.simulationStep()
                step += 1
            traci.trafficlight.setPhase(TL_ID, target_sumo_phase)
        else:
            # Hold Green
            for _ in range(5):
                traci.simulationStep()
                step += 1
                
        next_state = get_state(TL_ID)
        state = next_state
        
        for veh in traci.vehicle.getIDList():
            total_wait += traci.vehicle.getAccumulatedWaitingTime(veh)

    traci.close()
    return total_wait

if __name__ == "__main__":
    wait_time_fixed = run_fixed_timer()
    wait_time_ai = run_ai_agent()
    
    print("\n" + "="*40)
    print(f"RESULTS COMPARISON (Over {MAX_STEPS} steps)")
    print("="*40)
    print(f"1. Fixed Timer (Zimbabwe Std): {wait_time_fixed:.2f} total seconds delay")
    print(f"2. AI Agent (DQN Model):       {wait_time_ai:.2f} total seconds delay")
    print("-" * 40)
    
    if wait_time_fixed > 0:
        improvement = ((wait_time_fixed - wait_time_ai) / wait_time_fixed) * 100
        print(f"🚀 EFFICIENCY IMPROVEMENT: {improvement:.2f}%")
    else:
        print("Error in baseline calculation.")
    print("="*40)