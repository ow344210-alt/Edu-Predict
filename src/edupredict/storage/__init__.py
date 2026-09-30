"""Storage layer.

``HDFS`` is the system of record required by the document; ``Impala`` provides
SQL access to the data stored there. Both are reached through their native
clients so no additional Python dependency is required.
"""

from .hdfs import HadoopCliClient, HdfsClient, HdfsProbeResult
from .impala import ImpalaClient, ImpalaProbeResult

__all__ = [
    "HadoopCliClient",
    "HdfsClient",
    "HdfsProbeResult",
    "ImpalaClient",
    "ImpalaProbeResult",
]
