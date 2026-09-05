import plotly.express as px
import streamlit as st
import pandas as pd

def get_high_dim_dashboard(df_input):
    """
    Generates high-dimensional Plotly figures for the Analytics tab.
    Translated and optimized for Streamlit integration.
    """
    # Preparation for Parallel Categories (Codes for color scaling)
    df_plot = df_input.copy()
    if 'archetype' in df_plot.columns:
        df_plot['archetype_id'] = df_plot['archetype'].astype('category').cat.codes

    # FIG 0: Logic pipeline (Color: Archetype)
    fig0 = px.parallel_categories(
        df_plot, dimensions=['teacher', 'student', 'archetype', 'v_ok_numeric'],
        color="archetype_id", color_continuous_scale=px.colors.qualitative.Plotly,
        title="Logic pipeline | Color: Archetype"
    )
    fig0.update_layout(coloraxis_showscale=False)

    # FIG 1: Logic pipeline (Color: Validation Result)
    fig1 = px.parallel_categories(
        df_plot, dimensions=['teacher', 'student', 'archetype', 'v_ok_numeric'],
        color="v_ok_numeric", color_continuous_scale="RdYlGn",
        title="Logic pipeline | Color: v_ok (Success)"
    )

    # FIG 2: Productivity by Model Pair
    fig2 = px.bar(
        df_plot, x="student", y="ms_per_word", color="v_ok_numeric",
        facet_col="teacher", barmode="group",
        title="Productivity teacher | Inference efficiency",
        template="plotly_dark"
    )

    # FIG 4 & 5: Impact Matrices
    fig3 = px.scatter_matrix(
        df_plot, dimensions=['lexical_density', 'ms_per_word', 'cognitive_load'],
        color="teacher", title="Teacher impact matrix",
        template="plotly_dark"
    )

    fig4 = px.scatter_matrix(
        df_plot, dimensions=['lexical_density', 'ms_per_word', 'cognitive_load'],
        color="teacher", symbol="student",
        title="Cross-model dependency matrix",
        template="plotly_dark"
    )
    fig4.update_traces(diagonal_visible=False, marker=dict(size=4))

    return [fig0, fig1, fig2, fig3, fig4]
