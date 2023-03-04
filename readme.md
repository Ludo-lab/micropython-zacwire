# ZACwire protocol for MicroPython

MicroPython implementation of the ZACwire protocol used in TSic 506F temperature sensors.

The pyboard implementation is based on IRQs and a Timer, and seems to work reliably.

The RP2040 implementation uses two PIO state machines and also seems quite reliable. Thanks to Robert Hammelrath for his [RP2040 Examples](https://github.com/robert-hh/RP2040-Examples).