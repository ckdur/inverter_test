import os 
import subprocess
import numpy as np
import json
import re
import itertools
import numbers

# === Config ===
RESULT_DIR = "results"
NGSPICE = "ngspice"  # or full path to ngspice
PDK_ROOT = os.environ.get("PDK_ROOT", "/usr/local/share/OpenPDKs/IHP-Open-PDK")

os.makedirs(RESULT_DIR, exist_ok=True)

# === Load thresholds ===
def load_thresholds(file):
    with open(file) as f:
        return json.load(f)

# === Load swipes ===
def load_sweeps(file):
    with open(file) as f:
        sweeps = json.load(f)
        for key, val in sweeps.items():
            if val["type"] == "sweep":
                sweeps[key]["data"] = np.linspace(val["data"][0], val["data"][1], int(val["data"][2]))
    return sweeps

# An utility that just extracts the results from the "print" command
# This only works on measurements
def parse_timing_file(filepath):
    data = {}
    with open(filepath, 'r') as f:
        for line in f:
            if '=' in line:
                key, value = line.strip().split('=')
                data[key.strip()] = float(value.strip())
    return data

def extract_metrics(output_file, thresholds):
    # Just parse the file from the spice measurements.
    #try:
    data = parse_timing_file(output_file)
    values = {}
    for key in thresholds:
        values[key] = data[key]

    return values
    #except:
    #    return None

def check_threshold(value, min_val, max_val):
    return min_val <= value <= max_val

def run_simulation(sweep, thresholds, index, spice_template):
    spice_file = os.path.join(RESULT_DIR, f"test_{index}.spice")
    with open(spice_template) as f:
        content = f.read()
        content = content.replace("{PDK_ROOT}", PDK_ROOT)
        for key, val in sweep.items():
            if isinstance(val, numbers.Number):
                vals = f"{val:.2e}"
            else:
                vals = val
            content = content.replace("{{{}}}".format(key), vals)

    with open(spice_file, "w") as f:
        f.write(content)
    subprocess.run([NGSPICE, "-b", "-o", f"{RESULT_DIR}/sim_{index}.log", spice_file], check=True)
    result_file = os.path.join(RESULT_DIR, "results.txt")
    result = extract_metrics(result_file, thresholds)
    os.rename(result_file, os.path.join(RESULT_DIR, f"results_{index}.txt"))

    # TODO: We may need to return all true/false states for each threshold
    if result is None:
        return False, result

    is_pass = True
    for key, threshold in thresholds.items():
        this_data = result[key]
        this_pass = check_threshold(this_data, *threshold["range"])
        is_pass = is_pass and this_pass

    return is_pass, result

def run_all_sweeps(sweeps, thresholds, spice_template):
    # === Run all sweeps ===
    lists = []
    # TODO: It is really ok to do this?
    for key, d in sweeps.items():
        lists.append(list(d["data"]))
    
    # Iterate all sweeps in a combination
    index = 0
    summary = []
    for comb in itertools.product(*lists):
        sweep = {}
        for key, val in zip(list(sweeps),comb):
            sweep[key] = val
        
        # Running the simulation
        index += 1
        disp_text = ", ".join([f"{sweeps[key]["name"]}={sweep[key]}" for key in sweeps])
        print(f"Running test #{index} for {disp_text}...")
        passed, result = run_simulation(sweep, thresholds, index, spice_template)
        status = "PASS" if passed else "FAIL"
        summary.append((index, status, sweep, result))

    disp_text_sweeps = ", ".join([f"{sweeps[key]["name"]:>8}" for key in sweeps])
    disp_text_thresholds = ", ".join([f"{thresholds[key]["name"]:>8}" for key in thresholds])

    # === Print Results ===
    print("\n=== Simulation Summary ===")
    print(f"{'ID':>3} {"Status":>8} {disp_text_sweeps} {disp_text_thresholds}")
    for i, s, sweep, result in summary:
        disp_text_sweeps = ", ".join([f"{sweep[key]:>8}" for key in sweeps])
        disp_text_thresholds = ", ".join([f"{result[key]:>8.3g}" for key in thresholds])

        print(f"{i:>3} {s:>8} {disp_text_sweeps} {disp_text_thresholds} ")
    
    # Fail if any test failed
    if any(s != "PASS" for _, s, *_ in summary):
        return False

    return True

if __name__ == "__main__":
    SPICE_TEMPLATE = "inverter_tb.spice"
    THRESHOLD_FILE = "thresholds.json"
    SWIPE_FILE = "sweeps.json"

    thresholds = load_thresholds(THRESHOLD_FILE)
    sweeps = load_sweeps(SWIPE_FILE)

    result = run_all_sweeps(sweeps, thresholds, SPICE_TEMPLATE)
    if not result:
        exit(1)  # Fail the program to communicate to the CI
