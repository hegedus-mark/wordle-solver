let currentRow = 0;
let currentCol = 0;
let answerLength = 5;
let maxGuesses = 6
let gridCells = [];
let guessArray = [];
let sessionHistoryArray = [];

// Initialize game
document.addEventListener("DOMContentLoaded", startGame);
document.addEventListener('keydown', actionEvent);


function startGame() {
    fetch('/start_game')
        .then(res => res.json())
        .then(data => {
            answerLength = data.answer_length;
            initGrid();
            updateBestOptions()
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
    currentRow = 0;
    currentCol = 0;
    answerLength = 5;
    maxGuesses = 6
    gridCells = [];
    guessArray = [];
    startGame()
}

function activateCell(row, col) {
    // Only allow activating the current row
    if (row !== currentRow) return;

    // deactivate all
    gridCells.forEach(cell => cell.classList.remove('active'));

    currentCol = col;
    const idx = row * answerLength + col;
    gridCells[idx].classList.add('active');
}

function actionEvent(e) {
    if (currentRow >= maxGuesses) return;

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

    const entropyTop = document.getElementById('entropy-top');
    const entropyBottom = document.getElementById('entropy-bottom');
    const expectedTop = document.getElementById('expected-top');
    const expectedBottom = document.getElementById('expected-bottom');
    const totalRemaining = document.getElementById('total-remaining');

    entropyTop.innerHTML = '';
    entropyBottom.innerHTML = '';
    expectedTop.innerHTML = '';
    expectedBottom.innerHTML = '';

    fetch('/best_options?' + new URLSearchParams({ history: JSON.stringify(sessionHistoryArray) }))
        .then(res => res.json())
        .then(data => {
            totalRemaining.textContent = `Remaining words: ${data.total_remaining}`;

            function makeClickableLi(item, label) {
                const li = document.createElement('li');
                li.innerHTML = `<strong>${item.word.toUpperCase()}</strong> ${label}`;
                li.style.cursor = 'pointer';
                li.addEventListener('click', () => {
                    localStorage.setItem('wordle_history', JSON.stringify(sessionHistoryArray));

                    const url = new URL(window.location.origin + '/distribution');
                    url.searchParams.set('guess', item.word);
                    url.searchParams.set('history', JSON.stringify(sessionHistoryArray));
                    window.location.href = url.toString();
                });
                return li;
            }

            /// Entropy lists
            data.top_entropy.forEach(item => {
                entropyTop.appendChild(makeClickableLi(item, `(${item.entropy.toFixed(2)} bits)`));
            });

            if (data.bot_entropy) {
                data.bot_entropy.forEach(item => {
                    entropyBottom.appendChild(makeClickableLi(item, `(${item.entropy.toFixed(2)} bits)`));
                });
            }

            // Expected remaining lists
            data.top_expected_remaining.forEach(item => {
                expectedTop.appendChild(makeClickableLi(item, `(${item.expected_remaining.toFixed(1)} rem)`));
            });
            
            if (data.bot_expected_remaining) {
                data.bot_expected_remaining.forEach(item => {
                    expectedBottom.appendChild(makeClickableLi(item, `(${item.expected_remaining.toFixed(1)} rem)`));
                });
            }

            toggleLoadingOptions();
        })
        .catch(err => console.error(err));
}


function submitGuess() {
    const guess = guessArray[currentRow].join('');
    if (guess.length !== answerLength) return;

    fetch('/guess', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guess })
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
