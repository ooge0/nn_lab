import configparser
import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
from loguru import logger
from sentence_transformers import SentenceTransformer
from sklearn.decomposition import PCA


# -----------------------------
# LOAD KNOWLEDGE FILES
# -----------------------------
def load_chunks(folder_path):
    """
    Load text chunks from knowledge files.
    Each .txt file is treated as an archetype source.
    """
    data = []
    try:
        for file_name in os.listdir(folder_path):
            if not file_name.endswith(".txt"):
                continue

            archetype = file_name.replace(".txt", "")
            with open(os.path.join(folder_path, file_name), "r", encoding="utf-8") as f:
                text = f.read()

            # Split into chunks
            chunks = [c.strip() for c in text.split("\n") if len(c.strip()) > 0]

            # Calculate progress (0 to 1) for dynamics analysis
            total = len(chunks)
            for i, c in enumerate(chunks):
                if "|" in c:
                    category, content = c.split("|", 1)
                else:
                    category, content = "Uncategorized", c
                data.append(
                    {
                        "archetype": archetype,
                        "category": category.strip(),
                        "text": content.strip(),
                        "chunk_index": i,
                        "progress": i / total if total > 1 else 0,
                    }
                )
        logger.info(f"Loaded {len(data)} chunks from {folder_path}")
    except Exception as e:
        logger.error(f"Error loading chunks: {e}")
    return pd.DataFrame(data)


# -----------------------------
# CHUNK ANALYSIS
# -----------------------------


def analyze_chunks(df, output_dir):
    """
    Analyze loaded chunks with tabular and modern ML-style visualizations.
    Saves outputs as HTML for QA/ML inspection.
    """
    try:
        # 1. Tabular view
        table_html = df.head(50).to_html()  # preview first 50 rows
        with open(os.path.join(output_dir, "chunks_table.html"), "w", encoding="utf-8") as f:
            f.write(table_html)
        logger.info("Saved chunks_table.html (first 50 rows)")

        # 2. Distribution of chunk lengths
        df["length"] = df["text"].apply(len)
        fig_len = px.histogram(
            df, x="length", color="archetype", nbins=50, title="Chunk Length Distribution by Archetype"
        )
        fig_len.write_html(os.path.join(output_dir, "chunk_length_distribution.html"))
        logger.info("Saved chunk_length_distribution.html")

        # 3. Progress coverage per archetype
        fig_prog = px.box(df, x="archetype", y="progress", color="archetype", title="Narrative Progress Distribution")
        fig_prog.write_html(os.path.join(output_dir, "progress_distribution.html"))
        logger.info("Saved progress_distribution.html")

        # 4. Heatmap of chunk index vs length
        fig_heat = ff.create_2d_density(df["chunk_index"], df["length"], colorscale="Viridis")
        fig_heat.update_layout(title="Chunk Index vs Length Density")
        fig_heat.write_html(os.path.join(output_dir, "chunk_index_length_heatmap.html"))
        logger.info("Saved chunk_index_length_heatmap.html")

    except Exception as e:
        logger.error(f"Chunk analysis failed: {e}")


# -----------------------------
# EMBEDDINGS
# -----------------------------
def embed(df):
    """
    Generate semantic embeddings using SentenceTransformer "all-MiniLM-L6-v2".
    """
    try:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(df["text"].tolist(), show_progress_bar=True)
        logger.info(f"Generated embeddings for {len(df)} chunks")
        return np.array(embeddings)
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return np.array([])


# -----------------------------
# REDUCE DIMENSION
# -----------------------------
def reduce_dim(embeddings):
    """
    Reduce embeddings to 2D using PCA.
    """
    try:
        pca = PCA(n_components=2)
        coords = pca.fit_transform(embeddings)
        logger.info("Reduced embeddings to 2D with PCA")
        return coords
    except Exception as e:
        logger.error(f"PCA reduction failed: {e}")
        return np.array([])


# -----------------------------
# VISUALIZE AND SAVE HTML
# -----------------------------
def plot_with_dynamics(df, coords, output_dir):
    """
    Generate plots and save them as HTML files.
    """
    try:
        df["x"] = coords[:, 0]
        df["y"] = coords[:, 1]

        # PLOT 1: Scatter plot (Spatial distribution)
        fig1 = px.scatter(
            df, x="x", y="y", color="archetype", hover_data=["text"], title="1. Embedding Space Map (Clusters)"
        )
        fig1.write_html(os.path.join(output_dir, "embedding_space_map.html"))
        logger.info("Saved embedding_space_map.html")

        # PLOT 2: Violin + Box Plot (Analysis of deviations and variance)
        # This clearly shows outliers and the spread of each archetype
        fig2 = px.violin(
            df,
            y="x",
            x="archetype",
            color="archetype",
            box=True,
            points="all",
            hover_data=["text", "progress"],
            title="2. Deviation Analysis: Archetype Variance & Outliers (PCA 1)",
            labels={"x": "Semantic Value (PCA Axis 1)", "archetype": "Archetype"},
        )
        fig2.write_html(os.path.join(output_dir, "deviation_analysis.html"))
        logger.info("Saved deviation_analysis.html")

        # PLOT 3: Line plot (Dynamics across the file)
        fig3 = px.line(
            df,
            x="progress",
            y="x",
            color="archetype",
            hover_data=["text"],
            title="3. Narrative Dynamics (Vector drift from start to end)",
            labels={"progress": "File Start ———> File End", "x": "Semantic Vector (PCA 1)"},
        )
        fig3.update_traces(line=dict(width=1.5), marker=dict(size=4), mode="lines+markers")
        fig3.write_html(os.path.join(output_dir, "narrative_dynamics.html"))
        logger.info("Saved narrative_dynamics.html")

    except Exception as e:
        logger.error(f"Visualization failed: {e}")


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    CONFIG_PATH = os.path.join(BASE_DIR, "./config", "config.ini")
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    try:
        rag_knowledge_source = config["rag"]["rag_kb_source_path"]
        logger.info(f"RAG knowledge source path: {rag_knowledge_source}")
    except KeyError as e:
        logger.error(f"Missing config section or key: {e}")
        rag_knowledge_source = "knowledge/rag"  # fallback
        logger.warning(f"Using fallback path: {rag_knowledge_source}")

    KNOWLEDGE_PATH = os.path.join(BASE_DIR, rag_knowledge_source)

    try:
        results_dir = os.path.join(BASE_DIR, "results", "knowledge_graph_analyses")
        os.makedirs(results_dir, exist_ok=True)
        logger.info(f"Results directory ready: {results_dir}")

        df = load_chunks(KNOWLEDGE_PATH)
        logger.info(f"Loaded chunks: {len(df)}")
        analyze_chunks(df, results_dir)

        embeddings = embed(df)
        coords = reduce_dim(embeddings)

        if embeddings.size > 0 and coords.size > 0:
            plot_with_dynamics(df, coords, results_dir)
            logger.info(f"HTML plots saved to: {results_dir}")
        else:
            logger.warning("Skipping visualization due to missing embeddings or coords")
    except KeyError as e:
        logger.error(f"Missing config section or key: {e}")
        rag_knowledge_source = "knowledge/rag"  # fallback
        logger.warning(f"Using fallback path: {rag_knowledge_source}")
