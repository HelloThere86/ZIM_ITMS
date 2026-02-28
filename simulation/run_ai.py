import os
import sys
import traci

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

def create_zimbabwe_program(tl_id):
    """
    Injects the 6-phase logic (Green -> Yellow -> Red) into the traffic light
    so the AI has phases 0 to 5 to work with.
    """
    logics = traci.trafficlight.getAllProgramLogics(tl_id)
    current_logic = logics[0]
    
    # Grab existing Green states
    ns_green_state = current_logic.phases[0].state
    ew_green_state = current_logic.phases[2].state
    
    def make_yellow(state): return state.replace("G", "y").replace("g", "y")
    def make_red(state):    return "r" * len(state)

    phases = []
    # Phase 0: NS Green
    phases.append(traci.trafficlight.Phase(22, ns_green_state))
    # Phase 1: NS Yellow
    phases.append(traci.trafficlight.Phase(3, make_yellow(ns_green_state)))
    # Phase 2: All Red
    phases.append(traci.trafficlight.Phase(1, make_red(ns_green_state)))
    
    # Phase 3: EW Green
    phases.append(traci.trafficlight.Phase(22, ew_green_state))
    # Phase 4: EW Yellow
    phases.append(traci.trafficlight.Phase(3, make_yellow(ew_green_state)))
    # Phase 5: All Red
    phases.append(traci.trafficlight.Phase(1, make_red(ew_green_state)))
    
    new_logic = traci.trafficlight.Logic("ai_zim_logic", 0, 0, phases)
    traci.trafficlight.setCompleteRedYellowGreenDefinition(tl_id, new_logic)
    print("✅ Logic injected. AI is ready to control phases 0-5.")

def get_queue_lengths():
    # North/South incoming roads
    ns_halt = traci.edge.getLastStepHaltingNumber("top0A0") + \
              traci.edge.getLastStepHaltingNumber("bottom0A0")
    # East/West incoming roads
    ew_halt = traci.edge.getLastStepHaltingNumber("left0A0") + \
              traci.edge.getLastStepHaltingNumber("right0A0")
    return ns_halt, ew_halt

def run():
    print("Starting AI (Adaptive) Simulation...")
    tl_id = "A0"
    step = 0
    total_wait_time = 0
    
    # 1. INJECT THE LOGIC FIRST
    create_zimbabwe_program(tl_id)
    
    # Set initial phase
    current_phase = 0
    traci.trafficlight.setPhase(tl_id, 0)
    
    green_timer = 0
    MIN_GREEN = 5   
    MAX_GREEN = 60  
    
    while step < 3600:
        traci.simulationStep()
        
        ns_queue, ew_queue = get_queue_lengths()
        
        # Track stats
        for veh_id in traci.vehicle.getIDList():
            total_wait_time += traci.vehicle.getWaitingTime(veh_id)
            
        # --- AI LOGIC ---
        if current_phase == 0: # NS IS GREEN
            green_timer += 1
            if green_timer > MIN_GREEN:
                # If (NS Empty AND EW Waiting) OR (Max time reached)
                if (ns_queue == 0 and ew_queue > 0) or (green_timer >= MAX_GREEN):
                    traci.trafficlight.setPhase(tl_id, 1) 
                    current_phase = 1
                    green_timer = 0
                    
        elif current_phase == 1: # NS YELLOW
            green_timer += 1
            if green_timer >= 3:
                traci.trafficlight.setPhase(tl_id, 2) 
                current_phase = 2
                green_timer = 0

        elif current_phase == 2: # ALL RED
            green_timer += 1
            if green_timer >= 1:
                traci.trafficlight.setPhase(tl_id, 3) 
                current_phase = 3
                green_timer = 0

        elif current_phase == 3: # EW IS GREEN
            green_timer += 1
            if green_timer > MIN_GREEN:
                # If (EW Empty AND NS Waiting) OR (Max time reached)
                if (ew_queue == 0 and ns_queue > 0) or (green_timer >= MAX_GREEN):
                    traci.trafficlight.setPhase(tl_id, 4) 
                    current_phase = 4
                    green_timer = 0

        elif current_phase == 4: # EW YELLOW
            green_timer += 1
            if green_timer >= 3:
                traci.trafficlight.setPhase(tl_id, 5) 
                current_phase = 5
                green_timer = 0

        elif current_phase == 5: # ALL RED
            green_timer += 1
            if green_timer >= 1:
                traci.trafficlight.setPhase(tl_id, 0)
                current_phase = 0
                green_timer = 0

        step += 1

    traci.close()
    
    # Result
    hours = total_wait_time / 3600
    print("-" * 40)
    print(f"AI SIMULATION COMPLETE.")
    print(f"Total Cumulative Wait Time: {hours:.2f} hours")
    print("-" * 40)

if __name__ == "__main__":
    sumoCmd = ["sumo-gui", "-c", "sim.sumocfg"]
    traci.start(sumoCmd)
    run()