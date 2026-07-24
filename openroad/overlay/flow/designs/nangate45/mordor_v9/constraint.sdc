# Relaxed clock: this experiment isolates AREA and static power, so we use a period
# everything meets comfortably (no timing-driven gate bloat polluting the deltas).
set clk_period 10.0

create_clock -name core_clock -period $clk_period [get_ports clk]

set non_clock_inputs [lsearch -inline -all -not -exact [all_inputs] [get_ports clk]]
set_input_delay  [expr $clk_period * 0.2] -clock core_clock $non_clock_inputs
set_output_delay [expr $clk_period * 0.2] -clock core_clock [all_outputs]
