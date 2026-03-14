# Nicklas Waananen, Capstone 
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks

data = []

with open("pulse_data.txt") as f:
    for line in f:
        if "," not in line:
            continue

        try:
            ir, red = line.strip().split(",")
            data.append(int(ir))
        except:
            continue

# convert data to numpy
data = np.array(data)

data = data - np.mean(data)

# Sample rate approximation need to tweak
sample_rate = 25
time = np.arange(len(data)) / sample_rate

# detect heartbeat peaks
peaks, _ = find_peaks(data, distance=10)

# BPM Calculstion
if len(peaks) > 1:
    peak_times = time[peaks]
    intervals = np.diff(peak_times)
    bpm = 60 / np.mean(intervals)
else:
    bpm = 0

print(f"Estimated BPM: {bpm:.1f}")

# plot waveform
plt.figure(figsize=(8,4))
plt.plot(time, data, label="Pulse Signal")

# Dots/marks on heartbeat peaks
plt.plot(time[peaks], data[peaks], "ro", label="Detected Beats")

plt.title(f"Pulse Waveform (Estimated BPM: {bpm:.1f})")
plt.xlabel("Time (seconds)")
plt.ylabel("Relative IR Signal")
plt.legend()
plt.grid(True)
plt.savefig("pulse_waveform.png")
plt.show()

