#!/usr/bin/python3
import time
import serial

print("UART Demonstration Program")
print("NVIDIA Jetson Nano Developer Kit")

# Setup according to user request
serial_port = serial.Serial(
    port="/dev/ttyTHS1",
    baudrate=115200,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
)
# Wait a second to let the port initialize
time.sleep(1)

try:
    # Send a simple header AND a SentryBOT command so we get a reply
    print("Sending header and 'hello' command...")
    # serial_port.write("UART Demonstration Program\r\n".encode())
    
    # SentryBOT expects JSON with a newline
    cmd = '{"cmd":"hello"}\n'
    serial_port.write(cmd.encode())
    
    while True:
        if serial_port.inWaiting() > 0:
            # Read all available bytes
            data = serial_port.read(serial_port.inWaiting())
            
            # Print raw/decoded data
            try:
                print(data.decode('utf-8'), end='')
            except:
                print(data)
                
            # NOTE: Echo (serial_port.write(data)) is DISABLED
            # because echoing back to Arduino will confuse it (loops).
            
except KeyboardInterrupt:
    print("Exiting Program")

except Exception as exception_error:
    print("Error occurred. Exiting Program")
    print("Error: " + str(exception_error))

finally:
    serial_port.close()
    pass
