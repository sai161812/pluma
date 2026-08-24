"""tests.benchmarks — Performance latency benchmarks and memory soak tests for PLUMA.

Spec §22, §23:
- FAST route latency: < 50ms target.
- Resident core idle memory: < 30MB target.
- 1,000 task soak test with zero handle/memory leakage.
"""
