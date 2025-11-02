import random
import json

from solver import filter_words, get_and_decode_feedback, load_distribution_data, load_distribution_from_csv, load_options_sections, load_feedback_data, load_summary, next_best_guesses
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = "supersecretkey123"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/play')
def play():
    return render_template('play.html')

@app.route('/start_game', methods=['POST'])
def start_game():
    """
    Start a new game.
    Optional JSON parameters:
        - answer: predefined answer word
        - manual_feedback: True if the game will use manual feedback (no auto-answer)
    """
    data = request.json or {}
    manual_feedback = data.get("manual_feedback", False)
    answer = data.get("answer", None)

    words, feedback_matrix, word_to_index = load_feedback_data()

    if manual_feedback:
        # No answer mode
        session['answer'] = None
        session['manual_feedback'] = True
        session['history'] = []
        return jsonify({"status": "ok", "answer_length": 5, "manual_feedback": True})

    if answer:
        if answer not in words:
            return jsonify({"error": "Invalid answer word"}), 400
        session['answer'] = answer
    else:
        # default random answer
        session['answer'] = random.choice(words)

    session['manual_feedback'] = False
    session['history'] = []
    return jsonify({"status": "ok", "answer_length": len(session['answer']), "manual_feedback": False})


@app.route('/guess', methods=['POST'])
def guess():
    data = request.json
    guess_word = data.get('guess', '').lower()
    answer = session.get('answer', None)
    manual_feedback = session.get('manual_feedback', False)

    if 'history' not in session:
        session['history'] = []

    if manual_feedback:
        history = data.get('history', None)
        if not history or not all('guess' in h and 'feedback' in h for h in history):
            return jsonify({"error": "Invalid history for manual mode"}), 400

        for h in history:
            if len(h['feedback']) != 5 or any(c not in "BYG" for c in h['feedback']):
                return jsonify({"error": "Invalid feedback format in history"}), 400
    else:
        if not answer:
            return jsonify({"error": "Game not started"}), 400

        words, _, _ = load_feedback_data()
        if guess_word not in words:
            return jsonify({"error": "Invalid word", "win": False, "done": False}), 400

        feedback = get_and_decode_feedback(guess_word, answer)
        history = session.get('history', [])
        history.append({"guess": guess_word, "feedback": feedback})

    session['history'] = history

    win = history[-1]['feedback'] == "GGGGG"
    done = len(history) >= 6 or win

    return jsonify({
        "history": history,
        "win": win,
        "done": done,
        "manual_feedback": manual_feedback
    })

@app.route('/best_options')
def best_options():
    history = request.args.get('history', '[]')
    history = json.loads(history)
    history = [(str.lower(hist["guess"]), hist["feedback"]) for hist in history]

    data = load_options_sections(history)
    
    for key in ["viable_answers", "top_entropy", "bot_entropy", "top_remaining", "bot_remaining"]:
        for item in data.get(key, []):
            if "entropy" in item:
                item["entropy"] = float(item["entropy"])
            if "expected_remaining" in item:
                item["expected_remaining"] = float(item["expected_remaining"])

    # Total remaining words
    data["total_remaining"] = data.get("remaining_count", len(data.get("viable_answers", [])))

    return jsonify(data)

@app.route('/full_options')
def full_options():
    history = request.args.get('history', '[]')
    history = json.loads(history)
    history = [(str.lower(hist["guess"]), hist["feedback"]) for hist in history]

    words, feedback_matrix, word_to_index = load_feedback_data()
    data = next_best_guesses(words, feedback_matrix, word_to_index, history)

    if data is None:
        return jsonify({"viable_answers": [], "viable_guesses": []})

    remaining, results = data
    viable_answers = [{"word": w, "entropy": float(e), "expected": float(er)} for w, e, er in results if w in remaining]
    viable_guesses = [{"word": w, "entropy": float(e), "expected": float(er)} for w, e, er in results]
    sorted_answers = sorted(viable_answers, key=lambda x: x["entropy"], reverse=True)
    sorted_guesses = sorted(viable_guesses, key=lambda x: x["entropy"], reverse=True)

    for idx, item in enumerate(sorted_answers):
        item["index"] = idx
    for idx, item in enumerate(sorted_guesses):
        item["index"] = idx

    return jsonify({
        "viable_answers": sorted_answers,
        "viable_guesses": sorted_guesses
    })

# Distribution page
@app.route('/distribution')
def distribution_page():
    return render_template('dist.html')

@app.route('/distribution_data', methods=['POST'])
def distribution_data():
    data = request.json
    guess = data.get('guess', '').lower()
    history = data.get('history', [])

    results = load_distribution_data(guess, history)

    return jsonify(results)

@app.route("/simulation_dashboard")
def simulation_dashboard():
    strategy = "entropy"
    summary = load_summary(strategy)
    distribution = load_distribution_from_csv(strategy)

    #quick fix
    summary["start_ts"] = summary["start_ts"].isoformat()
    distribution = {str(k): v for k, v in summary["rounds_distribution"].items()}


    if not summary or not distribution:
        return "No simulation data found. Please run a simulation first."

    return render_template("simulation_dashboard.html",
                           summary=summary,
                           distribution=distribution,
                           strategy=strategy)


@app.route("/data/<strategy>")
def data(strategy):
    summary = load_summary(strategy)
    distribution = load_distribution_from_csv(strategy)
    if not summary or not distribution:
        return jsonify({"error": "No data found"}), 404

    return jsonify({
        "summary": summary,
        "distribution": distribution
    })

if __name__ == '__main__':
    app.run(debug=True)
