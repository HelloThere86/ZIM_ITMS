import traci

from main_marl import (
    SUMO_BINARY,
    SUMO_CFG,
    MAX_STEPS,
    DECISION_INTERVAL,
    bootstrap_agents,
    IntersectionController,
)

def start_sumo():
    traci.start([SUMO_BINARY, "-c", SUMO_CFG, "--no-step-log", "true", "--quit-on-end", "true"])

def run_fixed_time(tls_ids):
    start_sumo()

    # Do not override default SUMO programs
    controllers = [IntersectionController(tls_id, initialize_signals=False) for tls_id in tls_ids]
    lanes = []
    for ctrl in controllers:
        lanes.extend(ctrl.controlled_main_lanes())

    total_wait = 0.0
    total_queue = 0.0
    total_arrived = 0

    for step in range(MAX_STEPS):
        traci.simulationStep()

        total_wait += sum(traci.lane.getWaitingTime(lane) for lane in lanes)
        total_queue += sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lanes)
        total_arrived += traci.simulation.getArrivedNumber()

        if traci.simulation.getMinExpectedNumber() == 0 and step > 300:
            break

    traci.close()

    steps_done = max(1, step + 1)
    return {
        "avg_wait_per_step": total_wait / steps_done,
        "avg_queue_per_step": total_queue / steps_done,
        "throughput": total_arrived
    }

def run_trained_marl(agents):
    start_sumo()
    controllers = [IntersectionController(tls_id, initialize_signals=True) for tls_id in sorted(agents.keys())]
    lanes = []
    for ctrl in controllers:
        lanes.extend(ctrl.controlled_main_lanes())

    total_wait = 0.0
    total_queue = 0.0
    total_arrived = 0

    for step in range(MAX_STEPS):
        traci.simulationStep()

        for ctrl in controllers:
            ctrl.step_signal()

        if step % DECISION_INTERVAL == 0:
            for ctrl in controllers:
                agent = agents[ctrl.tls_id]
                state = ctrl.get_state()
                action = agent.select_action(state, explore=False)
                ctrl.request_action(action)

        total_wait += sum(traci.lane.getWaitingTime(lane) for lane in lanes)
        total_queue += sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lanes)
        total_arrived += traci.simulation.getArrivedNumber()

        if traci.simulation.getMinExpectedNumber() == 0 and step > 300:
            break

    traci.close()

    steps_done = max(1, step + 1)
    return {
        "avg_wait_per_step": total_wait / steps_done,
        "avg_queue_per_step": total_queue / steps_done,
        "throughput": total_arrived
    }

def main():
    tls_ids, agents = bootstrap_agents()

    for agent in agents.values():
        agent.load()

    fixed = run_fixed_time(tls_ids)
    marl = run_trained_marl(agents)

    print("\n=== FIXED-TIME BASELINE ===")
    print(f"Avg wait/step : {fixed['avg_wait_per_step']:.2f}")
    print(f"Avg queue/step: {fixed['avg_queue_per_step']:.2f}")
    print(f"Throughput    : {fixed['throughput']}")

    print("\n=== TRAINED MARL ===")
    print(f"Avg wait/step : {marl['avg_wait_per_step']:.2f}")
    print(f"Avg queue/step: {marl['avg_queue_per_step']:.2f}")
    print(f"Throughput    : {marl['throughput']}")

    print("\n=== IMPROVEMENT ===")
    wait_improvement = ((fixed['avg_wait_per_step'] - marl['avg_wait_per_step']) / max(fixed['avg_wait_per_step'], 1e-6)) * 100
    queue_improvement = ((fixed['avg_queue_per_step'] - marl['avg_queue_per_step']) / max(fixed['avg_queue_per_step'], 1e-6)) * 100
    throughput_gain = marl['throughput'] - fixed['throughput']

    print(f"Wait improvement : {wait_improvement:.2f}%")
    print(f"Queue improvement: {queue_improvement:.2f}%")
    print(f"Throughput gain  : {throughput_gain}")

if __name__ == "__main__":
    main()