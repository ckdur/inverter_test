import os 
import subprocess
import numpy as np
import json
import re

# === Config ===
W_VALUES = np.linspace(1e-6, 3e-6, 3)
SPICE_TEMPLATE = "inverter_tb.spice"
THRESHOLD_FILE = "thresholds.json"
RESULT_DIR = "results"
NGSPICE = "ngspice"  # or full path to ngspice
PDK_ROOT = os.environ.get("PDK_ROOT", "/usr/local/share/OpenPDKs/IHP-Open-PDK")

os.makedirs(RESULT_DIR, exist_ok=True)

# === Load thresholds ===
with open(THRESHOLD_FILE) as f:
    thresholds = json.load(f)

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

def extract_metrics(output_file):
    # Just parse the file from the spice measurements.
    try:
        data = parse_timing_file(output_file)
        delay = data["t_delay"]
        rise_time = data["t_rise"]
        fall_time = data["t_fall"]

        return delay * 1e9, rise_time * 1e9, fall_time * 1e9  # in ns
    except:
        return None, None, None

def check_threshold(value, min_val, max_val):
    return min_val <= value <= max_val

def run_simulation(wn, wp, index):

    spice_file = os.path.join(RESULT_DIR, f"test_{index}.spice")
    with open(SPICE_TEMPLATE) as f:
        content = f.read()
        content = content.replace("{Wn}", f"{wn:.2e}")
        content = content.replace("{Wp}", f"{wp:.2e}")
        content = content.replace("{PDK_ROOT}", PDK_ROOT)

    with open(spice_file, "w") as f:
        f.write(content)
    subprocess.run([NGSPICE, "-b", "-o", f"{RESULT_DIR}/sim_{index}.log", spice_file], check=True)
    result_file = os.path.join(RESULT_DIR, "results.txt")
    delay, rise, fall = extract_metrics(result_file)
    os.rename(result_file, os.path.join(RESULT_DIR, f"results_{index}.txt"))

    if None in (delay, rise, fall):
        return False, delay, rise, fall

    # Compare to thresholds
    rt_ok = check_threshold(rise, *thresholds["rise_time_ns"])
    ft_ok = check_threshold(fall, *thresholds["fall_time_ns"])
    d_ok = check_threshold(delay, *thresholds["delay_ns"])

    return rt_ok and ft_ok and d_ok, delay, rise, fall

# === Run all sweeps ===
summary = []
index = 0
for wn in W_VALUES:
    for wp in W_VALUES:
        index += 1
        print(f"Running test #{index} for Wn={wn*1e6:.2f}um, Wp={wp*1e6:.2f}um...")
        passed, delay, rise, fall = run_simulation(wn, wp, index)
        status = "PASS" if passed else "FAIL"
        summary.append((index, wn, wp, delay, rise, fall, status))

# === Print Results ===
print("\n=== Simulation Summary ===")
print(f"{'ID':>3} {'Wn(um)':>8} {'Wp(um)':>8} {'Delay(ns)':>10} {'Rise(ns)':>10} {'Fall(ns)':>10} Status")
for i, wn, wp, d, r, f, s in summary:
    print(f"{i:>3} {wn*1e6:>8.2f} {wp*1e6:>8.2f} {d:>10.3f} {r:>10.3f} {f:>10.3f} {s}")
# Fail if any test failed
if any(s != "PASS" for *_, s in summary):
    exit(1)



