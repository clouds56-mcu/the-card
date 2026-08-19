"""Shared physical-design identity for generated KiCad sources."""


PROJECT_NAME = "the-card"
DESIGN_VERSION = "0.2.0"

# The full SemVer is the only maintained design identity. The shorter marking
# is derived for the limited PCB silkscreen area; it is not a second revision.
DESIGN_SERIES = ".".join(DESIGN_VERSION.split(".")[:2])

# These physical-fit flags are shared by the schematic and PCB generators so
# KiCad parity cannot drift between the two generated sources.
DNP_REFERENCES = frozenset({"C29"})
NON_ASSEMBLY_REFERENCES = frozenset({"L2"})
