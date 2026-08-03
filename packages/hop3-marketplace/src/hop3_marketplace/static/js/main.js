// Hop3 Marketplace - Client-side search

let searchIndex = [];
let searchInput = null;
let searchResults = null;
let selectedIndex = -1;

// Initialize search
async function initSearch() {
    searchInput = document.getElementById('search-input');
    searchResults = document.getElementById('search-results');

    if (!searchInput || !searchResults) {
        return;
    }

    // Load search index
    try {
        const response = await fetch('/search-index.json');
        searchIndex = await response.json();
    } catch (e) {
        console.error('Could not load search index:', e);
        return;
    }

    // Set up event listeners
    searchInput.addEventListener('input', handleSearch);
    searchInput.addEventListener('focus', handleSearch);
    searchInput.addEventListener('keydown', handleKeydown);
}

function handleSearch() {
    const query = searchInput.value.trim().toLowerCase();
    selectedIndex = -1;

    if (query.length < 2) {
        searchResults.classList.remove('active');
        return;
    }

    const results = searchIndex.filter(app => {
        const titleMatch = app.title.toLowerCase().includes(query);
        const descMatch = app.description.toLowerCase().includes(query);
        const tagMatch = app.tags.some(tag => tag.toLowerCase().includes(query));
        const authorMatch = app.author.toLowerCase().includes(query);
        return titleMatch || descMatch || tagMatch || authorMatch;
    }).slice(0, 8);

    if (results.length === 0) {
        searchResults.innerHTML = '<div class="search-result-item search-result-empty">No apps found</div>';
    } else {
        searchResults.innerHTML = results.map((app, index) => `
            <a href="${app.url}" class="search-result-item" data-index="${index}">
                <div class="search-result-title">${highlightMatch(app.title, query)}</div>
                <div class="search-result-desc">${truncate(app.description, 80)}</div>
            </a>
        `).join('');
    }

    searchResults.classList.add('active');
}

function highlightMatch(text, query) {
    const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
    return text.replace(regex, '<strong>$1</strong>');
}

function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function truncate(text, length) {
    if (text.length <= length) return text;
    return text.substring(0, length) + '...';
}

function updateSelection(items) {
    items.forEach((item, index) => {
        if (index === selectedIndex) {
            item.classList.add('selected');
            item.scrollIntoView({ block: 'nearest' });
        } else {
            item.classList.remove('selected');
        }
    });
}

function handleKeydown(e) {
    const items = Array.from(searchResults.querySelectorAll('.search-result-item[href]'));

    if (!searchResults.classList.contains('active') || items.length === 0) {
        return;
    }

    switch (e.key) {
        case 'ArrowDown':
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
            updateSelection(items);
            break;

        case 'ArrowUp':
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, 0);
            updateSelection(items);
            break;

        case 'Enter':
            e.preventDefault();
            if (selectedIndex >= 0 && items[selectedIndex]) {
                window.location.href = items[selectedIndex].href;
            } else if (items.length > 0) {
                window.location.href = items[0].href;
            }
            break;

        case 'Escape':
            e.preventDefault();
            searchResults.classList.remove('active');
            selectedIndex = -1;
            searchInput.blur();
            break;
    }
}

// Global keyboard shortcut (Ctrl+K or Cmd+K)
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }
});

// Close search when clicking outside
document.addEventListener('click', (e) => {
    if (searchInput && searchResults) {
        const isClickInside = searchInput.contains(e.target) || searchResults.contains(e.target);
        if (!isClickInside) {
            searchResults.classList.remove('active');
            selectedIndex = -1;
        }
    }
});

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', initSearch);
