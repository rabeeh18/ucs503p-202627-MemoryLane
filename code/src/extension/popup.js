document.addEventListener('DOMContentLoaded', () => {
    // Tab Switching
    const tabSave = document.getElementById('tab-save');
    const tabSearch = document.getElementById('tab-search');
    const contentSave = document.getElementById('content-save');
    const contentSearch = document.getElementById('content-search');

    tabSave.addEventListener('click', () => {
        tabSave.classList.add('active');
        tabSearch.classList.remove('active');
        contentSave.classList.add('active');
        contentSearch.classList.remove('active');
    });

    tabSearch.addEventListener('click', () => {
        tabSearch.classList.add('active');
        tabSave.classList.remove('active');
        contentSearch.classList.add('active');
        contentSave.classList.remove('active');
    });

    // Save Logic
    const btnSave = document.getElementById('btn-save');
    const saveStatus = document.getElementById('save-status');

    function showSaveStatus(message, type) {
        saveStatus.textContent = message;
        saveStatus.className = `status-msg ${type}`;
    }

    btnSave.addEventListener('click', async () => {
        showSaveStatus('Saving...', 'info');
        btnSave.disabled = true;

        try {
            const response = await chrome.runtime.sendMessage({ type: 'SAVE_CURRENT_PAGE' });
            if (!response || !response.ok) {
                throw new Error((response && response.error) || 'Failed to save memory');
            }
            showSaveStatus('Saved!', 'success');
            setTimeout(() => { saveStatus.className = 'status-msg'; }, 3000);
        } catch (error) {
            showSaveStatus(error.message, 'error');
        } finally {
            btnSave.disabled = false;
        }
    });

    // Search Logic
    const searchInput = document.getElementById('search-input');
    const btnSearch = document.getElementById('btn-search');
    const searchStatus = document.getElementById('search-status');
    const searchResults = document.getElementById('search-results');

    function showSearchStatus(message, type) {
        searchStatus.textContent = message;
        searchStatus.className = `status-msg ${type}`;
        if(type === 'info') searchResults.innerHTML = '';
    }

    async function performSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        showSearchStatus('Searching...', 'info');
        btnSearch.disabled = true;

        try {
            const response = await fetch('http://localhost:8000/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: query,
                    num_results: 5,
                    summarize: true,
                    debug: false
                })
            });

            if (!response.ok) throw new Error('Search failed');

            const data = await response.json();
            
            searchStatus.className = 'status-msg'; // hide
            searchResults.innerHTML = '';

            if (!data.results || data.results.length === 0) {
                showSearchStatus('No results found.', 'info');
                return;
            }

            data.results.forEach(result => {
                const card = document.createElement('div');
                card.className = 'result-card';
                
                const title = document.createElement('h3');
                title.className = 'result-title';
                const link = document.createElement('a');
                link.href = result.url;
                link.target = '_blank';
                link.textContent = result.title || 'Untitled';
                title.appendChild(link);
                
                const meta = document.createElement('div');
                meta.className = 'result-meta';
                const dateStr = result.timestamp ? new Date(result.timestamp).toLocaleDateString() : 'Unknown date';
                meta.textContent = `${result.domain} • ${dateStr}`;
                
                card.appendChild(title);
                card.appendChild(meta);

                if (result.summary) {
                    const summary = document.createElement('div');
                    summary.className = 'result-summary';
                    summary.textContent = result.summary;
                    card.appendChild(summary);
                }

                searchResults.appendChild(card);
            });

        } catch (error) {
            showSearchStatus('Error performing search', 'error');
        } finally {
            btnSearch.disabled = false;
        }
    }

    btnSearch.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performSearch();
    });
});
