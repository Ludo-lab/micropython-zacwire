from pyb import ExtInt, Pin, micros, Timer
from utime import ticks_diff
from array import array


class ZACwire():

	def __init__(self, pin, timer = 1):
		self.timer = Timer(timer)
		self.bufloc = 0
		self.buflen = 41
		self.buf = array('l', [0]*self.buflen)
		self.dt = array('l', [0]*(self.buflen-1))
		self._cb_irq = self.cb_irq
		self._cb_timer = self.cb_timer
		self.ei = ExtInt(pin, ExtInt.IRQ_RISING_FALLING, Pin.PULL_NONE, self._cb_irq)
		self.bitslen = 13
		self.bits = array('b', [0]*self.bitslen)
		self.rawT = 0

	def cb_irq(self, _):
		# this takes ~35 us if self.bufloc = 0, ~15 us otherwise
		self.buf[self.bufloc] = micros()
		if self.bufloc == 0:
			self.timer.init(freq = 200, callback = self._cb_timer)
		self.bufloc += 1

	def cb_timer(self, _):
		self.timer.deinit()
		self.bufloc = 0
		self.decode()

	def decode(self):
		for k in range(self.buflen-1):
			self.dt[k] = ticks_diff(self.buf[k+1], self.buf[k])

		threshold = self.dt[0]

		for j in range(9):
			self.bits[-1-j] = self.dt[-(j+1)*2] < threshold
		for j in range(4):
			self.bits[-10-j] = self.dt[-(j+11)*2] < threshold

		# TODO: ADD PARITY CHECK
		
		self.rawT = self.bits[11]
		for k in range(7):
			self.rawT += self.bits[10-k] * 2**(k+1)
		for k in range(3):
			self.rawT += self.bits[2-k] * 2**(k+8)
		
	def T(self):
		return self.rawT / 2047 * 70 - 10

	# TODO: ADD START/STOP METHODS
