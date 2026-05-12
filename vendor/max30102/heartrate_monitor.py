# Nicklas Waananen, CSCU-490 Capstone Project, Professor Shelley Wong, 
from max30102 import MAX30102
import hrcalc # Hear rate/Sp02 calculation done by Max30102 sensor
import threading # Lets sensor read data in the background while matplotlib updates screen
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation # Draw graph and menu display
import RPi.GPIO as GPIO
import json
import os
from datetime import datetime

class HeartRateMonitor:
    """
    MAX30102 Working version
    - 5 second countdown
    - 20 second recording window
    - Menu/Button Activation
    - History view from menu HOLD
    """

    LOOP_TIME = 0.01 # Hundredth of a second it reads sensor/button checks
    BUFFER_SIZE = 200 # Sensor samples
    CAPTURE_TIME = 20
    COUNTDOWN_TIME = 5
    RESULT_TIME = 10
    BUTTON_PIN = 17
    HOLD_TIME = 1.5 # How long to count GPIO button press as a hold
    READINGS_FILE = "bpm_readings.json"

    def __init__(self, print_raw=False, print_result=False): 
        self.bpm = 0
        self.print_raw = print_raw # Flags to output raw sensor values to terminal
        self.print_result = print_result

        self.ir_data = [] # Lists are used to store recent sensor readings
        self.red_data = []
        self.bpms = []

        self.lock = threading.Lock() # Lock prevents the sensor thread and graph thread from editing/reading data at the same time
        self.running = False # State flags used by the graph display
        self.finished = False
        self.countdown_active = False
        self.countdown_value = self.COUNTDOWN_TIME

        self.state = "menu"  # Menu state tracking
        self.countdown_start = None
        self.record_start = None
        self.result_start = None
        self.final_bpm = 0
        self.button_down_start = None
        self.saved_readings = []
        
        # GPIO button setup
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        

        if self.print_raw:
            print("IR, Red")

    def reset_recording_data(self): # Reset only the data needed for a new recording
        self.bpm = 0
        self.ir_data = []
        self.red_data = []
        self.bpms = []
        self.running = False
        self.finished = False
        self.countdown_active = False
        self.countdown_value = self.COUNTDOWN_TIME
        self.countdown_start = None
        self.record_start = None
        self.result_start = None

    def load_readings(self): # Check if the readings file already exists, return empty if no file
        if os.path.exists(self.READINGS_FILE):
            with open(self.READINGS_FILE, "r") as file:
                return json.load(file)
        return []

    def save_reading(self, bpm):
        if bpm < 40 or bpm >= 150: # Ignore invalid BPMs
            return

        readings = self.load_readings()

        readings.append({ # Add newest readings with BPM and timestamp
            "bpm": round(float(bpm), 1),
            "time": datetime.now().strftime("%Y-%m-%d %I:%M %p")
        })

        with open(self.READINGS_FILE, "w") as file: # Rewrite Json with updated info
            json.dump(readings, file, indent=4)
            
    def run_sensor(self): 
        sensor = MAX30102()
        time.sleep(1) # Delay fix to allow the graph to work correctly I dont understand why

        try:
            while True:
                # Check how many unread samples are available from the sensor FIFO(First in first out) buffer
                num_bytes = sensor.get_data_present()

                if num_bytes > 0: # Read all samples
                    while num_bytes > 0:
                        red, ir = sensor.read_fifo()
                        num_bytes -= 1

                        with self.lock: # Save new readings, graph reads them too
                            self.ir_data.append(ir)
                            self.red_data.append(red)

                            if len(self.ir_data) > self.BUFFER_SIZE:
                                self.ir_data.pop(0)
                                self.red_data.pop(0)

                        if self.print_raw:
                            print(f"{ir}, {red}")

                    with self.lock: # Calculates 100 samples
                        if len(self.ir_data) >= 100:
                            ir_window = self.ir_data[-100:]
                            red_window = self.red_data[-100:]

                            bpm, valid_bpm, spo2, valid_spo2 = hrcalc.calc_hr_and_spo2(
                                ir_window, red_window
                            )

                            if valid_bpm and self.state == "recording": # Only update BPM during the recording state
                                if 45 <= bpm <= 180: # Reject extreme bpms
                                    self.bpms.append(bpm)
                                
                                    if len(self.bpms) > 8: # Save bpms for smoothing
                                        self.bpms.pop(0)
                                    
                                    if len(self.bpms) >= 4:
                                        self.bpm = np.median(self.bpms)

                            if np.mean(ir_window) < 50000 and np.mean(red_window) < 50000: # Check is made since low and red averages mean nothing on the sensor
                                self.bpm = 0
                                if self.print_result and self.state == "recording":
                                    print("No finger detected")
                            else:
                                if self.print_result and self.state == "recording":
                                    print(f"BPM: {self.bpm:.1f}")

                else:
                    if self.print_result and self.state == "recording": # Debug if sensor not providing samples
                        print("num_bytes = 0")

                # MENU state
                if self.state == "menu":
                    self.running = False
                    self.finished = False
                    self.countdown_active = False

                    if GPIO.input(self.BUTTON_PIN) == GPIO.LOW:
                        time.sleep(0.05) # Small debounce delay to avoid false button triggers

                        if GPIO.input(self.BUTTON_PIN) == GPIO.LOW:
                            if self.button_down_start is None:
                                self.button_down_start = time.time()

                            elif self.button_down_start is not None and time.time() - self.button_down_start >= self.HOLD_TIME: # Controls the history view from menu by holding GPIO button
                                self.saved_readings = self.load_readings()
                                self.state = "history"
                                self.button_down_start = None
                                time.sleep(1.0)

                    else:
                        if self.button_down_start is not None: # Decides if it was press or not
                            press_time = time.time() - self.button_down_start
                            self.button_down_start = None

                            if press_time < self.HOLD_TIME: # Single press starts new recording
                                self.reset_recording_data()
                                self.state = "countdown"
                                self.countdown_active = True
                                self.countdown_start = time.time()
                                time.sleep(0.3)
                                
                # COUNTDOWN
                elif self.state == "countdown":
                    elapsed = time.time() - self.countdown_start
                    self.countdown_value = max(1, self.COUNTDOWN_TIME - int(elapsed))

                    if elapsed >= self.COUNTDOWN_TIME: # Countdown finish, then record
                        self.countdown_active = False
                        self.running = True
                        self.state = "recording"
                        self.record_start = time.time()

                # RECORDING
                elif self.state == "recording":
                    if time.time() - self.record_start >= self.CAPTURE_TIME: # Stop recording a
                        self.running = False
                        self.finished = True

                        # Freeze final BPM and display
                        self.final_bpm = self.bpm
                        self.save_reading(self.final_bpm)

                        self.state = "result"
                        self.result_start = time.time()

                # RESULT
                elif self.state == "result":
                    if time.time() - self.result_start >= self.RESULT_TIME: # After result, return to menu
                        self.state = "menu"

                # HISTORY
                elif self.state == "history":
                    if GPIO.input(self.BUTTON_PIN) == GPIO.LOW: # Long press for history
                        self.button_down_start = None

                time.sleep(self.LOOP_TIME)

        finally:
            sensor.shutdown()
            GPIO.cleanup() # Cleanup when program exits

    def start_sensor(self):
        self._thread = threading.Thread(target=self.run_sensor, daemon=True) # Start run_sensor in a background daemon thread
        self._thread.start()

    def stop_sensor(self, timeout=2.0): # Wait for the sensor thread to stop when program exits
        if hasattr(self, "_thread"):
            self._thread.join(timeout)

    def find_peaks(self, data): # Find simple local peaks in the waveform for graph
        peaks_x = []
        peaks_y = []

        if len(data) < 3: # Needs 3 points to compare a point to left/right
            return peaks_x, peaks_y

        threshold = np.mean(data)

        for i in range(1, len(data) - 1): # Math for marking peaks if its higher than neighbors
            if data[i] > data[i - 1] and data[i] > data[i + 1] and data[i] > threshold:
                peaks_x.append(i)
                peaks_y.append(data[i])

        return peaks_x, peaks_y

    def plot_realtime(self): # Matplotlib screen for menu/graph/countdown
        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(11, 6))
        fig.patch.set_facecolor("black")
        ax.set_facecolor("black")

        line, = ax.plot([], [], lw=2) # Main waveform line and red peak markers
        peak_points, = ax.plot([], [], "ro", markersize=4)

        title_text = ax.text(0.5, 0.94, "", transform=ax.transAxes,
                             fontsize=20, ha="center", va="center", fontweight="bold")

        status_text = ax.text(0.5, 0.84, "", transform=ax.transAxes,
                              fontsize=18, ha="center", va="center")

        bpm_text = ax.text(0.5, 0.74, "", transform=ax.transAxes,
                           fontsize=28, ha="center", va="center", fontweight="bold")

        ax.set_title("Heart Rate Monitor", fontsize=18, pad=16)
        ax.set_xlabel("Sample")
        ax.set_ylabel("IR Value")
        ax.grid(True, alpha=0.2)

        def init(): # Set the initial blank graph state before animation starts
            line.set_data([], [])
            peak_points.set_data([], [])
            title_text.set_text("Heart Shaped Box")
            status_text.set_text("Preparing...")
            bpm_text.set_text("")
            return line, peak_points, title_text, status_text, bpm_text

        def update(frame):
            with self.lock:
                y = self.ir_data.copy() # Copy IR data from the sensor thread

            if self.state == "menu":
                status_text.set_fontsize(18)
                bpm_text.set_fontsize(28)
                line.set_data([], [])
                peak_points.set_data([], [])
                title_text.set_text("Welcome to Heart Shaped Box!")
                status_text.set_text("PRESS the button to record your BPM, HOLD to view history")
                bpm_text.set_text("")
                ax.set_xlim(0, self.BUFFER_SIZE)
                ax.set_ylim(0, 1)
                return line, peak_points, title_text, status_text, bpm_text

            if self.state == "history": # History screen
                line.set_data([], [])
                peak_points.set_data([], [])
                title_text.set_text("Previous BPM Readings")

                if len(self.saved_readings) == 0:
                    status_text.set_text("No saved readings yet")
                    bpm_text.set_text("Press button to return")
                else:
                    recent = self.saved_readings[-10:] # Show 10 newest saved readings.
                    history_lines = []

                    for reading in reversed(recent):
                        history_lines.append(f"{reading['time']} - {reading['bpm']} BPM")

                    status_text.set_fontsize(12)
                    bpm_text.set_fontsize(16)

                    status_text.set_text("\n".join(history_lines))
                    bpm_text.set_text("Press button to return")

                ax.set_xlim(0, self.BUFFER_SIZE)
                ax.set_ylim(0, 1)
                return line, peak_points, title_text, status_text, bpm_text

            if self.countdown_active: # Countdown screen before recording starts
                status_text.set_fontsize(18)
                bpm_text.set_fontsize(28)
                line.set_data([], [])
                peak_points.set_data([], [])
                title_text.set_text("Heart Shaped Box")
                status_text.set_text("Place finger on sensor")
                bpm_text.set_text(f"Starting in {self.countdown_value}")
                ax.set_xlim(0, self.BUFFER_SIZE)
                ax.set_ylim(0, 1)
                return line, peak_points, title_text, status_text, bpm_text

            x = list(range(len(y))) # Convert sensor data into x/y value for plot(s)
            y_centered = np.array(y) - np.mean(y) if len(y) > 0 else np.array([0]) # Remove large direct current offset for visibilty

            line.set_data(x, y_centered)

            if len(y) > 0:
                ymin = float(np.min(y_centered))
                ymax = float(np.max(y_centered))
                padding = max((ymax - ymin) * 0.2, 1000) # Padding for waveform not hitting the top/bottom
                ax.set_xlim(0, len(y))
                ax.set_ylim(ymin - padding, ymax + padding)

                peaks_x, peaks_y = self.find_peaks(y_centered) # Mark peaks on graph
                peak_points.set_data(peaks_x, peaks_y)

            status_text.set_fontsize(18) # Recording display
            bpm_text.set_fontsize(28)
            if self.running:
                status_text.set_text("Recording...")
                bpm_text.set_text(f"BPM: {self.bpm:.1f}" if self.bpm > 0 else "No finger detected")

            elif self.finished and self.result_start is not None: # Result display after the recording ends
                remaining = max(0, self.RESULT_TIME - int(time.time() - self.result_start))
                status_text.set_text(f"Returning to menu in {remaining}s")
                bpm_text.set_text(f"FINAL BPM: {self.final_bpm:.1f}")

            return line, peak_points, title_text, status_text, bpm_text

        self.ani = FuncAnimation(fig, update, init_func=init, interval=50) # FuncAnimation repeatedly calls update() to refresh the graph/screen
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    hrm = HeartRateMonitor(print_raw=False, print_result=True) # Create the monitor object, 
 # Print_result = true utilized because it prints bpm/status message(s) to the terminal
    try:
        hrm.start_sensor() # Start sensor thread first, then open the live display
        hrm.plot_realtime()
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        hrm.stop_sensor() # Try to stop the sensor thread smoothly when program closes
