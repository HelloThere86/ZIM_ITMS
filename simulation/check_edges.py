import re

def find_edges():
    try:
        with open("intersection.net.xml", "r") as f:
            content = f.read()
            # Find all edge IDs that are NOT internal connection edges (starting with :)
            edges = re.findall(r'<edge id="([^:]+)"', content)
            
            print("\n--- FOUND ROADS ---")
            print(f"Total Roads Found: {len(edges)}")
            for e in edges:
                print(f"Road ID: {e}")
            print("-------------------\n")
            
            return edges
    except FileNotFoundError:
        print("Error: intersection.net.xml not found! Did Step 1 run?")

if __name__ == "__main__":
    find_edges()