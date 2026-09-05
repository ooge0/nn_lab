"""
core.domain
===========

Entities and interfaces (Protocols/ABCs) for the nn_lab evaluation pipeline.

Notes
-----
Zero framework imports allowed in this package -- no Streamlit, FastAPI, Ollama,
or OpenAI SDK imports. ``core/adapters`` implements these interfaces;
``core/domain`` must never import from ``core/adapters``, ``api``, or ``web``.
"""
