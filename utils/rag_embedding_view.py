import os
import numpy as np
import pandas as pd
import plotly.express as px
from sentence_transformers import SentenceTransformer
from sklearn.decomposition import PCA


# -----------------------------
# LOAD KNOWLEDGE FILES
# -----------------------------
def load_chunks(folder_path):
    data = []
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
            data.append({
                "archetype": archetype,
                "text": c,
                "chunk_index": i,
                "progress": i / total if total > 1 else 0
            })
    return pd.DataFrame(data)


# -----------------------------
# EMBEDDINGS
# -----------------------------
def embed(df):
    # Using all-MiniLM-L6-v2 for semantic vectors
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(df["text"].tolist(), show_progress_bar=True)
    return np.array(embeddings)


# -----------------------------
# REDUCE DIMENSION
# -----------------------------
def reduce_dim(embeddings):
    # Reduce 384 dimensions to 2 for visualization
    pca = PCA(n_components=2)
    return pca.fit_transform(embeddings)


# -----------------------------
# VISUALIZE (ENHANCED)
# -----------------------------
def plot_with_dynamics(df, coords):
    df["x"] = coords[:, 0]
    df["y"] = coords[:, 1]

    # PLOT 1: Scatter plot (Spatial distribution)
    fig1 = px.scatter(
        df, x="x", y="y", color="archetype",
        hover_data=["text"],
        title="1. Embedding Space Map (Clusters)"
    )
    fig1.show()

    # PLOT 2: Violin + Box Plot (Analysis of deviations and variance)
    # This clearly shows outliers and the spread of each archetype
    fig2 = px.violin(
        df,
        y="x",
        x="archetype",
        color="archetype",
        box=True,  # Show box plot inside violin
        points="all",  # Show all points to see outliers clearly
        hover_data=["text", "progress"],
        title="2. Deviation Analysis: Archetype Variance & Outliers (PCA 1)",
        labels={"x": "Semantic Value (PCA Axis 1)", "archetype": "Archetype"}
    )
    fig2.show()

    # PLOT 3: Line plot (Dynamics across the file)
    fig3 = px.line(
        df,
        x="progress",
        y="x",
        color="archetype",
        hover_data=["text"],
        title="3. Narrative Dynamics (Vector drift from start to end)",
        labels={"progress": "File Start ———> File End", "x": "Semantic Vector (PCA 1)"}
    )
    fig3.update_traces(line=dict(width=1.5), marker=dict(size=4), mode='lines+markers')
    fig3.show()


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    # Keeping your original path logic
    BASE_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    KNOWLEDGE_PATH = os.path.join(BASE_DIR, "knowledge")

    # Execution flow
    df = load_chunks(KNOWLEDGE_PATH)
    print(f"Loaded chunks: {len(df)}")

    embeddings = embed(df)
    coords = reduce_dim(embeddings)

    # Run enhanced visualizations
    plot_with_dynamics(df, coords)
