from pyb import Pin
from utime import sleep_ms
from zacwire import ZACwire

Pin('Y1', Pin.OUT, value = 0)
Pin('Y3', Pin.OUT, value = 1)
zw = ZACwire('Y2')

while True:
	sleep_ms(125)
	print(zw.T())