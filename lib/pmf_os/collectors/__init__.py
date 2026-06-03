"""Deterministic data collectors for PMF Cohort OS.

Collectors do the bulk ETL from external systems (Amplitude, User 360, CredGPT)
into the PMF store. They are plain Python (no LLM) so they paginate, normalize,
and dedup reliably at cohort scale. The HTTP layer is injectable so tests run
against recorded fixtures, never live APIs.
"""
