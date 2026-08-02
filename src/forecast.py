# src/forecast.py
# Loads trained model + scaler
# Provides predict() function for dashboard

import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import pickle
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MODEL_PATH   = PROJECT_ROOT / "outputs" / "solar_flare_model.pth"
SCALER_PATH  = PROJECT_ROOT / "outputs" / "scaler.pkl"
META_PATH    = PROJECT_ROOT / "outputs" / "model_meta.json"


class SolarFlareLSTM(nn.Module):
    def __init__(self, input_size, hidden_size=256, num_layers=3, dropout=0.3):
        super(SolarFlareLSTM, self).__init__()
        self.lstm = nn.LSTM(
            input_size  = input_size,
            hidden_size = hidden_size,
            num_layers  = num_layers,
            batch_first = True,
            dropout     = dropout
        )
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, 128),
            nn.Tanh(),
            nn.Linear(128, 1)
        )
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size, 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 1)
        )

    def forward(self, x):
        lstm_out, _  = self.lstm(x)
        attn_weights = self.attention(lstm_out)
        attn_weights = torch.softmax(attn_weights, dim=1)
        context      = (lstm_out * attn_weights).sum(dim=1)
        return self.classifier(context).squeeze()


class FlareForecaster:
    """
    Loads trained LSTM model + scaler.
    Maintains a rolling window buffer of recent data.
    Predicts flare probability for next LEAD_TIME_MIN minutes.
    """

    def __init__(self):
        with open(META_PATH) as f:
            self.meta = json.load(f)

        self.feature_cols  = self.meta["input_features"]
        self.window_size   = self.meta["window_size"]
        self.lead_time     = self.meta["lead_time_min"]
        self.threshold     = self.meta["best_threshold"]
        self.n_features    = self.meta["n_features"]

        with open(SCALER_PATH, "rb") as f:
            self.scaler = pickle.load(f)

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model  = SolarFlareLSTM(
            input_size  = self.n_features,
            hidden_size = self.meta["hidden_size"],
            num_layers  = self.meta["num_layers"]
        ).to(self.device)

        self.model.load_state_dict(
            torch.load(MODEL_PATH, map_location=self.device, weights_only=True)
        )
        self.model.eval()

        # Rolling buffer — last WINDOW_SIZE rows
        self.buffer = []

        print(f"FlareForecaster loaded")
        print(f"  Device     : {self.device}")
        print(f"  Features   : {self.n_features}")
        print(f"  Window     : {self.window_size} rows")
        print(f"  Lead time  : {self.lead_time} min")
        print(f"  Threshold  : {self.threshold}")

    def update(self, row_dict):
        """
        Add one new data row to buffer.
        row_dict = {feature_name: value, ...}
        """
        row = [float(row_dict.get(col, 0.0) or 0.0)
               for col in self.feature_cols]
        self.buffer.append(row)

        # Keep only last WINDOW_SIZE rows
        if len(self.buffer) > self.window_size:
            self.buffer = self.buffer[-self.window_size:]

    def predict(self):
        """
        Returns forecast result dict.
        Needs at least WINDOW_SIZE rows in buffer.
        """
        if len(self.buffer) < self.window_size:
            return {
                "ready"       : False,
                "probability" : 0.0,
                "alert"       : False,
                "level"       : "INSUFFICIENT_DATA",
                "confidence"  : "LOW",
                "lead_time"   : self.lead_time,
            }

        window = np.array(self.buffer[-self.window_size:], dtype=np.float32)

        # Scale
        window_scaled = self.scaler.transform(
            window.reshape(-1, self.n_features)
        ).reshape(1, self.window_size, self.n_features)

        # Predict
        x = torch.FloatTensor(window_scaled).to(self.device)
        with torch.no_grad():
            logit = self.model(x)
            prob  = torch.sigmoid(logit).item()

        # Confidence label
        if prob >= 0.85:
            confidence = "HIGH"
        elif prob >= 0.60:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Flare level from probability
        if prob >= 0.90:
            level = "EXTREME"
        elif prob >= 0.75:
            level = "HIGH"
        elif prob >= 0.60:
            level = "MODERATE"
        elif prob >= self.threshold:
            level = "LOW"
        else:
            level = "QUIET"

        return {
            "ready"       : True,
            "probability" : round(prob, 3),
            "alert"       : prob >= self.threshold,
            "level"       : level,
            "confidence"  : confidence,
            "lead_time"   : self.lead_time,
        }


if __name__ == "__main__":
    forecaster = FlareForecaster()
    print("\nForecaster ready for dashboard!")