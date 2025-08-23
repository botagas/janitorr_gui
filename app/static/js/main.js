    // Load media thumbnails
document.addEventListener('DOMContentLoaded', () => {
    // Mobile navigation menu toggle
    const mobileToggle = document.querySelector('.mobile-menu-toggle');
    const navMenu = document.querySelector('.nav-menu');
    
    if (mobileToggle && navMenu) {
        mobileToggle.addEventListener('click', () => {
            mobileToggle.classList.toggle('active');
            navMenu.classList.toggle('active');
        });
        
        // Close menu when clicking on nav links
        const navLinks = navMenu.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', () => {
                mobileToggle.classList.remove('active');
                navMenu.classList.remove('active');
            });
        });
        
        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!mobileToggle.contains(e.target) && !navMenu.contains(e.target)) {
                mobileToggle.classList.remove('active');
                navMenu.classList.remove('active');
            }
        });
    }
    
    const mediaCards = document.querySelectorAll('.media-card');
    
    mediaCards.forEach(card => {
        const mediaId = card.dataset.mediaId;
        if (!mediaId) return;  // Skip if no media ID
        
        const thumbnailContainer = card.querySelector('.media-thumbnail');
        if (!thumbnailContainer) return;  // Skip if no thumbnail container
        
        // Insert image without removing overlay elements already inside the thumbnail
        const img = document.createElement('img');
        img.src = `/jellyfin/Items/${mediaId}/Images/Primary`;
        img.alt = 'Media thumbnail';
        img.onload = () => {
            // Remove only the loading placeholder if present
            const placeholder = thumbnailContainer.querySelector('.no-thumbnail');
            if (placeholder) placeholder.remove();
        };
        img.onerror = () => {
            console.error('Error loading image for media:', mediaId);
            // Show fallback but keep overlays intact
            const existingPlaceholder = thumbnailContainer.querySelector('.no-thumbnail');
            if (!existingPlaceholder) {
                const fallback = document.createElement('div');
                fallback.className = 'no-thumbnail';
                fallback.textContent = 'No Image Available';
                thumbnailContainer.appendChild(fallback);
            }
        };
        // Prepend the image so overlays remain above it
        thumbnailContainer.prepend(img);
    });
    
    // Handle configuration form submission
    const configForm = document.getElementById('config-form');
    if (configForm) {
        configForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(configForm);
            const config = {};
            
            // Convert flat form data to nested object
            for (const [key, value] of formData.entries()) {
                const keys = key.split('.');
                let current = config;
                
                keys.forEach((k, i) => {
                    if (i === keys.length - 1) {
                        current[k] = value;
                    } else {
                        current[k] = current[k] || {};
                        current = current[k];
                    }
                });
            }
            
            try {
                const response = await fetch('/config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(config)
                });
                
                if (response.ok) {
                    alert('Configuration saved successfully!');
                } else {
                    alert('Failed to save configuration.');
                }
            } catch (error) {
                console.error('Error saving configuration:', error);
                alert('Failed to save configuration.');
            }
        });
    }
    
    // --- Search and Pagination ---
    const searchInput = document.getElementById('media-search');
    const paginationTop = document.getElementById('media-pagination-top');
    const paginationBottom = document.getElementById('media-pagination-bottom');
    const mediaGrid = document.getElementById('media-grid');

    let allCards = [];
    let filteredCards = [];
    let currentPage = 1;
    const cardsPerPage = 9;

    function updateCards() {
        // Always get cards from the current grid (works for both views)
        allCards = Array.from(document.querySelectorAll('.media-grid .media-card'));
        // Apply current search filter
        const query = (searchInput && searchInput.value.trim().toLowerCase()) || '';
        filteredCards = allCards.filter(card => {
            const title = card.querySelector('.media-title');
            return title && title.textContent.toLowerCase().includes(query);
        });
    }

    function renderPage() {
        updateCards();
        // Hide all cards
        allCards.forEach(card => card.style.display = 'none');
        // Show only cards for current page
        const start = (currentPage - 1) * cardsPerPage;
        const end = start + cardsPerPage;
        filteredCards.slice(start, end).forEach(card => card.style.display = '');
        renderPagination(paginationTop);
        renderPagination(paginationBottom);
    }

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            currentPage = 1;
            renderPage();
        });
    }

    function renderPagination(paginationElem) {
        if (!paginationElem) return;
        const totalPages = Math.ceil(filteredCards.length / cardsPerPage) || 1;
        let html = '';
        if (totalPages > 1) {
            html += `<button class="page-btn" data-page="prev" ${currentPage === 1 ? 'disabled' : ''}>&laquo;</button>`;
            let startPage = Math.max(1, currentPage - 2);
            let endPage = Math.min(totalPages, currentPage + 2);
            if (startPage > 1) {
                html += `<button class="page-btn" data-page="1">1</button>`;
                if (startPage > 2) html += `<span class="page-ellipsis">…</span>`;
            }
            for (let i = startPage; i <= endPage; i++) {
                html += `<button class="page-btn${i === currentPage ? ' active' : ''}" data-page="${i}">${i}</button>`;
            }
            if (endPage < totalPages) {
                if (endPage < totalPages - 1) html += `<span class="page-ellipsis">…</span>`;
                html += `<button class="page-btn" data-page="${totalPages}">${totalPages}</button>`;
            }
            html += `<button class="page-btn" data-page="next" ${currentPage === totalPages ? 'disabled' : ''}>&raquo;</button>`;
        }
        paginationElem.innerHTML = html;
        // Add event listeners
        paginationElem.querySelectorAll('.page-btn').forEach(btn => {
            btn.addEventListener('click', e => {
                const page = btn.getAttribute('data-page');
                if (page === 'prev' && currentPage > 1) {
                    currentPage--;
                } else if (page === 'next' && currentPage < totalPages) {
                    currentPage++;
                } else if (!isNaN(page)) {
                    currentPage = parseInt(page);
                }
                renderPage();
            });
        });
    }
    const gridViewBtn = document.getElementById('grid-view-btn');
    const listViewBtn = document.getElementById('list-view-btn');
    const mediaContainer = document.getElementById('media-container');

    if (gridViewBtn && listViewBtn && mediaContainer) {
        // Load saved view preference from localStorage
        const savedView = localStorage.getItem('mediaView') || 'grid';
        setView(savedView);

        gridViewBtn.addEventListener('click', () => setView('grid'));
        listViewBtn.addEventListener('click', () => setView('list'));

        function setView(view) {
            if (view === 'list') {
                mediaContainer.classList.add('list-view');
                gridViewBtn.classList.remove('active');
                listViewBtn.classList.add('active');
            } else {
                mediaContainer.classList.remove('list-view');
                gridViewBtn.classList.add('active');
                listViewBtn.classList.remove('active');
            }
            // Save preference to localStorage
            localStorage.setItem('mediaView', view);
            // Re-render page to ensure correct cards are shown after view change
            currentPage = 1;
            renderPage();
        }
    }
});
