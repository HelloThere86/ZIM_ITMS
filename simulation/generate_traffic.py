import random

def generate_route_file():
    with open("traffic.rou.xml", "w") as routes:
        print("""<routes>
        <!-- 1. Define Driver Behaviors (The "Harare Mix") -->
        
        <!-- Normal Driver: Imperfect (sigma=0.5), tries to follow rules -->
        <vType id="normal" accel="2.0" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="15" guiShape="passenger"/>
        
        <!-- THE KOMBI: Aggressive, tailgates (minGap 0.5), speeds (factor 1.5), weaves lanes -->
        <vType id="kombi" accel="4.5" decel="7.0" sigma="0.9" length="5" minGap="0.5" maxSpeed="25" speedFactor="1.5" 
               laneChangeModel="SL2015" lcStrategic="10.0" lcSpeedGain="10.0" lcCooperative="0.0" lcPushy="1.0" guiShape="bus"/>
        
        <!-- THE HEAVY TRUCK: Slow acceleration, blocks traffic -->
        <vType id="truck" accel="0.8" decel="3.0" sigma="0.2" length="10" minGap="4.0" maxSpeed="8" guiShape="truck"/>

        <!-- 2. Define Routes -->
        <!-- North Incoming -->
        <route id="N_Straight" edges="top0A0 A0bottom0"/>
        <route id="N_Left"     edges="top0A0 A0left0"/>
        <route id="N_Right"    edges="top0A0 A0right0"/>

        <!-- South Incoming -->
        <route id="S_Straight" edges="bottom0A0 A0top0"/>
        <route id="S_Left"     edges="bottom0A0 A0right0"/>
        <route id="S_Right"    edges="bottom0A0 A0left0"/>

        <!-- East Incoming -->
        <route id="E_Straight" edges="right0A0 A0left0"/>
        <route id="E_Left"     edges="right0A0 A0bottom0"/>
        <route id="E_Right"    edges="right0A0 A0top0"/>

        <!-- West Incoming -->
        <route id="W_Straight" edges="left0A0 A0right0"/>
        <route id="W_Left"     edges="left0A0 A0top0"/>
        <route id="W_Right"    edges="left0A0 A0bottom0"/>
        """, file=routes)
        
        # Generate 1 hour of traffic
        for step in range(3600):
            # --- Vehicle Mix Logic ---
            # 60% Normal, 30% Aggressive Kombi, 10% Slow Truck
            p_type = random.uniform(0, 1)
            if p_type < 0.3: 
                veh_type = "kombi"
                color = "1,1,0" # Yellow
            elif p_type > 0.9:
                veh_type = "truck"
                color = "1,0,0" # Red Truck
            else:
                veh_type = "normal"
                color = "1,1,1" # White

            # --- NORTH/SOUTH (Overloaded Main Road) ---
            # Increased probability to 0.4 (Very Heavy)
            if random.uniform(0, 1) < 0.4: 
                # Direction Logic: Most go straight, but turning cars block lanes
                direction = random.uniform(0, 1)
                r_id = "N_Straight"
                if direction < 0.15: r_id = "N_Left"
                elif direction > 0.85: r_id = "N_Right"
                
                print(f'    <vehicle id="N_{step}" type="{veh_type}" route="{r_id}" depart="{step}" color="{color}"/>', file=routes)

            if random.uniform(0, 1) < 0.4:
                direction = random.uniform(0, 1)
                r_id = "S_Straight"
                if direction < 0.15: r_id = "S_Left"
                elif direction > 0.85: r_id = "S_Right"
                print(f'    <vehicle id="S_{step}" type="{veh_type}" route="{r_id}" depart="{step}" color="{color}"/>', file=routes)

            # --- EAST/WEST (Side Road) ---
            # Random occasional traffic
            if random.uniform(0, 1) < 0.08:
                print(f'    <vehicle id="E_{step}" type="{veh_type}" route="E_Straight" depart="{step}" color="{color}"/>', file=routes)
            if random.uniform(0, 1) < 0.08:
                print(f'    <vehicle id="W_{step}" type="{veh_type}" route="W_Straight" depart="{step}" color="{color}"/>', file=routes)
                
        print("</routes>", file=routes)

if __name__ == "__main__":
    generate_route_file()
    print("CHAOS MODE ACTIVATED: Kombis and Trucks generated.")