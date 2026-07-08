"""Operational scripts for PipeGuard (data fetch, one-off maintenance).

Kept as an importable package so the pure, network-free logic of scripts like
``fetch_giab_hg002`` can be unit-tested offline (``tests/test_fetch_giab.py``)
and strictly type-checked, without ever running a live download here. These
scripts run *elsewhere* (a machine with the bioconda/container genomics
toolchain); this package is not part of the installable ``pipeguard`` library.
"""
