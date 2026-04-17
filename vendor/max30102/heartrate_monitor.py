# Nicklas Waananen, Capstone Project
from max30102 import MAX30102
import hrcalc
import threading
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import RPi.GPIO as GPIO

class HeartRateMonitor:
    """
    MAX30102 Working version
    - 5 second countdown
    - 20 second recording window
    - Menu/Button Activation
    """

    LOOP_TIME = 0.01
    BUFFER_SIZE = 200
    CAPTURE_TIME = 20
    COUNTDOWN_TIME = 5
    RESULT_TIME = 10
    BUTTON_PIN = 17

    def __init__(self, print_raw=False, print_result=False):
        self.bpm = 0
        self.spo2 = 0
        self.print_raw = print_raw
        self.print_result = print_result

        self.ir_data = []
        self.red_data = []
        self.bpms = []

        self.lock = threading.Lock()
        self.running = False
        self.finished = False
        self.countdown_active = False
        self.countdown_value = self.COUNTDOWN_TIME

        # Menu/Button state tracking
        self.state = "menu"
        self.countdown_start = None
        self.record_start = None
        self.result_start = None
        self.final_bpm = 0

        # GPIO button setup
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        if self.print_raw:
            print("IR, Red")

    def reset_recording_data(self): # Resets recording data after run(s)
        self.bpm = 0
        self.spo2 = 0
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

    def run_sensor(self):
        sensor = MAX30102()
        time.sleep(1) # Delay fix to allow the graph to work correctly I dont understand why

        try:
            while True:
                # Always read sensor data in background
                num_bytes = sensor.get_data_present()

                if num_bytes > 0:
                    while num_bytes > 0:
                        red, ir = sensor.read_fifo()
                        num_bytes -= 1

                        with self.lock:
                            self.ir_data.append(ir)
                            self.red_data.append(red)

                            if len(self.ir_data) > self.BUFFER_SIZE:
                                self.ir_data.pop(0)
                                self.red_data.pop(0)

                        if self.print_raw:
                            print(f"{ir}, {red}")

                    with self.lock:
                        if len(self.ir_data) >= 100:
                            ir_window = self.ir_data[-100:]
                            red_window = self.red_data[-100:]

                            bpm, valid_bpm, spo2, valid_spo2 = hrcalc.calc_hr_and_spo2(
                                ir_window, red_window
                            )

                            if valid_bpm and self.state == "recording": # Smoothes BPM using average of last few values
                                self.bpms.append(bpm)
                                if len(self.bpms) > 4:
                                    self.bpms.pop(0)
                                self.bpm = np.mean(self.bpms)

                            self.spo2 = spo2 if valid_spo2 else 0

                            if np.mean(ir_window) < 50000 and np.mean(red_window) < 50000:
                                self.bpm = 0
                                if self.print_result and self.state == "recording":
                                    print("No finger detected")
                            else:
                                if self.print_result and self.state == "recording":
                                    print(f"BPM: {self.bpm:.1f}, SpO2: {self.spo2}")

                else:
                    if self.print_result and self.state == "recording":
                        print("num_bytes = 0")

                # MENU
                if self.state == "menu":
                    self.running = False
                    self.finished = False
                    self.countdown_active = False

                    if GPIO.input(self.BUTTON_PIN) == GPIO.LOW:
                        self.reset_recording_data()
                        self.state = "countdown"
                        self.countdown_active = True
                        self.countdown_start = time.time()
                        time.sleep(0.3)

                # COUNTDOWN
                elif self.state == "countdown":
                    elapsed = time.time() - self.countdown_start
                    self.countdown_value = max(1, self.COUNTDOWN_TIME - int(elapsed))

                    if elapsed >= self.COUNTDOWN_TIME:
                        self.countdown_active = False
                        self.running = True
                        self.state = "recording"
                        self.record_start = time.time()

                # RECORDING
                elif self.state == "recording":
                    if time.time() - self.record_start >= self.CAPTURE_TIME:
                        self.running = False
                        self.finished = True

                        # Freeze final BPM
                        self.final_bpm = self.bpm

                        self.state = "result"
                        self.result_start = time.time()

                # RESULT
                elif self.state == "result":
                    if time.time() - self.result_start >= self.RESULT_TIME:
                        self.state = "menu"

                time.sleep(self.LOOP_TIME)

        finally:
            sensor.shutdown()
            GPIO.cleanup()

    def start_sensor(self):
        self._thread = threading.Thread(target=self.run_sensor, daemon=True)
        self._thread.start()

    def stop_sensor(self, timeout=2.0):
        if hasattr(self, "_thread"):
            self._thread.join(timeout)

    def find_peaks(self, data):
        peaks_x = []
        peaks_y = []

        if len(data) < 3:
            return peaks_x, peaks_y

        threshold = np.mean(data)

        for i in range(1, len(data) - 1):
            if data[i] > data[i - 1] and data[i] > data[i + 1] and data[i] > threshold:
                peaks_x.append(i)
                peaks_y.append(data[i])

        return peaks_x, peaks_y

    def plot_realtime(self):
        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(11, 6))
        fig.patch.set_facecolor("black")
        ax.set_facecolor("black")

        line, = ax.plot([], [], lw=2)
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

        def init():
            line.set_data([], [])
            peak_points.set_data([], [])
            title_text.set_text("Heart Shaped Box")
            status_text.set_text("Preparing...")
            bpm_text.set_text("")
            return line, peak_points, title_text, status_text, bpm_text

        def update(frame):
            with self.lock:
                y = self.ir_data.copy()

            if self.state == "menu":
                line.set_data([], [])
                peak_points.set_data([], [])
                title_text.set_text("Welcome to Heart Shaped Box")
                status_text.set_text("Press button to record your BPM")
                bpm_text.set_text("")
                ax.set_xlim(0, self.BUFFER_SIZE)
                ax.set_ylim(0, 1)
                return line, peak_points, title_text, status_text, bpm_text

            if self.countdown_active:
                line.set_data([], [])
                peak_points.set_data([], [])
                title_text.set_text("Heart Shaped Box")
                status_text.set_text("Place finger on sensor")
                bpm_text.set_text(f"Starting in {self.countdown_value}")
                ax.set_xlim(0, self.BUFFER_SIZE)
                ax.set_ylim(0, 1)
                return line, peak_points, title_text, status_text, bpm_text

            x = list(range(len(y)))
            y_centered = np.array(y) - np.mean(y) if len(y) > 0 else np.array([0])

            line.set_data(x, y_centered)

            if len(y) > 0:
                ymin = float(np.min(y_centered))
                ymax = float(np.max(y_centered))
                padding = max((ymax - ymin) * 0.2, 1000)
                ax.set_xlim(0, len(y))
                ax.set_ylim(ymin - padding, ymax + padding)

                peaks_x, peaks_y = self.find_peaks(y_centered)
                peak_points.set_data(peaks_x, peaks_y)

            if self.running:
                status_text.set_text("Recording...")
                bpm_text.set_text(f"BPM: {self.bpm:.1f}" if self.bpm > 0 else "No finger detected")

            elif self.finished:
                remaining = max(0, self.RESULT_TIME - int(time.time() - self.result_start))
                status_text.set_text(f"Returning to menu in {remaining}s")
                bpm_text.set_text(f"FINAL BPM: {self.final_bpm:.1f}")

            return line, peak_points, title_text, status_text, bpm_text

        self.ani = FuncAnimation(fig, update, init_func=init, interval=50)
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    hrm = HeartRateMonitor(print_raw=False, print_result=True)

    try:
        hrm.start_sensor()
        hrm.plot_realtime()
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        hrm.stop_sensor()
