# core/cluster_discovery.py
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import plotly.express as px

class ClusterDiscovery:
    """
    ClusterDiscovery provides a pipeline for unsupervised clustering of tabular data
    using KMeans, dimensionality reduction with PCA, and visualization with Plotly.

    The workflow includes:
    1. Filtering numeric features and ignoring common metadata fields.
    2. Handling missing values by imputing column means.
    3. Scaling features for clustering stability.
    4. Applying KMeans clustering to assign cluster IDs.
    5. Reducing dimensions with PCA for visualization.
    6. Generating interactive scatter plots with Plotly.

    References
    ----------
    - scikit-learn KMeans: https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html
    - scikit-learn PCA: https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html
    - scikit-learn StandardScaler: https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html
    - Plotly Express scatter: https://plotly.com/python/plotly-express/

    Attributes
    ----------
    n_clusters : int
        Number of clusters to form.
    scaler : StandardScaler
        Scaler instance used to normalize numeric features.
    pca : PCA
        PCA instance used for dimensionality reduction.
    model : KMeans
        KMeans clustering model.
    feature_names : list of str
        Names of numeric features used in clustering.
    """

    def __init__(self, n_clusters=3):
        """
        Initialize the ClusterDiscovery pipeline.

        Parameters
        ----------
        n_clusters : int, optional (default=3)
            Number of clusters to form with KMeans.
        """
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=2)
        self.model = KMeans(n_clusters=self.n_clusters, n_init='auto', random_state=42)
        self.feature_names = None

    def process_data(self, df):
        """
        Process a DataFrame to perform clustering and dimensionality reduction.

        Steps:
        - Filter numeric columns, ignoring coordinates and status fields.
        - Impute missing values with column means.
        - Scale features for clustering.
        - Fit KMeans and assign cluster IDs.
        - Apply PCA to reduce to 2D coordinates.

        Parameters
        ----------
        df : pandas.DataFrame
            Input DataFrame containing numeric and categorical features.

        Returns
        -------
        pandas.DataFrame
            DataFrame with added columns:
            - 'cluster_id': str cluster assignment
            - 'x', 'y': PCA coordinates
        """
        ignore = ['x', 'y', 'v_ok_numeric', 'val']
        numeric_df = df.select_dtypes(include=['number']).drop(columns=ignore, errors='ignore').copy()

        if numeric_df.empty:
            return df

        numeric_df = numeric_df.fillna(numeric_df.mean())
        self.feature_names = numeric_df.columns.tolist()

        scaled_data = self.scaler.fit_transform(numeric_df)
        df['cluster_id'] = self.model.fit_predict(scaled_data).astype(str)

        pca_coords = self.pca.fit_transform(scaled_data)
        df['x'] = pca_coords[:, 0]
        df['y'] = pca_coords[:, 1]

        return df

    def get_component_dependencies(self):
        """
        Retrieve PCA component loadings for feature dependencies.

        Returns
        -------
        tuple of pandas.Series or (None, None)
            - PC1_Weight: loadings for principal component 1
            - PC2_Weight: loadings for principal component 2

        Notes
        -----
        Loadings represent the contribution of each feature to the principal components.
        Useful for interpreting which features drive clustering separation.
        """
        if not hasattr(self.pca, 'components_') or self.feature_names is None:
            return None, None

        loadings = self.pca.components_.T * np.sqrt(self.pca.explained_variance_)
        loading_df = pd.DataFrame(
            loadings,
            columns=['PC1_Weight', 'PC2_Weight'],
            index=self.feature_names
        )
        return loading_df['PC1_Weight'], loading_df['PC2_Weight']

    def get_plotly_fig(self, df):
        """
        Generate an interactive Plotly scatter plot of clustered data.

        Parameters
        ----------
        df : pandas.DataFrame
            DataFrame containing 'x', 'y', and 'cluster_id' columns.

        Returns
        -------
        plotly.graph_objs._figure.Figure
            Scatter plot showing PCA-reduced clusters with hover metadata.

        Notes
        -----
        Hover tooltips display categorical/object columns for richer context.
        """
        fig = px.scatter(
            df, x='x', y='y', color='cluster_id',
            title="Archetype Clustering (PCA Reduction)",
            labels={'x': 'Principal Component 1', 'y': 'Principal Component 2'},
            hover_data=df.select_dtypes(include=['object']).columns
        )
        return fig
