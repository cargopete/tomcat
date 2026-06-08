#!/usr/bin/env python3
"""Standalone PIR sanity check.

Wave a hand in front of the DFRobot SEN0018 and you should see MOTION printed.
The sensor is wired to BCM17 (physical pin 11). See docs/BUILD.md section 4.1.
"""
from time import sleep

from gpiozero import MotionSensor

pir = MotionSensor(17)  # BCM17 = physical pin 11

print("Warming up PIR for 30 s...")
sleep(30)
print("Ready. Wave your hand.")

while True:
    pir.wait_for_motion()
    print("MOTION")
    pir.wait_for_no_motion()
    print("...clear")
