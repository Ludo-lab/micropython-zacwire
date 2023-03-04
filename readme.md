# ZACwire protocol for MicroPython

MicroPython implementation of the ZACwire protocol used in the [TSic 506F](https://docs.rs-online.com/e2fb/0900766b81690bb9.pdf) temperature sensor. One useful property of these sensors is that their nominal accuracy is excellent (±0.1 °C), which is necessary for some scientific applications (e.g., ensuring precise *and* accurate control of a chemical reaction's temperature).

The pyboard implementation is based on IRQs and a Timer, and seems to work reliably.

The RP2040 implementation uses two PIO state machines and also seems quite reliable. Thanks to Robert Hammelrath for his [RP2040 Examples](https://github.com/robert-hh/RP2040-Examples).