export PLATFORM         = nangate45

export DESIGN_NAME      = mordor_v9
export DESIGN_NICKNAME  = mordor_v9

export VERILOG_FILES    = $(sort $(wildcard ./designs/src/$(DESIGN_NICKNAME)/*.v))
export SDC_FILE         = ./designs/$(PLATFORM)/$(DESIGN_NICKNAME)/constraint.sdc

# large, sparse die: the CAM mode (M x PROQ comparators) can be cell-heavy
export DIE_AREA  = 0 0 2000 2000
export CORE_AREA = 100 100 1900 1900

export TNS_END_PERCENT  = 100
