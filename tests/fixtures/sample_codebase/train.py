"""Sample training script with dataset loading and evaluation metrics."""

import pandas as pd
from datasets import load_dataset
from sklearn.metrics import accuracy_score, f1_score, classification_report

dataset = load_dataset("imdb", split="train")
df = pd.read_csv("data/training_data.csv")

y_true = [0, 1, 1, 0, 1]
y_pred = [0, 1, 0, 0, 1]

acc = accuracy_score(y_true, y_pred)
f1 = f1_score(y_true, y_pred)
report = classification_report(y_true, y_pred)

print(f"Accuracy: {acc}, F1: {f1}")
