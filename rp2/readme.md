# RP2040 Implementation of the ZACwire protocol for MicroPython

## Implementation

This use two state machines:

* The first one (`sm0`) reports the low pulses durations out of the TSic.
* The second state machine (`sm1`) raises an IRQ when it detects a high pulse longer than ~5 ms, which only happens in between temperature readings.
* The callback to that IRQ starts a DMA transfer which will copy the next twenty pulse durations reported by `sm0` and write them to a buffer array `dmabuf`. It also schedules the decoding of `dmabuf` into a temperature reading

## Usage

```py
from time import sleep_ms
from zacwire import ZACwire

zw = ZACwire(pin = 16, start = True, filter = 3, timeout = 3)

while True:
	sleep_ms(125)
	print(f"{zw.T():.2f},{zw.errorcount}")
```

The `start` argument (`False` by default) controls whether to start readings right away. Readings can be started and stopped using `ZACwire.start()` and `ZACwire.stop()` methods.

The `filter` argument defaults to `1`. Values larger than 1 indicate that a median filter should be applied over the last `N = filter` valid temperature readings. This will help ignore outliers but will also apply a low-pass filter to the readings: readings being performed at a rate of ~10 Hz, specifying `filter = 5` will filter the signal with a cutoff at about 2 Hz.

The `timeout` argument defaults to `3`. This indicates the maximum number of **consecutive** problematic readings (parity error, low or high range limits) before raising an exception. `ZACwire.errorcount` indicates how many such errors occurred (even if they did not cause an exception to be raised) since this instance of `ZACwire()` was initialized.

## Testing

To test long-term behavior, one may use the example above, which will report comma-separated values of temperature and `errorcount`. To plot these values in real time, one may use something like [polt](https://gitlab.com/nobodyinperson/python3-polt):

```sh
# /dev/cu.usbmodemXXXX is the port used to listen to the RP2040
polt add-source --cmd 'cat /dev/cu.usbmodemXXXX' --parser csv live
```
