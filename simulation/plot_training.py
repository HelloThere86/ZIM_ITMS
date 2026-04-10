import os
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

def _smooth(values, window=15):
    """Simple moving average for readability on noisy loss curves."""
    if len(values) < window:
        return values
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="valid")

def save_training_plots(epsilon_history, loss_history, wait_history, label="marl", out_dir="."):
    os.makedirs(out_dir, exist_ok=True)
    episodes = list(range(1, len(epsilon_history) + 1))

    # --- Figure 1: Epsilon + Loss ---
    fig, (ax_eps, ax_loss) = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle(f"Training curves — {label}", fontsize=13, y=1.01)

    # Epsilon Plot
    ep300 = min(300, len(episodes))
    ax_eps.plot(episodes[:ep300], epsilon_history[:ep300], color="#7F77DD", linewidth=1.8, label="phase 1 + 2")
    ax_eps.plot(episodes[ep300-1:], epsilon_history[ep300-1:], color="#378ADD", linewidth=1.8, label="phase 3")
    ax_eps.axhline(0.05, color="#B4B2A9", linewidth=0.8, linestyle="--", label="floor (0.05)")
    ax_eps.axvline(300, color="#B4B2A9", linewidth=0.8, linestyle=":")
    ax_eps.set_title("Epsilon decay")
    ax_eps.set_xlabel("Episode")
    ax_eps.set_ylabel("Epsilon")
    ax_eps.legend(frameon=False)
    ax_eps.spines[["top", "right"]].set_visible(False)

    # Loss Plot
    valid_loss = [(e, v) for e, v in zip(episodes, loss_history) if v > 0]
    if valid_loss:
        ep_l, lo_l = zip(*valid_loss)
        ax_loss.plot(ep_l, lo_l, color="#D3D1C7", linewidth=0.8, label="raw")
        smoothed = _smooth(list(lo_l))
        offset = len(lo_l) - len(smoothed)
        ax_loss.plot(list(ep_l)[offset:], smoothed, color="#1D9E75", linewidth=2.0, label="smoothed (w=15)")

    ax_loss.set_title("Training loss")
    ax_loss.set_xlabel("Episode")
    ax_loss.set_ylabel("Loss")
    ax_loss.legend(frameon=False)
    ax_loss.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    fig.savefig(os.path.join(out_dir, f"{label}_epsilon_loss.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    # --- Figure 2: Average Wait Time ---
    fig2, ax_wait = plt.subplots(figsize=(8, 4))
    fig2.suptitle(f"Average wait per step — {label}", fontsize=13, y=1.01)

    ax_wait.plot(episodes, wait_history, color="#D3D1C7", linewidth=0.8, label="raw")
    smoothed_w = _smooth(wait_history)
    offset_w = len(wait_history) - len(smoothed_w)
    ax_wait.plot(episodes[offset_w:], smoothed_w, color="#D85A30", linewidth=2.0, label="smoothed (w=15)")

    best_ep = int(np.argmin(wait_history)) + 1
    best_val = min(wait_history)
    ax_wait.scatter([best_ep], [best_val], color="#D85A30", zorder=5, s=40)
    ax_wait.annotate(f"best: {best_val:.2f}\nep {best_ep}", xy=(best_ep, best_val), xytext=(best_ep + 15, best_val + 0.5), arrowprops=dict(arrowstyle="->"))

    ax_wait.set_xlabel("Episode")
    ax_wait.set_ylabel("Avg wait per step (s)")
    ax_wait.legend(frameon=False)
    ax_wait.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    fig2.savefig(os.path.join(out_dir, f"{label}_wait.png"), dpi=150, bbox_inches="tight")
    plt.close(fig2)