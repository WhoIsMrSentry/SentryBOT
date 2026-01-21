import serial
import time
import json
import sys

def test_serial(port_name, baud_rate=115200):
    print("Opening {} at {}...".format(port_name, baud_rate))
    try:
        ser = serial.Serial(port_name, baud_rate, timeout=2)
        time.sleep(2)  # Wait for Arduino reset if DTR is connected, or just settle
        print("Port opened.")
    except Exception as e:
        print("Error opening port: {}".format(e))
        return

    # Clear buffer
    ser.reset_input_buffer()

    # Send Hello
    msg = {"cmd": "hello"}
    line_out = json.dumps(msg) + "\n"
    print("Sending: {}".format(line_out.strip()))
    ser.write(line_out.encode('utf-8'))

    # Listen for response
    start_time = time.time()
    while time.time() - start_time < 5:
        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8').strip()
                print("Received: {}".format(line))
                if "ok" in line:
                    print("SUCCESS: Communication established!")
                    return
            except Exception as e:
                print("Read error: {}".format(e))
        time.sleep(0.1)
    
    print("Timed out waiting for response.")
    ser.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        # Default for Jetson UART (GPIO 14/15 -> /dev/ttyTHS1)
        port = "/dev/ttyTHS1" 
    
    print("Usage: python3 manual_test_jetson.py [port]")
    test_serial(port)
