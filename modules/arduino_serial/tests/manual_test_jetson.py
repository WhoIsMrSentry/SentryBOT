import serial
import time
import json
import sys

def test_serial(port_name, baud_rate=115200):
    print(f"Opening {port_name} at {baud_rate}...")
    try:
        ser = serial.Serial(port_name, baud_rate, timeout=2)
        time.sleep(2)  # Wait for Arduino reset if DTR is connected, or just settle
        print("Port opened.")
    except Exception as e:
        print(f"Error opening port: {e}")
        return

    # Clear buffer
    ser.reset_input_buffer()

    # Send Hello
    msg = {"cmd": "hello"}
    line_out = json.dumps(msg) + "\n"
    print(f"Sending: {line_out.strip()}")
    ser.write(line_out.encode('utf-8'))

    # Listen for response
    start_time = time.time()
    while time.time() - start_time < 5:
        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8').strip()
                print(f"Received: {line}")
                if "ok" in line:
                    print("SUCCESS: Communication established!")
                    return
            except Exception as e:
                print(f"Read error: {e}")
        time.sleep(0.1)
    
    print("Timed out waiting for response.")
    ser.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        # Default for Jetson UART (GPIO 14/15 -> /dev/ttyTHS1)
        # Check your specific Jetson model!
        port = "/dev/ttyTHS1" 
    
    print(f"Usage: python3 manual_test_jetson.py [port]")
    test_serial(port)
