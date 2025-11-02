import random
import json

from solver import filter_words, get_and_decode_feedback, load_distribution_data, load_options_sections, load_feedback_data
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = "supersecretkey123"


@app.route('/')
def home():
    return render_template('play.html')

@app.route('/start_game')
def start_game():
    words, feedback_matrix, word_to_index = load_feedback_data()
    answer = random.choice(words)
    session['answer'] = answer
    session['history'] = []
    return jsonify({"status": "ok", "answer_length": len(answer)})


@app.route('/guess', methods=['POST'])
def guess():
    data = request.json
    guess_word = data.get('guess', '').lower()
    answer = session.get('answer', None)
    if not answer:
        return jsonify({"error": "Game not started"}), 400

    words, _, _ = load_feedback_data()
    if guess_word not in words:
        return jsonify({
            "error": "Invalid word",
            "win": False,
            "done": False
        }), 400

    feedback = get_and_decode_feedback(guess_word, answer)
    history = session.get('history', [])
    history.append({"guess": guess_word, "feedback": feedback})
    session['history'] = history

    win = guess_word == answer
    done = len(session['history']) >= 6 or win

    return jsonify({
        "feedback": feedback,
        "history": session['history'],
        "win": win,
        "done": done
    })


@app.route('/best_options')
def best_options():
    history = request.args.get('history', '[]')
    history = json.loads(history)
    history = [(str.lower(hist["guess"]), hist["feedback"]) for hist in history]

    data = load_options_sections(history)
    
    # Ensure all numbers are Python floats
    for key in ["viable_answers", "top_entropy", "bot_entropy", "top_remaining", "bot_remaining"]:
        for item in data.get(key, []):
            if "entropy" in item:
                item["entropy"] = float(item["entropy"])
            if "expected_remaining" in item:
                item["expected_remaining"] = float(item["expected_remaining"])

    # Total remaining words
    data["total_remaining"] = data.get("remaining_count", len(data.get("viable_answers", [])))

    return jsonify(data)

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


if __name__ == '__main__':
    app.run(debug=True)
