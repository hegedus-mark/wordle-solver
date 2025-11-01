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
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ guess, history })
    })
    .then(res => res.json())
    .then(data => renderChart(data));
}

function feedbackColor(p) {
    const greens = (p.match(/G/g) || []).length;
    const yellows = (p.match(/Y/g) || []).length;
    if (greens >= 3) return "#6aaa64"; // green
    if (yellows >= 3) return "#c9b458"; // yellow
    return "#787c7e"; // gray
}

function feedbackComplexity(p) {
    const greens = [...p].filter(c => c === 'G').length;
    const yellows = [...p].filter(c => c === 'Y').length;
    return greens * 10 + yellows; // prioritize greens first
}

function renderChart(data) {
    const ctx = document.getElementById("distributionChart").getContext("2d");
    
    const entries = Object.entries(data.pattern_counts)
        .sort((a, b) => feedbackComplexity(a[0]) - feedbackComplexity(b[0]));

    const labels = entries.map(([pattern]) => pattern);
    const values = entries.map(([_, count]) => count);

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: "Possible Answers per Feedback",
                data: values,
                backgroundColor: labels.map(l => feedbackColor(l))
            }]
        },
        options: {
            indexAxis: 'y',
            scales: {
                x: { title: { display: true, text: "Number of Words" } },
                y: { title: { display: true, text: "Feedback Pattern" } }
            }
        }
    });
}
