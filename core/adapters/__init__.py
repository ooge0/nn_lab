"""
core.adapters
=============

Concrete implementations of ``core.domain`` interfaces: ``OllamaClient``,
``JSONLStore``, ``SQLiteRepo``, ``StructuredJudge``, ``NaivePromptStrategy``,
``Neo4jGraphRepo``, and the RAG adapters. Callers depend on ``core.domain`` interfaces, never on
these concrete classes directly.
"""
