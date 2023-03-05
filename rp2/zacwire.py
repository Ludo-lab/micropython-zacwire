from array import array
from machine import Pin
from micropython import schedule
import rp2, gc


class ZACwireNotRunning(Exception):
	pass

class ZACwireWrongParity(Exception):
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

		self._buf = memoryview(self.buf)
		self._savedbuf = memoryview(self.savedbuf)
		self._bits = memoryview(self.bits)
		self._rawT = memoryview(self.rawT)

		self.sm0 = rp2.StateMachine(sm[0], count_pulse_len,   in_base = self.pin, jmp_pin = self.pin, freq = 3_000_000)
		self.sm1 = rp2.StateMachine(sm[1], detect_long_pulse, in_base = self.pin, jmp_pin = self.pin, freq = 100_000)
		self._decode = self.decode
		self.sm0.irq(self.cb_irq0)
		self.sm1.irq(self.cb_irq1)
		if start:
			self.sm0.active(1)
			self.sm1.active(1)

	@micropython.viper
	def cb_irq0(self, _) -> int: # ~40 us
		self._buf[self.bufpos] = int(self.sm0.get())
		self.bufpos = int(self.bufpos) + 1

	@micropython.native
	def cb_irq1(self, _): # 35-60 us
		self._savedbuf[:] = self._buf[:]
		self.bufpos = 0
		schedule(self._decode, 0)

	@micropython.native
	def T(self):
		if self.sm0.active():
			return sorted(self.rawT)[self.filter // 2] / 2047 * 70 - 10
		raise ZACwireNotRunning
		
	@micropython.viper
	def decode(self, _: int) -> int:
		gc.collect()
		bits = self._bits
		buf2 = self._savedbuf
		threshold = int(buf2[0])

		bits[6] = int(buf2[6]) > threshold
		bits[7] = int(buf2[7]) > threshold
		bits[8] = int(buf2[8]) > threshold
		bits[9] = int(buf2[9]) > threshold

		bits[11] = int(buf2[11]) > threshold
		bits[12] = int(buf2[12]) > threshold
		bits[13] = int(buf2[13]) > threshold
		bits[14] = int(buf2[14]) > threshold
		bits[15] = int(buf2[15]) > threshold
		bits[16] = int(buf2[16]) > threshold
		bits[17] = int(buf2[17]) > threshold
		bits[18] = int(buf2[18]) > threshold
		bits[19] = int(buf2[19]) > threshold
		
		parity = (
			int(bits[11])
			+ int(bits[12])
			+ int(bits[13])
			+ int(bits[14])
			+ int(bits[15])
			+ int(bits[16])
			+ int(bits[17])
			+ int(bits[18])
			)
		if (parity % 2) != int(bits[19]):
			self.timeout_counter = int(self.timeout_counter) + 1
			self.errorcount = int(self.errorcount) + 1
			if int(self.timeout_counter) >= int(self.timeout_limit):
				raise ZACwireWrongParity
			return None

		parity = (
			int(bits[6])
			+ int(bits[7])
			+ int(bits[8])
			)
		if (parity % 2) != int(bits[9]):
			self.timeout_counter = int(self.timeout_counter) + 1
			self.errorcount = int(self.errorcount) + 1
			if int(self.timeout_counter) >= int(self.timeout_limit):
				raise ZACwireWrongParity
			return None
	
		t = (
			int(bits[18])
			| (int(bits[17]) << 1)
			| (int(bits[16]) << 2)
			| (int(bits[15]) << 3)
			| (int(bits[14]) << 4)
			| (int(bits[13]) << 5)
			| (int(bits[12]) << 6)
			| (int(bits[11]) << 7)
			| (int(bits[8])  << 8)
			| (int(bits[7])  << 9)
			| (int(bits[6])  << 10)
			)
				
		self.timeout_counter = 0
		rawT = self._rawT
		n = int(len(self._rawT)) - 1
		_ = int(0)
		while _ < n:
			rawT[_] = rawT[_+1]
			_ = _ + 1

		rawT[-1] = int(t)

	def start(self):
		self.sm0.active(1)
		self.sm1.active(1)

	def stop(self):
		self.sm0.active(0)
		self.sm1.active(0)
