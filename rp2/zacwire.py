from array import array
import rp2
from machine import Pin
import rp2_util
from micropython import schedule


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


@rp2.asm_pio(autopush = True, push_thresh = 32)
def detect_long_pulse():
    label('reset_countdown')            # <── reset countdown ───────┐
    set(x, 31)                          #    x = 31                  │
    wait(1, pin, 0)                     #    wait for pin to go high │
    label('not_long_enough')            # <─────────────────┐        │
    jmp(pin, 'leapfrog')                # ── if pin high ─┐ │        │
    jmp('reset_countdown')              # ── else ────────┼─┘        │
    label('leapfrog')                   # <───────────────┘          │
    jmp(x_dec, 'not_long_enough') [13]  # ── if x>0: x -= 1 ─────────┘
    irq(rel(0))                         #    raise irq
    wait(0, pin, 0)                     #    wait for pin to go low


class ZACwire():

	def __init__(self, pin, sm = (0,1), start = False, filter = 1, timeout = 3):
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
		self.bitlen = 20
		self.timeout_counter = 0
		self.timeout_limit = timeout
		self.filter = filter
		self.pin = Pin(pin, Pin.IN)	
		self.dmabuf = array('l', [0]*self.buflen)
		self.bits = array('i', [0]*self.bitlen)
		self.rawT = array('f', [0] * filter)
		self.sm0 = rp2.StateMachine(sm[0], count_pulse_len,   in_base = self.pin, jmp_pin = self.pin, freq = 3_000_000)
		self.sm1 = rp2.StateMachine(sm[1], detect_long_pulse, in_base = self.pin, jmp_pin = self.pin, freq = 100_000)
		self._cb_irq1 = self.cb_irq1
		self._decode = self.decode
		self.sm1.irq(self._cb_irq1)
		if start:
			self.sm0.active(1)
			self.sm1.active(1)

	@micropython.native
	def cb_irq1(self, _):
		rp2_util.sm_dma_get(0, 0, self.dmabuf, len(self.dmabuf))
		schedule(self._decode, None)

	@micropython.native
	def T(self):
		if self.sm0.active():
			return sorted(self.rawT)[self.filter // 2] / 2047 * 70 - 10
		raise ZACwireNotRunning
		
	@micropython.native
	def decode(self, _):  # takes ~430 us
		threshold = self.dmabuf[0]

		for j in range(self.bitlen):
			self.bits[j] = self.dmabuf[j] > threshold
		
		self.rawT[:-1] = self.rawT[1:]

		parity = self.bits[-2]
		for k in range(7):
			parity += self.bits[-3-k]
		if (parity % 2) != self.bits[-1]:
			self.timeout_counter += 1
			self.errorcount += 1
			if self.timeout_counter >= self.timeout_limit:
				print(self.buf)
				raise ZACwireWrongParity
			return None

		parity = self.bits[-12]
		for k in range(2):
			parity += self.bits[-13-k]
		if (parity % 2) != self.bits[-11]:
			self.timeout_counter += 1
			self.errorcount += 1
			if self.timeout_counter >= self.timeout_limit:
				print(self.buf)
				raise ZACwireWrongParity
			return None
	
		t = self.bits[-2]
		for k in range(7):
			t += self.bits[-3-k] << k+1
		for k in range(3):
			t += self.bits[-12-k] << k+8
		
		if t == 0:
			self.timeout_counter += 1
			self.errorcount += 1
			if self.timeout_counter >= self.timeout_limit:
				raise ZACwireLowRangeLimit
		elif t == 2047:
			self.timeout_counter += 1
			self.errorcount += 1
			if self.timeout_counter >= self.timeout_limit:
				raise ValuZACwireHighRangeLimiteError		
		else:
			self.timeout_counter = 0
			self.rawT[-1] = t

	def start(self):
		self.sm0.active(1)
		self.sm1.active(1)

	def stop(self):
		self.sm0.active(0)
		self.sm1.active(0)
