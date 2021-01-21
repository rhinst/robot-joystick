import platform


if platform.platform().lower().find("armv") > -1:
    from Adafruit_ADS1x15 import ADS1015 as ADC
else:
    print("MOCK!")
    from random import random
    class ADC:
        def read_adc(self, channel, **kwargs):
            return int(random()*1600)

__all__ = ["ADC"]
