from array import array
from machine import Pin
from micropython import schedule
import rp2, gc


class ZACwireNotRunning(Exception):
	pass

class ZACwireWrongParity(Exception):
	pass

class ZACwireLowRangeLimit(Exception):
	pass

class ZACwireHighRangeLimit(Exception):
	pass


@rp2.asm_pio(autopush = True, push_thresh = 32)
def count_pulse_len():
    set(x, 0)             #    x = 0
    wait(0, pin, 0)       #    wait for pin to go low
    label('falling')      # <───────────────┐
    jmp(x_dec, 'next')    # ── x -= 1 ──┐   │
    label('next')         # <───────────┘   │
    jmp(pin, 'leapfrog')  # ── if pin high ─┼─┐
    jmp('falling')        # ── else ────────┘ │
    label('leapfrog')     # <─────────────────┘
    in_(x, 32)            #    shift x to ISR
    irq(rel(0))           #    raise irq


@rp2.asm_pio(autopush = True, push_thresh = 32)
def detect_long_pulse():
    label('reset_countdown')            # <── reset countdown ───────┐
    set(x, 31)                          #    x = 31                  │
    wait(1, pin, 0)                     #    wait for pin to go high │
    label('not_long_enough')            # <───────────────────┐      │
    jmp(pin, 'leapfrog')                # ── if pin high ─┐   │      │
    jmp('reset_countdown')              # ── else ────────┼───┼──────┘
    label('leapfrog')                   # <───────────────┘   │
    jmp(x_dec, 'not_long_enough') [13]  # ── if x>0: x -= 1 ──┘
    irq(rel(0))                         #    raise irq
    wait(0, pin, 0)                     #    wait for pin to go low


class ZACwire():

	def __init__(self, pin, sm = (0,1), start = False, filter = 1, timeout = 4):
		"""
		pin     : which pin to read
		sm      : which state machines to use
		          - sm[0] is used for timing low pulses.
		          - sm[1] is used for initiating DMA transfers.
		start   : whether to start the state machines right away
		filter  : width of the window over which a median filter is applied
		timeout : max number of error readings before raising an exception
		"""
		self.errorcount = -1
		self.buflen = 20
		self.bufpos = 0
		self.bitlen = 20
		self.timeout_counter = 0
		self.timeout_limit = timeout
		self.filter = filter
		self.pin = Pin(pin, Pin.IN)	
		self.buf = array('l', [0]*self.buflen)
		self.savedbuf = array('l', [0]*self.buflen)
		self.bits = array('i', [0]*self.bitlen)
		self.rawT = array('f', [0] * filter)
		self.sm0 = rp2.StateMachine(sm[0], count_pulse_len,   in_base = self.pin, jmp_pin = self.pin, freq = 3_000_000)
		self.sm1 = rp2.StateMachine(sm[1], detect_long_pulse, in_base = self.pin, jmp_pin = self.pin, freq = 100_000)
		self._decode = self.decode
		self.sm0.irq(self.cb_irq0)
		self.sm1.irq(self.cb_irq1)
		if start:
			self.sm0.active(1)
			self.sm1.active(1)

	@micropython.native
	def cb_irq0(self, _): # ~40 us
		self.buf[self.bufpos] = self.sm0.get()
		self.bufpos = self.bufpos + 1

	@micropython.native
	def cb_irq1(self, _): # 35-60 us
		self.savedbuf = self.buf[:]
		self.bufpos = 0
		schedule(self._decode, None)

	@micropython.native
	def T(self):
		if self.sm0.active():
			return sorted(self.rawT)[self.filter // 2] / 2047 * 70 - 10
		raise ZACwireNotRunning
		
	@micropython.native
	def decode(self, _):
		gc.collect()
		threshold = self.savedbuf[0]
		bits = self.bits
		buf2 = self.savedbuf

		for j in range(self.bitlen):
			bits[j] = buf2[j] > threshold
		
		parity = bits[-2]
		for k in range(7):
			parity += bits[-3-k]
		if (parity % 2) != bits[-1]:
			self.timeout_counter += 1
			self.errorcount += 1
			if self.timeout_counter >= self.timeout_limit:
				raise ZACwireWrongParity
			return None

		parity = bits[-12]
		for k in range(2):
			parity += bits[-13-k]
		if (parity % 2) != bits[-11]:
			self.timeout_counter += 1
			self.errorcount += 1
			if self.timeout_counter >= self.timeout_limit:
				raise ZACwireWrongParity
			return None
	
		t = bits[-2]
		for k in range(7):
			t |= bits[-3-k] << k+1
		for k in range(3):
			t |= bits[-12-k] << k+8
		
		if t == 0:
			self.timeout_counter += 1
			self.errorcount += 1
			if self.timeout_counter >= self.timeout_limit:
				raise ZACwireLowRangeLimit
		elif t == 2047:
			self.timeout_counter += 1
			self.errorcount += 1
			if self.timeout_counter >= self.timeout_limit:
				raise ZACwireHighRangeLimit
		else:
			self.timeout_counter = 0
			rawT = self.rawT
			rawT[:-1] = rawT[1:]
			rawT[-1] = t

	def start(self):
		self.sm0.active(1)
		self.sm1.active(1)

	def stop(self):
		self.sm0.active(0)
		self.sm1.active(0)
