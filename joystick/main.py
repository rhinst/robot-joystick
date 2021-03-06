import json
import time
from typing import Tuple, Dict
import logging
from dataclasses import dataclass
from math import atan, sqrt, pi

from redis import Redis

from joystick.adc import ADC

REDIS_SERVER = "192.168.86.28"
#REDIS_SERVER = "127.0.0.1"
REDIS_PORT = 6379

logger: logging.Logger


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
    adc: ADC

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
        self.adc = ADC()
        self.gain = kwargs['gain'] if 'gain' in kwargs else 1
        # set conservative starting min/max bounds
        self.x_axis = Axis(min=200, max=1500, center=800)
        self.y_axis = Axis(min=200, max=1500, center=800)

    def calibrate(self):
        logger.debug("Calibrating joystick bounds")
        calibration_values = [[], []]
        for i in range(10):
            for k in range(2):
                calibration_values[k].append(self.adc.read_adc(k, gain=self.gain))
            time.sleep(0.2)
        self.x_axis.center = sum(calibration_values[0]) / len(calibration_values[0])
        self.y_axis.center = sum(calibration_values[1]) / len(calibration_values[1])
        logger.debug(f"X Bounds: Min={self.x_axis.min}, Center={self.x_axis.center}, Max={self.x_axis.max}")
        logger.debug(f"Y Bounds: Min={self.y_axis.min}, Center={self.y_axis.center}, Max={self.y_axis.max}")

    def _update_bounds(self, x: int, y: int):
        self.x_axis.min = min(self.x_axis.min, x)
        self.x_axis.max = max(self.x_axis.max, x)
        self.y_axis.min = min(self.y_axis.min, y)
        self.y_axis.max = max(self.y_axis.max, y)
        logger.debug(f"X Bounds: Min={self.x_axis.min}, Center={self.x_axis.center}, Max={self.x_axis.max}")
        logger.debug(f"Y Bounds: Min={self.y_axis.min}, Center={self.y_axis.center}, Max={self.y_axis.max}")

    def _normalize(self, x: int, y: int) -> Tuple[float, float]:
        logger.debug(f"Normalizing coordinates: ({x}, {y})")
        normalized_x = 0 if x == self.x_axis.center else (
                (x - self.x_axis.center) / (self.x_axis.max - self.x_axis.center))
        normalized_y = 0 if y == self.y_axis.center else (
                (y - self.y_axis.center) / (self.y_axis.max - self.y_axis.center))
        return round(normalized_x, 1), round(normalized_y, 1)

    def get_position(self) -> Tuple[float, float]:
        x_val = self.adc.read_adc(0, gain=self.gain)
        y_val = self.adc.read_adc(1, gain=self.gain)
        self._update_bounds(x_val, y_val)
        logger.debug(f"Read values from ADC: ({x_val}, {y_val})")
        return self._normalize(x_val, y_val)


motor_states: Dict[str, MotorState]


def drive_motor(redis_client: Redis, position: str, speed: float, direction: str):
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


def stop_motors(redis_client: Redis):
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


def calculate_motor_speeds(x: float, y: float) -> Tuple[float, float]:
    dominant_speed = round(sqrt((x * x) + (y * y)), 1) 
    if y < 0:
        dominant_speed = -dominant_speed
    #avoid division by zero errors
    if y == 0:
        y = 0.00001
    weak_speed = round(dominant_speed * (1 - (abs(atan(x / y)) * (2 / (pi / 2)))), 1)
    return (dominant_speed, weak_speed) if x > 0 else (weak_speed, dominant_speed)


def main():
    global logger

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger()

    redis_client = Redis(host=REDIS_SERVER, port=REDIS_PORT, db=0)

    joystick = Joystick(gain=1)
    joystick.calibrate()
    initialize_motors()
    try:
        while True:
            x, y = joystick.get_position()
            logger.debug(f"Normalized coordinates: ({x}, {y})")
            l_speed, r_speed = calculate_motor_speeds(x, y)
            logger.debug(f"Left Speed={l_speed}, Right Speed={r_speed}")
            if l_speed == 0 and r_speed == 0:
                stop_motors(redis_client)
            else:
                drive_motor(redis_client, "front_left", abs(l_speed), "forward" if l_speed > 0 else "backward")
                drive_motor(redis_client, "front_right", abs(r_speed), "forward" if r_speed > 0 else "backward")
                drive_motor(redis_client, "rear_left", abs(l_speed), "forward" if l_speed > 0 else "backward")
                drive_motor(redis_client, "rear_right", abs(r_speed), "forward" if r_speed > 0 else "backward")
            time.sleep(0.1)
    finally:
        message = json.dumps({
            "command": "stop"
        })
        redis_client.publish("subsystem.motor.command", message)


if __name__ == '__main__':
    main()
