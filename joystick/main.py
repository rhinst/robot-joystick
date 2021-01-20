import json
import time
from typing import Tuple, Dict, Union
import logging
from dataclasses import dataclass

from redis import Redis
import Adafruit_ADS1x15




@dataclass
class MotorState:
    speed: float
    direction: str


@dataclass
class Axis:
    min: int
    max: int
    center: int


class Joystick:

    adc: Adafruit_ADS1x15.ADS1015

    # Choose a gain of 1 for reading voltages from 0 to 4.09V.
    # Or pick a different gain to change the range of voltages that are read:
    #  - 2/3 = +/-6.144V
    #  -   1 = +/-4.096V
    #  -   2 = +/-2.048V
    #  -   4 = +/-1.024V
    #  -   8 = +/-0.512V
    #  -  16 = +/-0.256V
    gain: int

    x_axis: Axis

    y_axis: Axis


    def __init__(self, **kwargs):
        self.adc = Adafruit_ADS1x15.ADS1015()
        self.gain = kwargs['gain'] if 'gain' in kwargs else 1
        #set conservative starting min/max bounds
        self.x_axis = Axis(min=200, max=1500, center=800)
        self.y_axis = Axis(min=200, max=1500, center=800)


    def calibrate(self):
        calibration_values = [[], []]
        for i in range(10):
            values = [[], []]
            for i in range(2):
                calibration_values[i].append(self.adc.read_adc(i, gain=self.gain))
            time.sleep(0.2)
        self.x_axis.center = sum(calibration_values[0])/len(calibration_values[0])
        self.x_axis.min = self.x_axis.center
        self.x_axis.max = self.x_axis.center
        self.y_axis.center = sum(calibration_values[1])/len(calibration_values[1])
        self.y_axis.min = self.y_axis.center
        self.y_axis.max = self.y_axis.center

    def _update_bounds(self, x: int, y: int):
        self.x_axis.min = min(self.x_axis.min, x)
        self.x_axis.max = max(self.x_axis.max, x)
        self.y_axis.min = min(self.y_axis.min, y)
        self.y_axis.max = max(self.y_axis.max, y)

    def _normalize(self, x: int, y: int) -> Tuple[float, float]:
        normalized_x = 0 if x == self.x_axis.center else ((x - self.x_axis.center) / (self.x_axis.max - self.x_axis.center))
        normalized_y = 0 if y == self.y_axis.center else ((y - self.y_axis.center) / (self.y_axis.max - self.y_axis.center))
        return round(normalized_x, 1), round(normalized_y, 1)

    def get_position(self) -> float:
        x_val = self.adc.read_adc(0, gain=self.gain)
        y_val = self.adc.read_adc(1, gain=self.gain)
        self._update_bounds(x_val, y_val)
        return self._normalize(x_val, y_val)


logger: logging.Logger
motor_states: Dict[str, MotorState]


def drive_motor(position: str, speed: float, direction: str):
    global motor_states

    new_state = MotorState(speed=speed, direction=direction)
    if new_state != motor_states[position]:
        message = json.dumps({
            "command": "drive_motor",
            "position": position,
            "speed": speed,
            "direction": direction
        })
        redis_client.publish("subsystem.motor.command", message)
        motor_states[position] = new_state


def stop_motors():
    global motor_states

    send_command = False
    for position, state in motor_states.items():
        if state.speed > 0:
            state.speed = 0
            send_command = True
    if send_command:
        message = json.dumps({
            "command": "stop"
        })
        redis_client.publish("subsystem.motor.command", message)


def initialize_motors():
    global motor_states

    motor_states = {
        "front_left": MotorState(speed=0, direction="forward"),
        "front_right": MotorState(speed=0, direction="forward"),
        "rear_left": MotorState(speed=0, direction="forward"),
        "rear_right": MotorState(speed=0, direction="forward"),
    }

        

def main():
    global logger

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger()

    redis_client = Redis(host="192.168.86.28", port=6379, db=0)

    
    joystick = Joystick(gain=1)
    joystick.calibrate()
    initialize_motors()
    try:
        while True:
            x, y = joystick.get_position()
            speed = x
            direction = "backward" if y < 0 else "forward"
            if speed == 0:
                stop_motors()
            else: 
                drive_motors("front_left", speed, direction)
                drive_motors("front_right", speed, direction)
                drive_motors("rear_left", speed, direction)
                drive_motors("rear_right", speed, direction)
            logger.debug(f"speed={speed}, direction={direction}")
            # Pause for half a second.
            time.sleep(0.5)
    finally:
        message = json.dumps({
             "command": "stop"
        })
        redis_client.publish("subsystem.motor.command", message)


if __name__ == '__main__':
    main()
