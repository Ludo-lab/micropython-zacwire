from pyb import ExtInt, Pin, micros, Timer
from utime import ticks_diff
from array import array
from micropython import schedule


class ZACwire():

	# values chosen to yield apparent temperatures below absolute zero:
	_NO_READING_YET  = -97174   # yields apparent temperature around -3333
	_WRONG_PARITY    = -64685   # yields apparent temperature around -2222
	_LOW_RANGE_LIMIT = -32196   # yields apparent temperature around -1111
	_HIGH_RANGE_LIMIT = -292107 # yields apparent temperature around -9999

	def __init__(self, pin, timer = 1):
		self.timer = Timer(timer)
		self.bufloc = 0
		self.buflen = 41
		self.buf = array('l', [0]*self.buflen)
		self.dt = array('l', [0]*(self.buflen-1))
		self._cb_irq = self.cb_irq
		self._cb_timer = self.cb_timer
		self._decode = self.decode
		self.ei = ExtInt(pin, ExtInt.IRQ_RISING_FALLING, Pin.PULL_NONE, self._cb_irq)
		self.bitslen = 14
		self.bits = array('b', [0]*self.bitslen)
		self.rawT = ZACwire._NO_READING_YET

	def cb_irq(self, _):
		# this takes ~35 us if self.bufloc = 0, ~15 us otherwise
		self.buf[self.bufloc] = micros()
		if self.bufloc == 0:
			self.timer.init(freq = 200, callback = self._cb_timer)
		self.bufloc += 1

	def cb_timer(self, _):
		# this takes ~1 ms
		self.timer.deinit()
		self.bufloc = 0
		schedule(self._decode, None)

	def decode(self, _):
		for k in range(self.buflen-1):
			self.dt[k] = ticks_diff(self.buf[k+1], self.buf[k])

		threshold = self.dt[0]

		for j in range(self.bitslen):
			self.bits[-1-j] = self.dt[-(j+1)*2] < threshold

		parity = self.bits[-2]
		for k in range(7):
			parity += self.bits[-3-k]
		if (parity % 2) != self.bits[-1]:
			self.rawT = ZACwire._WRONG_PARITY
			return None

		parity = self.bits[-12]
		for k in range(2):
			parity += self.bits[-13-k]
		if (parity % 2) != self.bits[-11]:
			self.rawT = ZACwire._WRONG_PARITY
			return None
	
		self.rawT = self.bits[-2]
		for k in range(7):
			self.rawT += self.bits[-3-k] << k+1
		for k in range(3):
			self.rawT += self.bits[-12-k] << k+8

	def T(self):
		if self.rawT == 0:
			return ZACwire._LOW_RANGE_LIMIT
		elif self.rawT == 2047:
			return ZACwire._HIGH_RANGE_LIMIT
		return self.rawT / 2047 * 70 - 10

	# TODO: ADD START/STOP METHODS
