from collections import Counter
import csv
import json
import multiprocessing
from pathlib import Path
import random
import sys
import numpy as np
from numba import njit, prange
import datetime
from functools import wraps
import os
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed
import cProfile
import pstats

NO_HISTORY_CACHE_FILE = "data/no_history_guesses_cache.npz"
SIMULATION_SAVE_DIR = "simulation_results"



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

def save_best_guesses(results, remaining):
    print("Caching no-history results...")
    names = np.array([r[0] for r in results])
    entropies = np.array([r[1] for r in results], dtype=np.float32)
    expected_remaining = np.array([r[2] for r in results], dtype=np.float32)
    remaining_arr = np.array(remaining)

    np.savez(
        NO_HISTORY_CACHE_FILE,
        names=names,
        entropies=entropies,
        expected_remaining=expected_remaining,
        remaining=remaining_arr
    )
#endregion

#region UI
def next_best_guesses(words, feedback_matrix, word_to_index, history):
    if not history and os.path.exists(NO_HISTORY_CACHE_FILE):
        data = np.load(NO_HISTORY_CACHE_FILE, allow_pickle=False)
        results = list(zip(data["names"], data["entropies"], data["expected_remaining"]))
        remaining = data["remaining"].tolist()
    else:
        remaining = filter_words(words, feedback_matrix, word_to_index, history)
        remaining_indices = [word_to_index[w] for w in remaining]

        if len(remaining) == 0:
            return None

        entropies, expected_remaining = compute_metrics_numba(feedback_matrix, remaining_indices)
        results = [(words[i], float(entropies[i]), float(expected_remaining[i])) for i in range(len(words))]

        if not history and not os.path.exists(NO_HISTORY_CACHE_FILE):
            save_best_guesses(results, remaining)

    return remaining, results

def load_options_sections(history):
    words, feedback_matrix, word_to_index = load_feedback_data()
    data = next_best_guesses(words, feedback_matrix, word_to_index, history)
    if data is None:
        return {"remaining_count": 0, "viable_answers": []}
    
    remaining, results = data

    if len(remaining) > 2:
        filtered_results = [
            (w, float(e), float(er))   # <-- Convert here
            for (w, e, er) in results
            if float(e) > 0.0 and float(er) < len(remaining)
        ]
    elif len(remaining) <= 2 and len(remaining) > 0:
        filtered_results = [(w, float(e), float(er)) for (w, e, er) in results if w in remaining]
    else:
        filtered_results = [(w, float(e), float(er)) for (w, e, er) in results]

    remaining_set = set(remaining)
    viable_results = [r for r in filtered_results if r[0] in remaining_set]
    sorted_viable = sorted(viable_results, key=lambda x: x[1], reverse=True)
    sorted_entropy = sorted(filtered_results, key=lambda x: x[1], reverse=True)
    sorted_remaining = sorted(filtered_results, key=lambda x: x[2])

    top_n = 10 

    viable = sorted_viable[:20] 

    top_entropy = sorted_entropy[:top_n]
    bot_entropy = sorted_entropy[-top_n:] if len(sorted_entropy) > top_n else sorted_entropy

    top_remaining = sorted_remaining[:top_n]
    bot_remaining = sorted_remaining[-top_n:] if len(sorted_remaining) > top_n else sorted_remaining

    return {
        "remaining_count": len(remaining),
        "viable_answers": viable,
        "top_entropy": top_entropy,
        "bot_entropy": bot_entropy,
        "top_remaining": top_remaining,
        "bot_remaining": bot_remaining,
    }

def load_distribution_data(guess, history):
    words, feedback_matrix, word_to_index = load_feedback_data()

    remaining = filter_words(words, feedback_matrix, word_to_index, history)
    N = len(remaining)
    if N == 0:
        return {"guess": guess, "total_remaining": 0, "expected_remaining": 0.0}

    g_idx = word_to_index[guess]
    remaining_indices = np.array([word_to_index[w] for w in remaining])

    fb_codes = feedback_matrix[g_idx, remaining_indices]

    remaining_counts = np.zeros(N, dtype=np.int32)
    for i, ans_idx in enumerate(remaining_indices):
        fb_code = feedback_matrix[g_idx, ans_idx]
        remaining_counts[i] = np.sum(fb_codes == fb_code)

    expected_remaining = float(np.mean(remaining_counts))

    unique_counts, occurrences = np.unique(remaining_counts, return_counts=True)
    print(list(zip(unique_counts, occurrences)))
    distribution = {
        int(count): int(occ) for count, occ in zip(unique_counts, occurrences)
    }

    return {
        "guess": guess,
        "total_remaining": N,
        "expected_remaining": expected_remaining,
        "distribution": distribution
    }

#endregion

#region Simulation
def choose_guess_from_results(results, remaining_set, strategy="entropy"):
    if strategy == "random_viable":
        viable = [r[0] for r in results if r[0] in remaining_set]
        return random.choice(viable)

    few_left = len(remaining_set) <= 2

    if "viable" in strategy or few_left:
        cand = [r for r in results if r[0] in remaining_set]
    else:
        cand = results

    if not cand:
        return random.choice(list(remaining_set))

    if "entropy" in strategy:
        best = max(cand, key=lambda r: r[1])
        return best[0]
    elif "min_expected" in strategy or "expected" in strategy:
        best = min(cand, key=lambda r: r[2])
        return best[0]
    else:
        return max(cand, key=lambda r: r[1])[0]

def simulate_one_answer(answer, words, feedback_matrix, word_to_index, max_guesses=6, strategy="entropy", first_guess=None):
    history = []
    remaining = np.array(words)  
    remaining_set = set(remaining.tolist())

    if first_guess is not None:
        guess = first_guess
    else:
        _, results = next_best_guesses(words, feedback_matrix, word_to_index, history)
        guess = choose_guess_from_results(results, remaining_set, strategy=("viable_entropy" if "viable" in strategy else "entropy"))

    for turn in range(1, max_guesses + 1):
        fb_str = get_and_decode_feedback(guess, answer)
        history.append((guess, fb_str))
        if fb_str == "GGGGG":
            return turn, True, history

        remaining = filter_words(words, feedback_matrix, word_to_index, history)
        remaining_set = set(remaining.tolist())
        if len(remaining) == 0:
            return None, False, history

        _, results = next_best_guesses(words, feedback_matrix, word_to_index, history)
        guess = choose_guess_from_results(results, remaining_set, strategy=strategy)

    return None, False, history

# MULTI PROCESS HELPERS 
_global_data = {}

def init_worker(words_path, feedback_matrix_path, word_to_index_path):
    global _global_data

    with open(words_path, "r", encoding="utf8") as f:
        words = [w.strip() for w in f if w.strip()]

    with open(word_to_index_path, "r", encoding="utf8") as f:
        word_to_index = json.load(f)

    feedback_matrix = np.load(feedback_matrix_path, mmap_mode="r")

    _global_data['words'] = words
    _global_data['feedback_matrix'] = feedback_matrix
    _global_data['word_to_index'] = word_to_index

def simulate_one_answer_wrapper(args):
    answer, max_guesses, strategy, first_guess = args
    data = _global_data
    turn, solved,history =  simulate_one_answer(
        answer,
        data['words'],
        data['feedback_matrix'],
        data['word_to_index'],
        max_guesses=max_guesses,
        strategy=strategy,
        first_guess=first_guess
    )
    return answer, turn, solved, history

def simulate_all_answers(words, feedback_matrix, word_to_index,
                         strategy="entropy",
                         max_guesses=6,
                         answers_to_simulate=None,
                         first_guess=None,
                         save_dir=SIMULATION_SAVE_DIR,
                         parallel=True):
    os.makedirs(save_dir, exist_ok=True)

    if answers_to_simulate is None:
        answers_to_simulate = words

    feedback_matrix_path = os.path.join("data", "feedback_matrix.npy")
    words_path = os.path.join("data", "words.txt")
    word_to_index_path = os.path.join("data", "word_to_index.json")
    
    if not os.path.exists(word_to_index_path):
        import json
        with open(word_to_index_path, "w", encoding="utf8") as f:
            json.dump(word_to_index, f)

    assert os.path.exists(feedback_matrix_path), "feedback_matrix .npy not found"

    total_games = len(answers_to_simulate)
    start_ts = datetime.datetime.now()
    feedback_matrix = np.ascontiguousarray(feedback_matrix)

    results = []
    if parallel:
        num_workers = max(1, min(multiprocessing.cpu_count() - 1, 8))  
        with ProcessPoolExecutor(
            max_workers=num_workers,
            initializer=init_worker,
            initargs=(words_path, feedback_matrix_path, word_to_index_path)
        ) as executor:
            task_args = [(ans, max_guesses, strategy, first_guess) for ans in answers_to_simulate]
            for res in tqdm(executor.map(simulate_one_answer_wrapper, task_args),
                            total=total_games, desc="Simulating", ncols=100):
                results.append(res)

    else:
        init_worker(words_path, feedback_matrix_path, word_to_index_path)
        for ans in tqdm(answers_to_simulate, desc="Simulating", ncols=100):
            results.append(simulate_one_answer_wrapper((ans, max_guesses, strategy, first_guess)))

    per_answer_rows = []
    rounds_counter = Counter()
    solved_count = 0
    attempts_list = []

    for ans, guesses_taken, solved, history in results:
            if solved:
                rounds_counter[guesses_taken] += 1
                solved_count += 1
                attempts_list.append(guesses_taken)
            else:
                rounds_counter["fail"] += 1
                attempts_list.append(max_guesses + 1)

            per_answer_rows.append({
                "answer": ans,
                "solved": bool(solved),
                "guesses_taken": guesses_taken if guesses_taken is not None else -1,
                "history": " | ".join([f"{g}:{fb}" for g, fb in history])
            })

    # compute statistics
    wins = solved_count
    fails = total_games - solved_count
    mean_rounds = float(np.mean([a for a in attempts_list if a <= max_guesses])) if wins > 0 else float("nan")
    median_rounds = float(np.median([a for a in attempts_list if a <= max_guesses])) if wins > 0 else float("nan")
    overall_mean_including_fails = float(np.mean(attempts_list))  # treats fails as max_guesses+1


    end_ts = datetime.datetime.now()
    elapsed = (end_ts - start_ts).total_seconds()

    summary = {
        "elapsed_seconds": elapsed,
        "strategy": strategy,
        "first_guess": first_guess,
        "total_games": total_games,
        "wins": int(wins),
        "fails": int(fails),
        "win_rate": wins / total_games,
        "mean_rounds_win_only": mean_rounds,
        "median_rounds_win_only": median_rounds,
        "mean_rounds_including_fails": overall_mean_including_fails,
        "rounds_distribution": dict(rounds_counter),
        "start_ts": start_ts.isoformat(),
    }

    csv_path = os.path.join(save_dir, f"simulation_{strategy}_{'withfirst' if first_guess else 'nofirst'}.csv")
    with open(csv_path, "w", newline="", encoding="utf8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["answer", "solved", "guesses_taken", "history"])
        writer.writeheader()
        writer.writerows(per_answer_rows)

    np.savez(os.path.join(save_dir, f"summary_{strategy}.npz"), **summary)

    print("\nSimulation complete.")
    print(f"Saved per-answer CSV to: {csv_path}")
    print("Summary:")
    for k, v in summary.items():
        if k != "rounds_distribution":
            print(f"  {k}: {v}")
    print("  rounds_distribution:", summary["rounds_distribution"])

    return summary
#endregion

#region LoadData
def load_summary(strategy):
    path = os.path.join(SIMULATION_SAVE_DIR, f"summary_{strategy}.npz")
    if not os.path.exists(path):
        return None

    data = np.load(path, allow_pickle=True)
    summary = {key: data[key].item() if data[key].shape == () else data[key].tolist() for key in data.files}
    return summary


def load_distribution_from_csv(strategy, first_guess=False):
    filename = f"simulation_{strategy}_{'withfirst' if first_guess else 'nofirst'}.csv"
    path = os.path.join(SIMULATION_SAVE_DIR, filename)
    if not os.path.exists(path):
        return None

    rounds_count = {}
    with open(path, newline="", encoding="utf8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["solved"] == "True":
                g = int(row["guesses_taken"])
                rounds_count[g] = rounds_count.get(g, 0) + 1
            else:
                rounds_count["fail"] = rounds_count.get("fail", 0) + 1

    return rounds_count
#endregion

if __name__ == "__main__":

    try:
        words, feedback_matrix, word_to_index = load_feedback_data()
    except FileNotFoundError:
        print("No cached data found — building matrix...")
        words = read_word_dataset(5)
        feedback_matrix = build_feedback_matrix(words)
        word_to_index = {w: i for i, w in enumerate(words)}
        save_feedback_data(words, feedback_matrix)

    test_answers = words
    import multiprocessing
    multiprocessing.set_start_method("spawn", force=True)
    summary = simulate_all_answers(words, feedback_matrix, word_to_index,
                                   strategy="entropy",
                                   max_guesses=6,
                                   answers_to_simulate=test_answers,
                                   first_guess=None,
                                   save_dir=SIMULATION_SAVE_DIR)

    # with cProfile.Profile() as pr:
    #     results = next_best_guesses(words, feedback_matrix, word_to_index, [])

    # print(f":")
    # stats = pstats.Stats(pr)
    # stats.sort_stats(pstats.SortKey.TIME).print_stats(20)

