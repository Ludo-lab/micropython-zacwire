from machine import Pin
from time import sleep_ms
from zacwire import ZACwire

Pin(17, Pin.OUT, value = 0)
zw = ZACwire(pin = 16, start = True)

while True:
	sleep_ms(125)
	print(f"{zw.T()},{zw.errorcount}")
