import os
import sys
import traci
from sumolib import checkBinary

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

def create_zimbabwe_program(tl_id):
    # 1. Get the existing logic to understand the lane structure
    logics = traci.trafficlight.getAllProgramLogics(tl_id)
    current_logic = logics[0]
    
    # The netgenerate map usually has 4 phases: 
    # 0: NS Green, 1: NS Yellow, 2: EW Green, 3: EW Yellow
    
    # We grab the "Green" states from the existing map
    ns_green_state = current_logic.phases[0].state
    ew_green_state = current_logic.phases[2].state
    
    # Helper to make yellow/red states
    def make_yellow(state):
        return state.replace("G", "y").replace("g", "y")
    
    def make_red(state):
        return "r" * len(state)

    # 2. Create the 6 Phases: G(22) -> Y(3) -> R(1)
    phases = []
    
    # Phase 0: NS Green (22s)
    phases.append(traci.trafficlight.Phase(22, ns_green_state))
    # Phase 1: NS Yellow (3s)
    phases.append(traci.trafficlight.Phase(3, make_yellow(ns_green_state)))
    # Phase 2: All Red (1s)
    phases.append(traci.trafficlight.Phase(1, make_red(ns_green_state)))
    
    # Phase 3: EW Green (22s)
    phases.append(traci.trafficlight.Phase(22, ew_green_state))
    # Phase 4: EW Yellow (3s)
    phases.append(traci.trafficlight.Phase(3, make_yellow(ew_green_state)))
    # Phase 5: All Red (1s)
    phases.append(traci.trafficlight.Phase(1, make_red(ew_green_state)))
    
    # 3. Apply this new logic to the simulation
    new_logic = traci.trafficlight.Logic("custom_zim", 0, 0, phases)
    traci.trafficlight.setCompleteRedYellowGreenDefinition(tl_id, new_logic)
    print("✅ Zimbabwean Timer (22s-3s-1s) injected successfully!")

def run():
    print("Starting Baseline Simulation...")
    tl_id = "A0"
    
    # Inject the logic immediately after startup
    create_zimbabwe_program(tl_id)
    
    step = 0
    total_wait_time = 0
    
    while step < 3600:
        traci.simulationStep()
        
        # Track waiting time for the report
        for veh_id in traci.vehicle.getIDList():
            total_wait_time += traci.vehicle.getWaitingTime(veh_id)
            
        step += 1

    traci.close()
    print("-" * 30)
    print(f"SIMULATION COMPLETE.")
    print(f"Total Traffic Jam Time: {total_wait_time/3600:.2f} hours")
    print("-" * 30)

if __name__ == "__main__":
    # Start SUMO GUI
    sumoCmd = ["sumo-gui", "-c", "sim.sumocfg"]
    traci.start(sumoCmd)
    run()