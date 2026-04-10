import os
import sys
import traci

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

def create_zimbabwe_program(tl_id):
    # 1. Get the existing logic to understand the lane structure
    logics = traci.trafficlight.getAllProgramLogics(tl_id)
    current_logic = logics[0]
    
    ns_green_state = current_logic.phases[0].state
    ew_green_state = current_logic.phases[2].state
    
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
    print(f"✅ Zimbabwean Timer (22s-3s-1s) injected successfully into {tl_id}!")

def run():
    print("Starting Baseline Simulation...")
    
    # APPLY TO BOTH INTERSECTIONS
    traffic_lights = traci.trafficlight.getIDList()
    for tl_id in traffic_lights:
        create_zimbabwe_program(tl_id)
    
    step = 0
    total_wait_seconds = 0
    
    while step < 3600:
        traci.simulationStep()
        
        # Track total waiting time correctly:
        # Get the number of vehicles halted (speed < 0.1m/s) in this exact second.
        # 1 halted vehicle in 1 step = 1 second of waiting time.
        for veh_id in traci.vehicle.getIDList():
            if traci.vehicle.getSpeed(veh_id) < 0.1:
                total_wait_seconds += 1
            
        step += 1

    traci.close()
    print("-" * 40)
    print(f"🛑 SIMULATION COMPLETE.")
    print(f"📊 Total Fleet Wait Time: {total_wait_seconds} seconds")
    print(f"📊 Equivalent to: {total_wait_seconds/3600:.2f} hours of cumulative gridlock")
    print("-" * 40)

if __name__ == "__main__":
    # Make sure this points to your new Chaos config file!
    sumoCmd = ["sumo-gui", "-c", "marl_sim.sumocfg"]
    traci.start(sumoCmd)
    run()