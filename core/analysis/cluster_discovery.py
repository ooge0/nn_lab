# core/cluster_discovery.py
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import plotly.express as px


class ClusterDiscovery:
    def __init__(self, n_clusters=3):
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=2)
        self.model = KMeans(n_clusters=self.n_clusters, n_init='auto', random_state=42)
        self.feature_names = None  # <--- Store names here

    def process_data(self, df):
        # 1. Filter out non-numeric and coordinates immediately
        # We also drop common ID/status fields to keep the clustering 'clean'
        ignore = ['x', 'y', 'v_ok_numeric', 'val']
        numeric_df = df.select_dtypes(include=['number']).drop(columns=ignore, errors='ignore').copy()

        if numeric_df.empty:
            return df

        # 2. Handle NaNs
        numeric_df = numeric_df.fillna(numeric_df.mean())

        # 3. Save the exact column names used for the math
        self.feature_names = numeric_df.columns.tolist()  # <--- CRITICAL

        # 4. Scale & Cluster
        scaled_data = self.scaler.fit_transform(numeric_df)
        df['cluster_id'] = self.model.fit_predict(scaled_data).astype(str)

        # 5. PCA
        pca_coords = self.pca.fit_transform(scaled_data)
        df['x'] = pca_coords[:, 0]
        df['y'] = pca_coords[:, 1]

        return df

    def get_component_dependencies(self):  # <--- Remove 'feature_names' argument
        if not hasattr(self.pca, 'components_') or self.feature_names is None:
            return None, None

        loadings = self.pca.components_.T * np.sqrt(self.pca.explained_variance_)

        # Now shapes will always match because we use self.feature_names
        loading_df = pd.DataFrame(
            loadings,
            columns=['PC1_Weight', 'PC2_Weight'],
            index=self.feature_names
        )

        return loading_df['PC1_Weight'], loading_df['PC2_Weight']

    def get_plotly_fig(self, df):
        """Generates the interactive Plotly scatter plot."""
        fig = px.scatter(
            df, x='x', y='y', color='cluster_id',
            title="Psychotype Clustering (PCA Reduction)",
            labels={'x': 'Principal Component 1', 'y': 'Principal Component 2'},
            hover_data=df.select_dtypes(include=['object']).columns  # Show text data on hover
        )
        return fig