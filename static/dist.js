document.addEventListener("DOMContentLoaded", () => {
    const params = new URLSearchParams(window.location.search);
    const guess = params.get("guess");
    const history = JSON.parse(params.get("history") || "[]");

    document.getElementById("guess-title").textContent = `Distribution for "${guess}"`;

    renderHistoryGrid(history);
    fetchDistribution(guess, history);
    setupSidebar();
});

function setupSidebar() {
    const sidebar = document.getElementById("sidebar");
    const toggleBtn = document.getElementById("toggleSidebar");
    toggleBtn.addEventListener("click", () => {
        sidebar.classList.toggle("closed");
    });
}

function renderHistoryGrid(history) {
    const grid = document.getElementById("grid");
    grid.innerHTML = "";
    const rows = history.length;
    const cols = history[0]?.guess.length || 5;

    grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
    grid.style.gridTemplateRows = `repeat(${rows}, 1fr)`;

    history.forEach((h) => {
        for (let i = 0; i < cols; i++) {
            const div = document.createElement("div");
            div.className = "cell " + h.feedback[i];
            div.textContent = h.guess[i].toUpperCase();
            grid.appendChild(div);
        }
    });
}

function fetchDistribution(guess, history) {
    fetch("/distribution_data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ guess, history })
    })
        .then(res => res.json())
        .then(data => renderChart(data));
}


function renderChart(data) {
    const ctx = document.getElementById("distributionChart").getContext("2d");

    // Extract and sort distribution data by remaining word count (numeric)
    const entries = Object.entries(data.distribution)
        .map(([remaining, count]) => [Number(remaining), count])
        .sort((a, b) => a[0] - b[0]);

    const labels = entries.map(([remaining]) => remaining);
    const values = entries.map(([_, count]) => count);

    // Clear any previous chart before drawing a new one
    if (window.currentChart) {
        window.currentChart.destroy();
    }

    window.currentChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: "Possible Answers → Remaining Word Count",
                data: values,
                backgroundColor: "#6aaa64" 
            }]
        },
        options: {
            scales: {
                x: {
                    title: { display: true, text: "Words Remaining After Guess" }
                },
                y: {
                    title: { display: true, text: "Number of Possible Answers" },
                    beginAtZero: true
                }
            },
            plugins: {
                title: {
                    display: true,
                    text: `Expected Remaining: ${data.expected_remaining.toFixed(2)}`
                },
                tooltip: {
                    callbacks: {
                        label: (context) =>
                            `${context.parsed.y} answers leave ${context.parsed.x} remaining`
                    }
                }
            }
        }
    });
}
