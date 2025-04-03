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
            const card = document.createElement('div');
            card.className = 'card package-card mb-3';
            card.innerHTML = `
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
                </div>`;
            
            container.appendChild(card);
            
            // Add all versions section if available
            if (result.all_versions && result.all_versions.length > 1) {
                const sortedVersions = [...result.all_versions].sort((a, b) => {
                    const verA = `${a.package.version.epoch ? a.package.version.epoch + ':' : ''}${a.package.version.ver}-${a.package.version.rel}`;
                    const verB = `${b.package.version.epoch ? b.package.version.epoch + ':' : ''}${b.package.version.ver}-${b.package.version.rel}`;
                    return verB.localeCompare(verA);
                });
                
                const versionsHtml = `
                    <div class="all-versions mt-3">
                        <h6 class="text-orange">
                            <i class="fas fa-layer-group me-2"></i>
                            All Available Versions (${result.all_versions.length})
                        </h6>
                        <div class="list-group">
                            ${sortedVersions.map(ver => `
                                <div class="list-group-item ${ver.package.name === pkg.name && ver.package.version.ver === pkg.version.ver ? 'active-version' : ''}">
                                    <div class="d-flex justify-content-between">
                                        <div>
                                            <strong>v${ver.package.version.ver}-${ver.package.version.rel}</strong>
                                            ${ver.package.version.epoch ? ` <span class="text-muted">(epoch: ${ver.package.version.epoch})</span>` : ''}
                                        </div>
                                        <div>
                                            <span class="badge bg-primary">${ver.repo}</span>
                                            ${ver.version_tags?.filter(t => t).map(t => 
                                                `<span class="badge bg-info ms-1">${t}</span>`
                                            ).join('')}
                                        </div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>`;
                
                card.querySelector('.card-body').innerHTML += versionsHtml;
            }
        });
    }
    
    document.getElementById('resultsContainer').style.display = 'block';
}
