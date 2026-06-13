import streamlit as st
import pandas as pd
import plotly.express as px
from loguru import logger

class Taxonomy_Failure_metrics:
    """
    Failure Taxonomy metrics and visualization.

    Provides a Streamlit tab called 'Failure Taxonomy' that processes
    and plots details for categories such as:
      - Hallucination
      - Refusal
      - Instruction Drift
      - Context Loss
      - Toxicity
      - Retrieval Failure
      - Reasoning Error

    References:
      - HELM (Holistic Evaluation of Language Models)
      - Responsible AI guidelines (Microsoft, Google, OpenAI)
      - Common error taxonomies in NLP research
    """

    def __init__(self, df: pd.DataFrame):
        """
        Initialize with a DataFrame containing evaluation logs.
        Expected columns include:
          - 'batch', 'steps', 'archetype', 'bias'
          - 'output', 'sentiment', 'lexical_density', 'cognitive_load'
          - 'coherence', 'semantic_overlap', etc.
        """
        self.df = df

    def render_tab(self):
        """Render the Failure Taxonomy tab in Streamlit."""
        st.subheader("Failure Taxonomy")

        # Raw table preview
        st.write("### Raw Evaluation Logs")
        st.dataframe(self.df.head(50))

        # Category counts (if you annotate failures)
        if "failure_category" in self.df.columns:
            st.write("### Failure Category Counts")
            counts = self.df["failure_category"].value_counts().reset_index()
            counts.columns = ["Category", "Count"]
            st.bar_chart(counts.set_index("Category"))

        # Sentiment distribution
        st.write("### Sentiment Distribution")
        fig_sent = px.histogram(
            self.df,
            x="sentiment",
            color="archetype",
            title="Sentiment distribution across archetypes"
        )
        st.plotly_chart(fig_sent, use_container_width=True)

        # Lexical density vs cognitive load
        st.write("### Lexical Density vs Cognitive Load")
        fig_ld = px.scatter(
            self.df,
            x="lexical_density",
            y="cognitive_load",
            color="archetype",
            hover_data=["batch", "steps", "bias"],
            title="Lexical Density vs Cognitive Load"
        )
        st.plotly_chart(fig_ld, use_container_width=True)

        # Coherence vs semantic overlap
        st.write("### Coherence vs Semantic Overlap")
        fig_coh = px.scatter(
            self.df,
            x="coherence",
            y="semantic_overlap",
            color="archetype",
            hover_data=["batch", "steps"],
            title="Coherence vs Semantic Overlap"
        )
        st.plotly_chart(fig_coh, use_container_width=True)

        logger.info("Failure Taxonomy tab rendered successfully")
