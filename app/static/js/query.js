document.getElementById('searchForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const packageName = document.getElementById('packageInput').value.trim();
    const repo = document.getElementById('repoSelect').value;
    
    if (!packageName) return;
    
    showLoading();
    
    try {
        const response = await fetch(
            `/api/search?package=${encodeURIComponent(packageName)}${repo ? `&repo=${repo}` : ''}`
        );
        const data = await response.json();
        displayResults(data);
    } catch (error) {
        showError(error);
    } finally {
        hideLoading();
    }
});

function displayResults(data) {
    const container = document.getElementById('packageResults');
    container.innerHTML = '';
    
    if (data.results.length === 0) {
        container.innerHTML = `
            <div class="alert alert-warning">
                No packages found matching "${data.query}"
            </div>`;
    } else {
        data.results.forEach(result => {
            const pkg = result.package;
            container.innerHTML += `
            <div class="card package-card mb-3">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h5 class="card-title">${pkg.name}</h5>
                            <h6 class="card-subtitle mb-2 text-muted">
                                <span class="badge version-badge me-2">
                                    ${pkg.version.ver}-${pkg.version.rel}
                                </span>
                                <span class="badge bg-secondary">
                                    ${pkg.arch}
                                </span>
                            </h6>
                            <p class="card-text">${pkg.summary}</p>
                        </div>
                        <span class="badge bg-orange">${result.repo}</span>
                    </div>
                </div>
            </div>`;
        });
    }
    
    document.getElementById('resultsContainer').style.display = 'block';
}

// Shared UI functions with RepoDiff
function showLoading() {
    // Implement similar to RepoDiff
}

function hideLoading() {
    // Implement similar to RepoDiff
}

function showError(error) {
    // Implement similar to RepoDiff
}
