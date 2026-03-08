#!/usr/bin/env python3
"""
Simple serial test harness for SentryBOT Arduino stepper PID using NDJSON commands.
Sends commands, sweeps target speeds, logs pid_status responses to CSV.

Requires: pyserial
pip install pyserial

Usage example:
python scripts/serial_stepper_test.py --port COM4 --baud 115200 --id 0 --start 10 --stop 200 --step 10 --log pid_log.csv
"""
import argparse
import serial
import time
import csv

parser = argparse.ArgumentParser()
parser.add_argument('--port', required=True)
parser.add_argument('--baud', type=int, default=115200)
parser.add_argument('--id', type=int, default=0)
parser.add_argument('--start', type=float, default=10.0)
parser.add_argument('--stop', type=float, default=100.0)
parser.add_argument('--step', type=float, default=10.0)
parser.add_argument('--dwell', type=float, default=3.0, help='seconds to wait after setting target')
parser.add_argument('--log', default='pid_log.csv')
args = parser.parse_args()

ser = serial.Serial(args.port, args.baud, timeout=1)
# flush
time.sleep(0.2)
ser.reset_input_buffer()

def send(cmd):
    s = cmd.replace('\n','') + '\n'
    ser.write(s.encode('utf-8'))

def read_line(timeout=1.0):
    end = time.time() + timeout
    while time.time() < end:
        line = ser.readline()
        if line:
            try:
                return line.decode('utf-8').strip()
            except UnicodeDecodeError:
                return line
    return None

with open(args.log, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['timestamp_ms','id','target','measured','stalled','raw'])

    # enable pid
    send('{"cmd":"pid_enable","id":%d,"enable":true}' % args.id)
    time.sleep(0.2)

    v = args.start
    while v <= args.stop:
        send('{"cmd":"pid_set","id":%d,"target":%f}' % (args.id, v))
        # wait for system to settle
        time.sleep(args.dwell)
        send('{"cmd":"pid_status","id":%d}' % args.id)
        line = read_line(2.0)
        ts = int(time.time()*1000)
        if line is None:
            writer.writerow([ts, args.id, v, '', 'timeout', ''])
            print('No response for target', v)
        else:
            # attempt to parse measured & stalled fields simply
            measured = ''
            stalled = ''
            try:
                import json
                j = json.loads(line)
                measured = j.get('measured','')
                stalled = j.get('stalled','')
            except Exception:
                pass
            writer.writerow([ts, args.id, v, measured, stalled, line])
            print(ts, '->', line)
        v += args.step

    # disable pid and set speed 0
    send('{"cmd":"pid_set","id":%d,"target":0}' % args.id)
    send('{"cmd":"pid_enable","id":%d,"enable":false}' % args.id)
    ser.close()

print('Log written to', args.log)
