"""
core.adapters
=============

Concrete implementations of ``core.domain`` interfaces: ``OllamaClient``,
``JSONLStore``, ``SQLiteRepo``, ``StructuredJudge``, ``NaivePromptStrategy``, and
the RAG adapters. Callers depend on ``core.domain`` interfaces, never on
these concrete classes directly.
"""
