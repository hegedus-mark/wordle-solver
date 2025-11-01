import random
import json

from solver import filter_words, get_and_decode_feedback, load_best_guesses_for_history, load_feedback_data
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


    results, remaining = load_best_guesses_for_history(history)

    top_n = 10

    sorted_by_entropy = sorted(results, key=lambda x: x[1], reverse=True)
    top_entropy = sorted_by_entropy[:top_n]
    bot_entropy = sorted_by_entropy[-top_n:]

    sorted_by_expected = sorted(results, key=lambda x: x[2])
    top_expected_remaining = sorted_by_expected[:top_n]
    bot_expected_remaining = sorted_by_expected[-top_n:]

    return jsonify({
        "top_entropy": [
            {"word": w, "entropy": e, "expected_remaining": er} 
            for w, e, er in top_entropy
        ],
        "bot_entropy":[
            {"word": w, "entropy": e, "expected_remaining": er} 
            for w, e, er in bot_entropy
        ],
        "top_expected_remaining": [
            {"word": w, "entropy": e, "expected_remaining": er} 
            for w, e, er in top_expected_remaining
        ],
        "bot_expected_remaining":[
            {"word": w, "entropy": e, "expected_remaining": er} 
            for w, e, er in bot_expected_remaining
        ],
        "total_remaining": len(remaining)
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

    words, feedback_matrix, word_to_index = load_feedback_data()

    remaining = filter_words(words, feedback_matrix, word_to_index, [
        (h["guess"].lower(), h["feedback"]) for h in history
    ])
    pattern_counts = {}
    for word in remaining:
        fb_str = get_and_decode_feedback(guess, word)
        pattern_counts[fb_str] = pattern_counts.get(fb_str, 0) + 1

    return jsonify({
        "guess": guess,
        "total_remaining": len(remaining),
        "pattern_counts": pattern_counts
    })


if __name__ == '__main__':
    app.run(debug=True)
