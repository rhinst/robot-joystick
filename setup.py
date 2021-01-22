from setuptools import setup, find_packages
import platform


setup(
  name='robot-joystick-service',
  version='0.1',
  description='Robot joystick service',
  url='https://github.com/rhinst/robot-joystick',
  author='Rob Hinst',
  author_email='rob@hinst.net',
  license='MIT',
  packages=find_packages(),
  install_requires = [
    'RPi.GPIO==0.7.0' if platform.platform().lower().find("armv7l") > -1 else 'Mock.GPIO==0.1.7',
    'Adafruit-ADS1x15==1.0.2'
  ],
  test_suite='tests',
  tests_require=['pytest==6.2.1'],
  entry_points={
    'console_scripts': ['joystick=joystick.main:main']
  }
)