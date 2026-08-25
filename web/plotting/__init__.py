"""
web.plotting
==============

Presentation-only Plotly figure construction for Stage 8 (``tab_analytics``).
Deliberately kept out of ``core/services`` -- this is chart construction, not
business logic, matching the "moves into web/" split the refactor plan calls
for. Every figure here is a plain ``plotly.graph_objects.Figure``, fully
independent of Streamlit or FastAPI; ``api/routers/analytics.py`` is the only
caller, converting figures to embeddable HTML fragments via
:func:`web.plotting.render.figure_to_div`.
"""
