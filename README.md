# Nicklas Waananen, CSCI-490, Shelley Wong -Capstone
![alt text](image.png)
Order confirmation photo for parts^

# MAX30102
MAX30102 pulse oximetry sensor code for Raspberry Pi.

## Overview ##

The heartrate_monitor.py code was originally based on:
[vrano714 MAX30102 Raspberry Pi tutorial](https://github.com/vrano714/max30102-tutorial-raspberrypi?utm_source=chatgpt.com)

Code has been modified it so the sensor no longer relies on the interrupt pin, but will instead continuously check the FIFO read/write pointers to pull data directly from the sensor. I also added a threaded system to make the sensor easier to start, stop, and manage during runtime.

## Setup

This project requires a few external Python libraries, mainly `smbus` and `numpy`.


## Running the script

To run the script, you would first activate the virtual environment via: source venv/bin/activate

Then the script is found within Vendor/Max30102/ heartrate_monitor.py, can be run with python3 heartrate_monitor.py

The sensor data will print to the terminal output regardless if the Pi is not plugged in to display the script.

While the thread is active, the current BPM value can be accessed through the `bpm` variable. It usually takes a few seconds before the readings stabilize enough to produce reliable heart rate values, since the MAX30102 is pretty sensitive to movement and finger placement.
