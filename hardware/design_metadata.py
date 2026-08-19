"""Shared physical-design identity for generated KiCad sources."""


PROJECT_NAME = "the-card"
HARDWARE_REVISION = "B"

# These physical-fit flags are shared by the schematic and PCB generators so
# KiCad parity cannot drift between the two generated sources.
DNP_REFERENCES = frozenset({"C29"})
NON_ASSEMBLY_REFERENCES = frozenset({"L2"})
