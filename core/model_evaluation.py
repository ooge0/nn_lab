# core/model_evaluation.py

import numpy as np
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from sklearn.linear_model import LogisticRegression

from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report,
)


class ModelEvaluation:
    """
    Evaluates how well linguistic / neuro metrics
    predict a target label.

    Example target:
        - hallucination
        - truthful_response
        - anomaly
        - psychotype
    """

    def __init__(self, target_column="label"):
        self.target_column = target_column

        self.scaler = StandardScaler()

        # Simple interpretable baseline model
        self.model = LogisticRegression(
            max_iter=1000,
            random_state=42
        )

        self.feature_names = None

    # ---------------------------------------------------
    # PREPARE DATA
    # ---------------------------------------------------
    def prepare_data(self, df):
        """
        Extract numeric features and target labels.
        """

        if self.target_column not in df.columns:
            raise ValueError(
                f"Target column '{self.target_column}' not found."
            )

        # Remove non-feature columns
        ignore = [
            self.target_column,
            "x",
            "y",
            "cluster_id",
            "text",
        ]

        X = (
            df.select_dtypes(include=["number"])
            .drop(columns=ignore, errors="ignore")
            .copy()
        )

        y = df[self.target_column]

        # Fill NaNs
        X = X.fillna(X.mean())

        self.feature_names = X.columns.tolist()

        return X, y

    # ---------------------------------------------------
    # TRAIN + EVALUATE
    # ---------------------------------------------------
    def evaluate(self, df, test_size=0.2):
        """
        Main evaluation pipeline.
        """

        X, y = self.prepare_data(df)

        if len(X) < 10:
            raise ValueError(
                "Dataset too small for evaluation."
            )

        # ---------------------------------------------
        # TRAIN / TEST SPLIT
        # ---------------------------------------------
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=test_size,
            random_state=42,
            stratify=y
        )

        # ---------------------------------------------
        # SCALE
        # ---------------------------------------------
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # ---------------------------------------------
        # TRAIN
        # ---------------------------------------------
        self.model.fit(X_train_scaled, y_train)

        # ---------------------------------------------
        # PREDICT
        # ---------------------------------------------
        y_pred = self.model.predict(X_test_scaled)

        # Probability estimates for ROC-AUC
        y_prob = self.model.predict_proba(X_test_scaled)

        # ---------------------------------------------
        # METRICS
        # ---------------------------------------------
        precision = precision_score(y_test, y_pred, average="macro")
        recall = recall_score(y_test, y_pred, average="macro")
        f1 = f1_score(y_test, y_pred, average="macro")

        roc_auc = roc_auc_score(
            y_test,
            y_prob,
            multi_class="ovr",
            average="macro"
        )

        # ---------------------------------------------
        # CONFUSION MATRIX
        # ---------------------------------------------
        cm = confusion_matrix(y_test, y_pred)

        # ---------------------------------------------
        # FEATURE IMPORTANCE
        # (Logistic Regression weights)
        # ---------------------------------------------
        importance_df = pd.DataFrame({
            "feature": self.feature_names,
            "weight": self.model.coef_[0]
        })

        importance_df["abs_weight"] = importance_df["weight"].abs()

        importance_df = importance_df.sort_values(
            by="abs_weight",
            ascending=False
        )

        # ---------------------------------------------
        # FINAL RESULT
        # ---------------------------------------------
        return {
            "precision": round(float(precision), 3),
            "recall": round(float(recall), 3),
            "f1_score": round(float(f1), 3),
            "roc_auc": round(float(roc_auc), 3),

            "confusion_matrix": cm.tolist(),

            "classification_report":
                classification_report(y_test, y_pred),

            "top_features":
                importance_df.head(10).to_dict("records"),
        }

    # ---------------------------------------------------
    # PREDICT SINGLE SAMPLE
    # ---------------------------------------------------
    def predict(self, feature_df):
        """
        Predict on new unseen data.
        """

        scaled = self.scaler.transform(feature_df)

        prediction = self.model.predict(scaled)
        probability = self.model.predict_proba(scaled)

        return {
            "prediction": prediction.tolist(),
            "probability": probability.tolist(),
        }