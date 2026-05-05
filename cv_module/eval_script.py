"""
evaluate_cnn.py — CNN Model Evaluation Report
==============================================
Loads the trained zimbabwe_traffic_model.h5 and generates:
  1. Overall accuracy
  2. Per-class precision, recall, F1-score
  3. Confusion matrix (counts + normalised %)
  4. Saves all charts as PNG files for the report/presentation

Run from the folder containing the model and dataset:
    python evaluate_cnn.py

Requirements:
    pip install tensorflow scikit-learn matplotlib seaborn numpy
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
import tensorflow as tf
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    precision_recall_fscore_support,
)

# ==============================================================================
# CONFIGURATION — edit these if your paths differ
# ==============================================================================
MODEL_PATH   = "zimbabwe_traffic_model.h5"   # your saved model
DATASET_DIR  = "test_dataset"             # folder with class sub-folders
OUTPUT_DIR   = "evaluation_output"           # where PNGs and the report are saved

IMG_HEIGHT   = 150
IMG_WIDTH    = 150
BATCH_SIZE   = 16
VAL_SPLIT    = 0.0                           # must match what you used in training
SEED         = 123

CLASS_NAMES  = ["ambulance", "civilian_car", "fire_truck", "police_car"]

# ==============================================================================
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==============================================================================
# 1. LOAD MODEL
# ==============================================================================
print("=" * 60)
print("  CNN EVALUATION — Zimbabwe Traffic Model")
print("=" * 60)
print(f"\n  Loading model from: {MODEL_PATH}")
model = tf.keras.models.load_model(MODEL_PATH)
model.summary()

# ==============================================================================
# 2. LOAD VALIDATION DATASET
# ==============================================================================
print(f"\n  Loading validation data from: {DATASET_DIR}")
val_ds = tf.keras.utils.image_dataset_from_directory(
    DATASET_DIR,
   # validation_split=VAL_SPLIT,
   # subset="validation",
   # seed=SEED,
    image_size=(IMG_HEIGHT, IMG_WIDTH),
    batch_size=BATCH_SIZE,
    shuffle=False,   # important to keep order for metrics
)

detected_class_names = val_ds.class_names
print(f"  Classes detected in dataset: {detected_class_names}")

# ==============================================================================
# 3. RUN INFERENCE
# ==============================================================================
print("\n  Running inference on validation set...")
y_true = []
y_pred = []

for images, labels in val_ds:
    # The model was trained with from_logits=True so we apply softmax here
    logits       = model.predict(images, verbose=0)
    probs        = tf.nn.softmax(logits).numpy()
    predicted    = np.argmax(probs, axis=1)
    y_true.extend(labels.numpy())
    y_pred.extend(predicted)

y_true = np.array(y_true)
y_pred = np.array(y_pred)

# ==============================================================================
# 4. METRICS
# ==============================================================================
overall_accuracy = accuracy_score(y_true, y_pred) * 100

precision, recall, f1, support = precision_recall_fscore_support(
    y_true, y_pred, labels=list(range(len(detected_class_names))), zero_division=0
)

print("\n" + "=" * 60)
print("  RESULTS")
print("=" * 60)
print(f"\n  Overall Validation Accuracy : {overall_accuracy:.2f}%\n")
print(f"  {'Class':<16} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Samples':>10}")
print("  " + "-" * 56)
for i, name in enumerate(detected_class_names):
    print(
        f"  {name:<16}"
        f" {precision[i]*100:>9.1f}%"
        f" {recall[i]*100:>9.1f}%"
        f" {f1[i]*100:>9.1f}%"
        f" {int(support[i]):>10}"
    )

# Macro averages
print("  " + "-" * 56)
print(
    f"  {'MACRO AVG':<16}"
    f" {precision.mean()*100:>9.1f}%"
    f" {recall.mean()*100:>9.1f}%"
    f" {f1.mean()*100:>9.1f}%"
    f" {int(support.sum()):>10}"
)
print("=" * 60)

# Full sklearn report saved to text file
report_text = classification_report(
    y_true, y_pred,
    target_names=detected_class_names,
    digits=4,
)
report_path = os.path.join(OUTPUT_DIR, "classification_report.txt")
with open(report_path, "w") as f:
    f.write(f"Overall Validation Accuracy: {overall_accuracy:.2f}%\n\n")
    f.write(report_text)
print(f"\n  Full report saved → {report_path}")

# ==============================================================================
# 5. CONFUSION MATRIX PLOTS
# ==============================================================================
cm      = confusion_matrix(y_true, y_pred)
cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True) * 100   # row %

fig = plt.figure(figsize=(16, 7))
fig.suptitle(
    f"CNN Traffic Vehicle Classifier — Evaluation Results\n"
    f"Overall Accuracy: {overall_accuracy:.1f}%",
    fontsize=14, fontweight="bold", y=1.01,
)

gs = gridspec.GridSpec(1, 2, figure=fig, wspace=0.4)

# --- Left: raw counts ---
ax1 = fig.add_subplot(gs[0])
sns.heatmap(
    cm, annot=True, fmt="d", cmap="Blues",
    xticklabels=detected_class_names,
    yticklabels=detected_class_names,
    ax=ax1,
    linewidths=0.5,
)
ax1.set_xlabel("Predicted Label", fontsize=11)
ax1.set_ylabel("True Label", fontsize=11)
ax1.set_title("Confusion Matrix (counts)", fontsize=12, pad=10)
ax1.tick_params(axis="x", rotation=20)
ax1.tick_params(axis="y", rotation=0)

# --- Right: normalised % ---
ax2 = fig.add_subplot(gs[1])
sns.heatmap(
    cm_norm, annot=True, fmt=".1f", cmap="Greens",
    xticklabels=detected_class_names,
    yticklabels=detected_class_names,
    ax=ax2,
    linewidths=0.5,
    vmin=0, vmax=100,
)
ax2.set_xlabel("Predicted Label", fontsize=11)
ax2.set_ylabel("True Label", fontsize=11)
ax2.set_title("Confusion Matrix (row %)", fontsize=12, pad=10)
ax2.tick_params(axis="x", rotation=20)
ax2.tick_params(axis="y", rotation=0)

plt.tight_layout()
cm_path = os.path.join(OUTPUT_DIR, "confusion_matrix.png")
plt.savefig(cm_path, dpi=150, bbox_inches="tight")
plt.show()
print(f"  Confusion matrix saved → {cm_path}")

# ==============================================================================
# 6. PER-CLASS BAR CHART (Precision / Recall / F1)
# ==============================================================================
fig2, ax = plt.subplots(figsize=(10, 5))

x       = np.arange(len(detected_class_names))
width   = 0.25
colors  = ["#4C72B0", "#55A868", "#C44E52"]

bars_p = ax.bar(x - width,     precision * 100, width, label="Precision", color=colors[0])
bars_r = ax.bar(x,             recall    * 100, width, label="Recall",    color=colors[1])
bars_f = ax.bar(x + width,     f1        * 100, width, label="F1-Score",  color=colors[2])

def label_bars(bars):
    for bar in bars:
        h = bar.get_height()
        ax.annotate(
            f"{h:.1f}%",
            xy=(bar.get_x() + bar.get_width() / 2, h),
            xytext=(0, 3), textcoords="offset points",
            ha="center", va="bottom", fontsize=8,
        )

label_bars(bars_p)
label_bars(bars_r)
label_bars(bars_f)

ax.set_xlabel("Vehicle Class", fontsize=12)
ax.set_ylabel("Score (%)", fontsize=12)
ax.set_title(
    f"Per-Class Precision, Recall & F1-Score\n"
    f"Overall Accuracy: {overall_accuracy:.1f}%",
    fontsize=13, fontweight="bold",
)
ax.set_xticks(x)
ax.set_xticklabels(detected_class_names, fontsize=11)
ax.set_ylim(0, 115)
ax.legend(fontsize=11)
ax.grid(axis="y", linestyle="--", alpha=0.5)

plt.tight_layout()
bar_path = os.path.join(OUTPUT_DIR, "per_class_metrics.png")
plt.savefig(bar_path, dpi=150, bbox_inches="tight")
plt.show()
print(f"  Per-class metrics chart saved → {bar_path}")

# ==============================================================================
# 7. SUMMARY CARD — single image suitable for a slide
# ==============================================================================
fig3, ax = plt.subplots(figsize=(7, 4))
ax.axis("off")

summary_data = [["Class", "Precision", "Recall", "F1-Score", "Samples"]]
for i, name in enumerate(detected_class_names):
    summary_data.append([
        name,
        f"{precision[i]*100:.1f}%",
        f"{recall[i]*100:.1f}%",
        f"{f1[i]*100:.1f}%",
        str(int(support[i])),
    ])
summary_data.append([
    "Macro Avg",
    f"{precision.mean()*100:.1f}%",
    f"{recall.mean()*100:.1f}%",
    f"{f1.mean()*100:.1f}%",
    str(int(support.sum())),
])

col_colors  = [["#2c3e50"] * 5]
row_colors  = [["#ecf0f1"] * 5] * (len(summary_data) - 2)
row_colors += [["#d5e8d4"] * 5]   # macro avg row in green

table = ax.table(
    cellText=summary_data[1:],
    colLabels=summary_data[0],
    cellLoc="center",
    loc="center",
    cellColours=row_colors,
)
table.auto_set_font_size(False)
table.set_fontsize(11)
table.scale(1.2, 1.8)

# Style header
for j in range(5):
    table[(0, j)].set_facecolor("#2c3e50")
    table[(0, j)].set_text_props(color="white", fontweight="bold")

# Bold macro avg row
for j in range(5):
    table[(len(summary_data) - 1, j)].set_text_props(fontweight="bold")

ax.set_title(
    f"Zimbabwe Traffic CNN Classifier\nOverall Validation Accuracy: {overall_accuracy:.1f}%",
    fontsize=13, fontweight="bold", pad=20,
)

plt.tight_layout()
summary_path = os.path.join(OUTPUT_DIR, "summary_card.png")
plt.savefig(summary_path, dpi=150, bbox_inches="tight")
plt.show()
print(f"  Summary card saved → {summary_path}")

# ==============================================================================
# 8. FINAL PRINTOUT
# ==============================================================================
print("\n" + "=" * 60)
print("  ALL OUTPUTS SAVED")
print("=" * 60)
print(f"  📄  {report_path}")
print(f"  🖼️   {cm_path}")
print(f"  📊  {bar_path}")
print(f"  🃏  {summary_path}")
print(f"\n  Overall Accuracy  : {overall_accuracy:.2f}%")
print(f"  Macro Precision   : {precision.mean()*100:.2f}%")
print(f"  Macro Recall      : {recall.mean()*100:.2f}%")
print(f"  Macro F1-Score    : {f1.mean()*100:.2f}%")
print("=" * 60)