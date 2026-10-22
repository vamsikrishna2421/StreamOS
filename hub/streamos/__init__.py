"""StreamOS local streaming hub.

A household media hub that relays authorized upstream streams to multiple
local devices (shared viewing) and allocates distinct authorized sources
for independent viewing, under configurable concurrency limits.

Everything in this package operates on local or explicitly configured
sources only. It never probes, enumerates, or authenticates against a
third-party provider on its own.
"""

__version__ = "0.3.0"
