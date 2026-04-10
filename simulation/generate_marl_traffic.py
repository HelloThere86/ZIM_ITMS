import random

def generate():
    with open("marl_traffic.rou.xml", "w") as f:
        print("""<routes>
        <vType id="normal" accel="2.0" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="15" 
               speedFactor="1.0" speedDev="0.1" guiShape="passenger" jmIgnoreKeepClearTime="30.0"/>
        
        <vType id="kombi" accel="3.5" decel="6.0" sigma="0.9" length="6" minGap="1.0" maxSpeed="20" 
               speedFactor="1.2" speedDev="0.2" laneChangeModel="SL2015" 
               lcStrategic="1.0" lcSpeedGain="10.0" lcCooperative="0.0" lcPushy="1.0" lcAssertive="10" lcImpatience="1.0"
               jmDriveAfterRedTime="2.0" jmDriveAfterYellowTime="5.0" jmIgnoreKeepClearTime="0.1" guiShape="bus"/>
               
        <vType id="mshikashika" accel="4.5" decel="7.0" sigma="1.0" length="4" minGap="0.5" maxSpeed="25" 
               speedFactor="1.4" speedDev="0.3" laneChangeModel="SL2015" 
               lcStrategic="0.1" lcSpeedGain="20.0" lcCooperative="0.0" lcPushy="1.0" lcAssertive="100" lcImpatience="1.0"
               jmDriveAfterRedTime="4.0" jmDriveAfterYellowTime="5.0" jmIgnoreKeepClearTime="0.0" jmIgnoreFoeProb="0.2"
               guiShape="passenger/hatchback"/>
               
        <vType id="truck" accel="0.8" decel="3.0" sigma="0.2" length="12" minGap="4.0" maxSpeed="10" 
               jmIgnoreKeepClearTime="0.1" guiShape="truck"/>
        
        <route id="WE_Straight" edges="left0A0 A0B0 B0right0"/>
        <route id="EW_Straight" edges="right0B0 B0A0 A0left0"/>
        
        <route id="WE_Turn_A0" edges="left0A0 A0bottom0"/>
        <route id="WE_Turn_B0" edges="left0A0 A0B0 B0bottom1"/>
        <route id="EW_Turn_B0" edges="right0B0 B0top1"/>
        <route id="EW_Turn_A0" edges="right0B0 B0A0 A0top0"/>

        <route id="A0_NS" edges="top0A0 A0bottom0"/>
        <route id="A0_SN" edges="bottom0A0 A0top0"/>
        <route id="B0_NS" edges="top1B0 B0bottom1"/>
        <route id="B0_SN" edges="bottom1B0 B0top1"/>
        """, file=f)

        for step in range(3600):
            p_type = random.uniform(0, 1)
            if p_type < 0.15:
                vtype, color = "mshikashika", "1,0.5,0"
            elif p_type < 0.40:
                vtype, color = "kombi", "1,1,0"
            elif p_type > 0.90:
                vtype, color = "truck", "1,0,0"
            else:
                vtype, color = "normal", "1,1,1"

            # Platooning Surge Logic (Massive traffic for 90s, then light traffic)
            surge_multiplier = 3.0 if (step % 300) < 90 else 0.8 

            # Spawn WE
            if random.random() < (0.50 * surge_multiplier):
                route = random.choices(["WE_Straight", "WE_Turn_A0", "WE_Turn_B0"], weights=[0.7, 0.15, 0.15])[0]
                print(f'    <vehicle id="WE_{step}" type="{vtype}" route="{route}" depart="{step}" color="{color}"/>', file=f)
            
            # Spawn EW
            if random.random() < (0.50 * surge_multiplier):
                route = random.choices(["EW_Straight", "EW_Turn_B0", "EW_Turn_A0"], weights=[0.7, 0.15, 0.15])[0]
                print(f'    <vehicle id="EW_{step}" type="{vtype}" route="{route}" depart="{step}" color="{color}"/>', file=f)

            # Spawn Cross Traffic
            cross_prob = 0.10 * surge_multiplier
            for r in ["A0_NS", "A0_SN", "B0_NS", "B0_SN"]:
                if random.random() < cross_prob:
                    print(f'    <vehicle id="{r}_{step}" type="{vtype}" route="{r}" depart="{step}" color="{color}"/>', file=f)

        print("</routes>", file=f)

if __name__ == "__main__":
    generate()
    print("✅ Traffic generated!")