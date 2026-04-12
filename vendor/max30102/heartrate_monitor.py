# Nicklas Waananen, Capstone Project
from max30102 import MAX30102
import hrcalc
import threading
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


class HeartRateMonitor:
    """
    MAX30102 Working version
    - 5 second countdown
    - 20 second recording window
    """

    LOOP_TIME = 0.01
    BUFFER_SIZE = 200
    CAPTURE_TIME = 20
    COUNTDOWN_TIME = 5

    def __init__(self, print_raw=False, print_result=False):
        self.bpm = 0
        self.spo2 = 0
        self.print_raw = print_raw
        self.print_result = print_result

        self.ir_data = []
        self.red_data = []
        self.bpms = []

        self.lock = threading.Lock()  # Thread safety lock to prevent graph and sensor conflict
        self.running = False
        self.finished = False
        self.countdown_active = True
        self.countdown_value = self.COUNTDOWN_TIME

        if self.print_raw:
            print("IR, Red")

    def run_sensor(self):
        sensor = MAX30102()
        time.sleep(1) # Delay fix to allow the graph to work correctly I dont understand why

        start_program_time = time.time()
        capture_start_time = None

        try:
            while True:
                elapsed = time.time() - start_program_time

                # countdown phase
                if elapsed < self.COUNTDOWN_TIME:
                    self.countdown_active = True
                    self.countdown_value = max(1, self.COUNTDOWN_TIME - int(elapsed))
                else:
                    if capture_start_time is None:
                        self.countdown_active = False
                        self.running = True
                        capture_start_time = time.time()

                    # stop after capture time
                    if time.time() - capture_start_time >= self.CAPTURE_TIME:
                        self.running = False
                        self.finished = True
                        break

                num_bytes = sensor.get_data_present() ############### SENSOR ###############

                if num_bytes > 0: # If data available;
                    while num_bytes > 0:
                        red, ir = sensor.read_fifo()
                        num_bytes -= 1

                        with self.lock:
                            self.ir_data.append(ir)
                            self.red_data.append(red)

                            if len(self.ir_data) > self.BUFFER_SIZE: # Keep buffer dsize fixed
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

                            if valid_bpm:  # Smoothes BPM using average of last few values
                                self.bpms.append(bpm)
                                if len(self.bpms) > 4:
                                    self.bpms.pop(0)
                                self.bpm = np.mean(self.bpms)

                            self.spo2 = spo2 if valid_spo2 else 0

                            if np.mean(ir_window) < 50000 and np.mean(red_window) < 50000: # Basic finger detection (low signal = no finger)
                                self.bpm = 0
                                if self.print_result:
                                    print("No finger detected")
                            else:
                                if self.print_result:
                                    print(f"BPM: {self.bpm:.1f}, SpO2: {self.spo2}")

                else:
                    if self.print_result:
                        print("num_bytes = 0")

                time.sleep(self.LOOP_TIME)

        finally:
            sensor.shutdown()

    def start_sensor(self):
        self._thread = threading.Thread(target=self.run_sensor, daemon=True)
        self._thread.start()

    def stop_sensor(self, timeout=2.0):
        self.running = False
        if hasattr(self, "_thread"):
            self._thread.join(timeout)

    def find_peaks(self, data):
        peaks_x = []
        peaks_y = []

        if len(data) < 3:
            return peaks_x, peaks_y

        threshold = np.mean(data)

        for i in range(1, len(data) - 1): # Local peak(s) check
            if data[i] > data[i - 1] and data[i] > data[i + 1] and data[i] > threshold:
                peaks_x.append(i)
                peaks_y.append(data[i])

        return peaks_x, peaks_y

    def plot_realtime(self):
        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(11, 6))
        fig.patch.set_facecolor("black")
        ax.set_facecolor("black")

        line, = ax.plot([], [], lw=2) # Waveform line + peak markers
        peak_points, = ax.plot([], [], "ro", markersize=4)

        status_text = ax.text(
            0.5, 0.92, "",
            transform=ax.transAxes,
            fontsize=18,
            ha="center",
            va="center"
        )

        bpm_text = ax.text( # Displays for bpm
            0.5, 0.82, "",
            transform=ax.transAxes,
            fontsize=28,
            ha="center",
            va="center",
            fontweight="bold"
        )

        ax.set_title("Heart Rate Monitor", fontsize=18, pad=16)
        ax.set_xlabel("Sample")
        ax.set_ylabel("IR Value")
        ax.grid(True, alpha=0.2)

        def init():
            line.set_data([], [])
            peak_points.set_data([], [])
            status_text.set_text("Preparing...")
            bpm_text.set_text("")
            return line, peak_points, status_text, bpm_text

        def update(frame):
            with self.lock:
                y = self.ir_data.copy()
                bpm = self.bpm

            if self.countdown_active: #THe Countdown screen
                line.set_data([], [])
                peak_points.set_data([], [])
                status_text.set_text("Place finger on sensor")
                bpm_text.set_text(f"Starting in {self.countdown_value}")
                ax.set_xlim(0, self.BUFFER_SIZE)
                ax.set_ylim(0, 1)
                return line, peak_points, status_text, bpm_text

            if len(y) == 0: # No data yet captured
                status_text.set_text("Waiting for signal...")
                bpm_text.set_text("")
                return line, peak_points, status_text, bpm_text

            x = list(range(len(y)))
            y_centered = np.array(y) - np.mean(y) # Center waveform (removes large DC offset)

            line.set_data(x, y_centered)

            ymin = float(np.min(y_centered))
            ymax = float(np.max(y_centered))
            padding = max((ymax - ymin) * 0.2, 1000)

            ax.set_xlim(0, len(y))
            ax.set_ylim(ymin - padding, ymax + padding)

            peaks_x, peaks_y = self.find_peaks(y_centered) # Peak detection
            peak_points.set_data(peaks_x, peaks_y)

            if self.running:
                status_text.set_text("Recording...")
                if bpm > 0:
                    bpm_text.set_text(f"BPM: {bpm:.1f}")
                else:
                    bpm_text.set_text("No finger detected")

            elif self.finished:
                status_text.set_text("Recording complete")
                if bpm > 0:
                    bpm_text.set_text(f"FINAL BPM: {bpm:.1f}")
                else:
                    bpm_text.set_text("FINAL BPM: Not detected")

                self.ani.event_source.stop()

            return line, peak_points, status_text, bpm_text

        self.ani = FuncAnimation( # Aniamation loop(s)
            fig,
            update,
            init_func=init,
            interval=50,
            blit=False,
            cache_frame_data=False
        )

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
