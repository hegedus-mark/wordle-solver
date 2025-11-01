from pathlib import Path
import random
import sys
import numpy as np
from numba import njit, prange
import time
from functools import wraps
import os
import cProfile
import pstats

CLEAN_METRICS_CACHE_FILE = "data/best_options.npy"


#region Data
def save_feedback_data(words, feedback_matrix, save_dir="data",):
    os.makedirs(save_dir, exist_ok=True)

    np.save(f"{save_dir}/feedback_matrix.npy", feedback_matrix)

    with open(f"{save_dir}/words.txt", "w") as f:
        f.write("\n".join(words))

    print(f"Saved feedback matrix and words to '{save_dir}'")

def load_feedback_data(save_dir="data"):
    feedback_matrix = np.load(f"{save_dir}/feedback_matrix.npy")
    with open(f"{save_dir}/words.txt", "r") as f:
        words = [w.strip() for w in f if w.strip()]
    word_to_index = {w: i for i, w in enumerate(words)}
    
    print(f"Loaded {len(words)} words and feedback matrix from '{save_dir}'")
    return words, feedback_matrix, word_to_index

def read_word_dataset(letters_count:int, take: int = None):
    script_dir = Path(__file__).parent
    file_path = script_dir / "data" / "archive" / "words_alpha.txt"

    with open(file_path, "r") as file:
        words =  [
            word.strip()
            for word in file
            if letters_count== len(word.strip())
        ]

        if take is not None and take < len(words):
            words = random.sample(words, take)
        return words




def get_feedback_code(guess: str, answer: str) -> int:
    """Return feedback as a base-3 integer (0–242 for 5-letter words)."""
    feedback = [0] * len(guess)  # 0=B, 1=Y, 2=G
    answer_counts = {}

    for a in answer:
        answer_counts[a] = answer_counts.get(a, 0) + 1

    for i, (g, a) in enumerate(zip(guess, answer)):
        if g == a:
            feedback[i] = 2
            answer_counts[g] -= 1
        elif answer_counts.get(g, 0) > 0:
            feedback[i] = 1
            answer_counts[g] -= 1

    code = 0
    for f in feedback:
        code = code * 3 + f
    return code

def build_feedback_matrix(words):
    n = len(words)
    matrix = np.zeros((n, n), dtype=np.uint16)
    print(f"Building feedback matrix for {n} words...")

    for i, g in enumerate(words):
        for j, a in enumerate(words):
            matrix[i, j] = get_feedback_code(g, a)

        if (i + 1) % max(1, n // 20) == 0 or i == n - 1:
            percent = (i + 1) / n * 100
            sys.stdout.write(f"\rProgress: {percent:5.1f}% ({i+1}/{n})")
            sys.stdout.flush()

    print("\nFeedback matrix built.")
    return matrix

#endregion

#region Solver
def encode_feedback(fb_str: str) -> int:
    code = 0
    for ch in fb_str:
        code = code * 3 + {'B':0, 'Y':1, 'G':2}[ch]
    return code

def get_and_decode_feedback(guess: str, answer: str) -> str:
    code = get_feedback_code(guess, answer)
    chars = []
    for _ in range(5): 
        code, r = divmod(code, 3)
        chars.append("BYG"[r])
    return "".join(reversed(chars))

def filter_words(words, feedback_matrix, word_to_index, history):
    remaining_mask = np.ones(len(words), dtype=bool)

    for guess, fb_str in history:
        fb_code = encode_feedback(fb_str)
        g_idx = word_to_index[guess]
        remaining_mask &= (feedback_matrix[g_idx] == fb_code)

    return np.array(words)[remaining_mask]



@njit(parallel=True)
def compute_metrics_numba(feedback_matrix, remaining_indices):
    n_words = feedback_matrix.shape[0]
    entropies = np.zeros(n_words, dtype=np.float64)
    expected_remaining = np.zeros(n_words, dtype=np.float64)

    for g_idx in prange(n_words):  
        counts = np.zeros(3**5, dtype=np.int32)
        for j in remaining_indices:
            pattern = feedback_matrix[g_idx, j]
            counts[pattern] += 1

        total = len(remaining_indices)
        H = 0.0
        E_remain = 0.0
        for c in counts:
            if c > 0:
                p = c / total
                H += p * np.log2(1.0 / p)
                E_remain += p * c
        entropies[g_idx] = H
        expected_remaining[g_idx] = E_remain

    return entropies, expected_remaining


def save_best_options(words, feedback_matrix):
    entropies, expected_remaining = compute_metrics_numba(
        feedback_matrix, remaining_indices=list(range(len(words)))
    )
    results = np.zeros((len(words), 3), dtype=np.float32)  
    results[:,0] = entropies
    results[:,1] = expected_remaining
    np.save(CLEAN_METRICS_CACHE_FILE, results)

def load_best_options():
    if os.path.exists(CLEAN_METRICS_CACHE_FILE):
        return np.load(CLEAN_METRICS_CACHE_FILE)
    return None

def next_best_guesses(words, feedback_matrix, word_to_index, history):
    remaining = filter_words(words, feedback_matrix, word_to_index, history)
    remaining_indices = [word_to_index[w] for w in remaining]

    if len(remaining) == 1:
        print(f"\nOnly one possible answer remains: {remaining[0]}")
        print("Entropy = 0 bits (certainty achieved).")
        return [(remaining[0], 0.0), remaining[0]]
    
    entropies, expected_remaining = compute_metrics_numba(feedback_matrix, remaining_indices)

    results = [(words[i], float(entropies[i]), float(expected_remaining[i])) for i in range(len(words))]

    return results, remaining

def load_best_guesses_for_history(history):
    words, feedback_matrix, word_to_index = load_feedback_data()
    if(len(history) != 0):
        results, remaining = next_best_guesses(words, feedback_matrix, word_to_index, history)
    else:
        results = load_best_options()
        if (results is None):
            results, remaining =  next_best_guesses(words, feedback_matrix, word_to_index, [])
            save_best_options(words, feedback_matrix)
        else:
            remaining = words

    return results, remaining
    
if __name__ == "__main__":

    try:
        words, feedback_matrix, word_to_index = load_feedback_data()
    except FileNotFoundError:
        print("No cached data found — building matrix...")
        words = read_word_dataset(5)
        feedback_matrix = build_feedback_matrix(words)
        word_to_index = {w: i for i, w in enumerate(words)}
        save_feedback_data(words, feedback_matrix)

    with cProfile.Profile() as pr:
        entropies, remaining = next_best_guesses(words, feedback_matrix, word_to_index, [])


        top_indices = np.argsort(entropies)[::-1][:20]
        results = [(words[i], float(entropies[i])) for i in top_indices]


        print(f"\n{len(remaining)} possible answers remain.")
        print(f"Top {20} guesses:")
        for w, H in results:
            print(f"  {w:<10}  {H:.3f} bits")


    stats = pstats.Stats(pr)
    stats.sort_stats(pstats.SortKey.TIME).print_stats(20)

