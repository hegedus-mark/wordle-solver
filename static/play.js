let currentRow = 0;
let currentCol = 0;
let answerLength = 5;
let maxGuesses = 6
let gridCells = [];
let guessArray = [];
let sessionHistoryArray = [];
let gameMode = 'auto';
let manualClickCount = [];
let letterFeedbackMap = {};
let fullOptionsData = { answers: [], guesses: [] };


// Initialize game
document.addEventListener("DOMContentLoaded", startGame);
document.addEventListener('keydown', actionEvent);



function onModeChange() {
    const select = document.getElementById('game-mode');
    const input = document.getElementById('manual-answer-input');
    const startBtn = document.getElementById('manual-answer-start');

    gameMode = select.value;
    localStorage.setItem('wordle_mode', gameMode);

    // Reset all game state
    currentRow = 0;
    currentCol = 0;
    gridCells = [];
    guessArray = Array.from({ length: maxGuesses }, () => Array(answerLength).fill(''));
    sessionHistoryArray = [];
    manualClickCount = Array(maxGuesses).fill(null).map(() => Array(answerLength).fill(0));

    // Show/hide input
    if (gameMode === 'manual-answer') {
        input.style.display = 'inline-block';
        startBtn.style.display = 'inline-block';
    } else {
        input.style.display = 'none';
        startBtn.style.display = 'none';
        startGame();
    }

    // Clear previous grid
    const grid = document.getElementById('grid');
    if (grid) grid.innerHTML = '';
}

function startGame() {
    let payload = {};

    if (gameMode === 'manual-answer') {
        const answer = document.getElementById('manual-answer-input').value.trim().toLowerCase();
        if (!answer) {
            alert('Please type a word for Manual Answer mode');
            return;
        }
        payload.answer = answer;
    }

    if (gameMode === 'manual-feedback') {
        payload.manual_feedback = true;
    }

    fetch('/start_game', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(res => res.json())
        .then(data => {
            answerLength = data.answer_length;
            manualClickCount = Array(maxGuesses).fill(null).map(() => Array(answerLength).fill(0));
            initGrid();
            updateBestOptions();
        });
}

function initGrid() {
    const grid = document.getElementById('grid');
    grid.innerHTML = '';
    gridCells = [];
    guessArray = Array.from({ length: maxGuesses }, () => Array(answerLength).fill(''));
    grid.style.gridTemplateColumns = `repeat(${answerLength}, 1fr)`;
    grid.style.gridTemplateRows = `repeat(${maxGuesses}, 1fr)`
    for (let r = 0; r < maxGuesses; r++) {
        for (let c = 0; c < answerLength; c++) {
            const div = document.createElement('div');
            div.className = 'cell';
            div.dataset.row = r;
            div.dataset.col = c;
            div.addEventListener('click', () => activateCell(r, c));
            grid.appendChild(div);
            gridCells.push(div);
        }
    }
    activateCell(0, 0);
}

function restartGame() {
    window.location.reload();
}

function activateCell(row, col) {
    // Only allow activating the current row
    if (gameMode !== 'manual-feedback') {
        if ((row !== currentRow)) return;
    } else {
        if (row > currentRow) return;
    }


    gridCells.forEach(cell => cell.classList.remove('active'));
    currentCol = col;
    const idx = row * answerLength + col;
    gridCells[idx].classList.add('active');

    if (gameMode === 'manual-feedback') {
        gridCells[idx].onclick = () => cycleFeedback(row, col);
    }
}

function logFeedback(message) {
    const logBox = document.getElementById('feedback-log');
    if (!logBox) return;
    const p = document.createElement('p');
    p.textContent = message;
    logBox.appendChild(p);
    while (logBox.childNodes.length > 10) logBox.removeChild(logBox.firstChild);
}

function cycleFeedback(row, col) {
    const letter = guessArray[row][col];
    if (!letter) return;

    let oldFb = manualClickCount[row][col] || 0;

    // Cycle feedback
    let count = (oldFb + 1) % 3; // 0=B, 1=Y, 2=G
    manualClickCount[row][col] = count;
    const fbChar = 'BYG'[count];

    logFeedback(`Letter "${letter}" at col ${col + 1}: ${'BYG'[oldFb]} → ${fbChar}`);

    // Update letterFeedbackMap by column
    if (!letterFeedbackMap[letter]) letterFeedbackMap[letter] = {};
    letterFeedbackMap[letter][col] = fbChar;

    updateCellFeedback(row, col);
}

function propagateFeedbackAfterSubmit() {
    letterFeedbackMap = {}; // reset map

    for (let r = 0; r <= currentRow; r++) {
        for (let c = 0; c < answerLength; c++) {
            const letter = guessArray[r][c];
            if (!letter) continue;

            const fbChar = 'BYG'[manualClickCount[r][c]];

            if (!letterFeedbackMap[letter]) letterFeedbackMap[letter] = {};
            letterFeedbackMap[letter][c] = fbChar;
        }
    }

    // Apply propagation across all rows and columns
    for (let r = 0; r <= currentRow; r++) {
        for (let c = 0; c < answerLength; c++) {
            const letter = guessArray[r][c];
            if (!letter || !letterFeedbackMap[letter]) continue;

            const fbChar = letterFeedbackMap[letter][c];
            manualClickCount[r][c] = 'BYG'.indexOf(fbChar);
            updateCellFeedback(r, c);
        }
    }

    logFeedback(`Feedback propagated across all rows after submission`);
}

function updateCellFeedback(row, col) {
    const idx = row * answerLength + col;
    const feedbackChar = 'BYG'[manualClickCount[row][col]];
    gridCells[idx].className = 'cell ' + feedbackChar;
    gridCells[idx].textContent = guessArray[row][col] || '';
}

function actionEvent(e) {
    if (currentRow >= maxGuesses) return;
    if (document.activeElement.tagName === 'INPUT') return;
    // Only allow typing in current row
    if (e.key.length === 1 && /^[a-zA-Z]$/.test(e.key)) {
        if (currentCol >= answerLength) return;
        const idx = currentRow * answerLength + currentCol;
        gridCells[idx].textContent = e.key.toUpperCase();
        guessArray[currentRow][currentCol] = e.key.toUpperCase();

        if (currentCol < answerLength - 1) activateCell(currentRow, currentCol + 1);

    } else if (e.key === 'Backspace') {
        const idx = currentRow * answerLength + currentCol;

        if (guessArray[currentRow][currentCol] === '') {
            if (currentCol > 0) activateCell(currentRow, currentCol - 1);
        }

        const idxBack = currentRow * answerLength + currentCol;
        gridCells[idxBack].textContent = '';
        guessArray[currentRow][currentCol] = '';
    } else if (e.key === 'Enter') {
        submitGuess();
    }
}

function toggleLoadingOptions() {
    const loadingComp = document.getElementById("loading-options");
    if (loadingComp.style.display == "none") {
        loadingComp.style.display = "block"
    } else {
        loadingComp.style.display = "none"
    }
}

function updateBestOptions() {
    toggleLoadingOptions();

    const sections = {
        entropyTop: document.getElementById('entropy-top'),
        entropyBottom: document.getElementById('entropy-bottom'),
        expectedTop: document.getElementById('expected-top'),
        expectedBottom: document.getElementById('expected-bottom'),
        viableAnswers: document.getElementById('viable-answers'),
        topRemaining: document.getElementById('top-remaining'),
        botRemaining: document.getElementById('bot-remaining'),
        totalRemaining: document.getElementById('total-remaining')
    };

    // Clear all lists
    Object.values(sections).forEach(el => { if (el) el.innerHTML = ''; });

    fetch('/best_options?' + new URLSearchParams({ history: JSON.stringify(sessionHistoryArray) }))
        .then(res => res.json())
        .then(data => {
            sections.totalRemaining.textContent = `Remaining words: ${data.total_remaining}`;

            function makeClickableLi(item, label) {
                const li = document.createElement('li');
                li.innerHTML = `<strong>${item[0].toUpperCase()}</strong> ${label}`;
                li.style.cursor = 'pointer';
                li.addEventListener('click', () => {
                    localStorage.setItem('wordle_history', JSON.stringify(sessionHistoryArray));
                    const url = new URL(window.location.origin + '/distribution');
                    url.searchParams.set('guess', item[0]);
                    url.searchParams.set('history', JSON.stringify(sessionHistoryArray));
                    window.location.href = url.toString();
                });
                return li;
            }

            // Top/Bottom entropy
            data.top_entropy.forEach(item => sections.entropyTop.appendChild(makeClickableLi(item, `(${item[1].toFixed(2)} bits)`)));
            data.bot_entropy.forEach(item => sections.entropyBottom.appendChild(makeClickableLi(item, `(${item[1].toFixed(2)} bits)`)));

            // Top/Bottom expected remaining
            data.top_remaining.forEach(item => sections.topRemaining.appendChild(makeClickableLi(item, `(${item[2].toFixed(1)} rem)`)));
            data.bot_remaining.forEach(item => sections.botRemaining.appendChild(makeClickableLi(item, `(${item[2].toFixed(1)} rem)`)));

            // Viable answers
            data.viable_answers.forEach(item => sections.viableAnswers.appendChild(makeClickableLi(item, `(${item[1].toFixed(2)} bits, ${item[2].toFixed(1)} rem)`)));

            toggleLoadingOptions();
        })
        .catch(err => console.error(err));
}

function prepareGuessPayload() {
    let guess = guessArray[currentRow].join('');
    if (gameMode === 'manual-feedback' && guess === '') {
        currentRow--;
    }
    guess = guessArray[currentRow].join('');
    if (guess.length !== answerLength) return null;

    if (gameMode === 'manual-feedback') {
        propagateFeedbackAfterSubmit();
    }

    let payload = { guess };

    if (gameMode === 'manual-feedback') {
        const fullHistory = [];
        for (let r = 0; r <= currentRow; r++) {
            const rowGuess = guessArray[r].join('');
            const rowFeedback = manualClickCount[r].map(i => 'BYG'[i]).join('');
            fullHistory.push({ guess: rowGuess, feedback: rowFeedback });
        }
        payload.history = fullHistory;
        payload.feedback = manualClickCount[currentRow].map(i => 'BYG'[i]).join('');
    }

    return payload;
}

function submitGuess() {
    const payload = prepareGuessPayload();
    if (!payload) return;

    fetch('/guess', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).then(res => res.json())
        .then(data => {
            if (data.error) {
                document.getElementById('message').textContent = data.error;
                return;
            }
            renderFeedback(data.history);
            sessionHistoryArray = data.history.map(h => ({
                guess: h.guess,
                feedback: h.feedback
            }));

            if (gameMode === 'manual-feedback') {
                propagateFeedbackAfterSubmit();
            }

            updateBestOptions();
            if (data.win) document.getElementById('message').textContent = "You Win!";
            else if (data.done) document.getElementById('message').textContent = "Game Over!";
            if (!data.done && !data.win) {
                activateCell(currentRow, 0);
            }
        });
}

function renderFeedback(history) {
    history.forEach((h, row) => {
        for (let c = 0; c < answerLength; c++) {
            const idx = row * answerLength + c;
            const cell = gridCells[idx];
            cell.textContent = h.guess[c];

            cell.className = 'cell ' + h.feedback[c] + ' locked';
        }
    });

    currentRow = history.length < maxGuesses ? history.length : maxGuesses;
    currentCol = 0;

    if (currentRow < maxGuesses) {
        activateCell(currentRow, 0);
    }
}

function loadFullOptions() {
    fullOptionsData = { answers: [], guesses: [] };
    if (document.getElementById('options-panel').style.display == 'none') {
        document.getElementById('options-panel').style.display = 'block';
        document.getElementById('full-options-panel').style.display = 'none';
        return;
    }
    document.getElementById('options-panel').style.display = 'none';
    toggleLoadingOptions();

    fetch('/full_options?' + new URLSearchParams({ history: JSON.stringify(sessionHistoryArray) }))
        .then(res => res.json())
        .then(data => {
            fullOptionsData.answers = data.viable_answers.map((item, idx) => ({ ...item, index: idx }));
            fullOptionsData.guesses = data.viable_guesses.map((item, idx) => ({ ...item, index: idx }));

            displayFullOptions(fullOptionsData);

            document.getElementById('full-options-panel').style.display = 'block';
            toggleLoadingOptions();
        });
}

function displayFullOptions(data) {
    const ulAnswers = document.getElementById('full-viable-answers');
    const ulGuesses = document.getElementById('full-viable-guesses');

    ulAnswers.innerHTML = '';
    ulGuesses.innerHTML = '';

    data.answers.forEach(item => {
        const li = document.createElement('li');
        li.textContent = `${item.index + 1}. ${item.word.toUpperCase()} | Entropy: ${item.entropy.toFixed(2)}, Expected: ${item.expected.toFixed(1)}`;
        li.dataset.word = item.word.toLowerCase();
        ulAnswers.appendChild(li);
    });

    data.guesses.forEach(item => {
        const li = document.createElement('li');
        li.textContent = `${item.index + 1}. ${item.word.toUpperCase()} | Entropy: ${item.entropy.toFixed(2)}, Expected: ${item.expected.toFixed(1)}`;
        li.dataset.word = item.word.toLowerCase();
        ulGuesses.appendChild(li);
    });
}

function filterFullOptions() {
    const answerFilterRaw = document.getElementById('search-answers').value.toLowerCase();
    const guessFilterRaw = document.getElementById('search-guesses').value.toLowerCase();

    // put /r in the beginning to use regex 
    function createFilterRegex(raw) {
        if (!raw) return null;
        const parts = raw.split(',').map(p => p.trim().replace(/^\r/, ''));
        const pattern = parts.map(p => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
        return new RegExp(pattern, 'i');
    }

    const answerRegex = createFilterRegex(answerFilterRaw);
    const guessRegex = createFilterRegex(guessFilterRaw);

    document.querySelectorAll('#full-viable-answers li').forEach(li => {
        const word = li.dataset.word.replace(/^\r/, '');
        li.style.display = answerRegex && !answerRegex.test(word) ? 'none' : '';
    });

    document.querySelectorAll('#full-viable-guesses li').forEach(li => {
        const word = li.dataset.word.replace(/^\r/, '');
        li.style.display = guessRegex && !guessRegex.test(word) ? 'none' : '';
    });
}