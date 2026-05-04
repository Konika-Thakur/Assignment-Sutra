import numpy as np


class FraudDetector:
    def __init__(self, threshold=0.85):
        self.threshold = threshold
        self.model = None

    def load_model(self, path):
        import joblib
        self.model = joblib.load(path)

    def score_transaction(self, features: dict) -> float:
        if self.model is None:
            raise RuntimeError("Model not loaded")
        x = np.array([list(features.values())])
        return float(self.model.predict_proba(x)[0][1])

    def is_fraud(self, features: dict) -> bool:
        return self.score_transaction(features) >= self.threshold
