document.addEventListener('DOMContentLoaded', () => {
    const loginSection = document.getElementById('login-section');
    const adminContent = document.getElementById('admin-content');
    const loginForm = document.getElementById('login-form');
    const loginError = document.getElementById('login-error');
    const logoutButton = document.getElementById('logout-button');

    const shareForm = document.getElementById('share-form');
    const stashIdInput = document.getElementById('stash-id');
    const videoNameInput = document.getElementById('video-name');
    const daysValidInput = document.getElementById('days-valid');
    const lookupTitleButton = document.getElementById('lookup-title-button');
    const shareMessage = document.getElementById('share-message');
    const shareError = document.getElementById('share-error');

    const sharedVideosTableBody = document.querySelector('#shared-videos-table tbody');
    const refreshSharesButton = document.getElementById('refresh-shares');

    const editModal = document.getElementById('edit-modal');
    const editShareIdInput = document.getElementById('edit-share-id');
    const editVideoNameInput = document.getElementById('edit-video-name');
    const editDaysValidInput = document.getElementById('edit-days-valid');
    const saveEditButton = document.getElementById('save-edit-button');
    const cancelEditButton = document.getElementById('cancel-edit-button');
    const editError = document.getElementById('edit-error');

    let authToken = localStorage.getItem('kinpeek_token');

    // --- Helper Functions ---
    function showLogin() {
        loginSection.style.display = 'block';
        adminContent.style.display = 'none';
        localStorage.removeItem('kinpeek_token');
        authToken = null;
    }

    function showAdmin() {
        loginSection.style.display = 'none';
        adminContent.style.display = 'block';
        loginError.textContent = '';
        fetchSharedVideos();
    }

    function clearMessages() {
        loginError.textContent = '';
        shareMessage.textContent = '';
        shareError.textContent = '';
        editError.textContent = '';
    }

    async function apiRequest(url, method = 'GET', body = null, requiresAuth = true) {
        const headers = {
            'Content-Type': 'application/json',
        };
        if (requiresAuth) {
            if (!authToken) {
                showLogin();
                throw new Error('Not authenticated');
            }
            headers['Authorization'] = `Bearer ${authToken}`;
        }

        const options = {
            method,
            headers,
        };

        if (body) {
            options.body = JSON.stringify(body);
        }

        try {
            const response = await fetch(url, options);
            if (response.status === 401 && requiresAuth) {
                showLogin();
                throw new Error('Authentication failed');
            }
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
                throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
            }
            // Handle no content responses
            if (response.status === 204 || response.headers.get('content-length') === '0') {
                return null; 
            }
            return await response.json();
        } catch (error) {
            console.error('API Request Error:', error);
            throw error;
        }
    }

    // --- Initialization ---
    if (authToken) {
        // Simple check: Assume token is valid initially. 
        // A better check would be to make a test API call.
        showAdmin();
    } else {
        showLogin();
    }

    // --- Event Listeners ---
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        clearMessages();
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        
        // FastAPI's OAuth2PasswordRequestForm expects form data
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        try {
            const response = await fetch('/login', {
                method: 'POST',
                body: formData,
                headers: {
                     'Content-Type': 'application/x-www-form-urlencoded',
                }
            });

            if (!response.ok) {
                 const errorData = await response.json().catch(() => ({ detail: 'Login failed' }));
                 throw new Error(errorData.detail || `Login failed with status: ${response.status}`);
            }

            const data = await response.json();
            authToken = data.access_token;
            localStorage.setItem('kinpeek_token', authToken);
            showAdmin();
        } catch (error) {
            console.error('Login failed:', error);
            loginError.textContent = error.message;
            showLogin(); // Ensure user stays on login page on error
        }
    });

    logoutButton.addEventListener('click', () => {
        showLogin();
    });

    lookupTitleButton.addEventListener('click', async () => {
        clearMessages();
        const stashId = stashIdInput.value;
        if (!stashId) {
            shareError.textContent = 'Please enter a Stash Video ID.';
            return;
        }
        try {
            // *** Requires a new backend endpoint: /get_video_title/{stash_id} ***
            // This endpoint should use the Stash API key securely on the backend.
            const data = await apiRequest(`/get_video_title/${stashId}`); 
            if (data && data.title) {
                videoNameInput.value = data.title;
            } else {
                shareError.textContent = 'Could not find title for this ID.';
                videoNameInput.value = ''; // Clear if not found
            }
        } catch (error) {
            shareError.textContent = `Error looking up title: ${error.message}`;
            videoNameInput.value = '';
        }
    });

    shareForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        clearMessages();

        const shareData = {
            video_name: videoNameInput.value,
            stash_video_id: parseInt(stashIdInput.value, 10),
            days_valid: parseInt(daysValidInput.value, 10),
        };

        if (!shareData.video_name || isNaN(shareData.stash_video_id) || isNaN(shareData.days_valid)) {
            shareError.textContent = 'Please fill in all fields correctly.';
            return;
        }

        try {
            const result = await apiRequest('/share', 'POST', shareData);
            shareMessage.textContent = `Video shared successfully! URL: ${result.share_url}`;
            shareForm.reset(); // Clear the form
            fetchSharedVideos(); // Refresh the list
        } catch (error) {
            shareError.textContent = `Failed to share video: ${error.message}`;
        }
    });

    refreshSharesButton.addEventListener('click', fetchSharedVideos);

    // --- Shared Videos Table Logic ---
    async function fetchSharedVideos() {
        try {
            const videos = await apiRequest('/shared_videos');
            renderSharedVideos(videos);
        } catch (error) {
            console.error('Failed to fetch shared videos:', error);
            // Optionally display an error message to the user in the table area
            sharedVideosTableBody.innerHTML = '<tr><td colspan="7">Failed to load shared videos. Please try again.</td></tr>';
        }
    }

    function renderSharedVideos(videos) {
        sharedVideosTableBody.innerHTML = ''; // Clear existing rows
        if (!videos || videos.length === 0) {
            sharedVideosTableBody.innerHTML = '<tr><td colspan="7">No videos shared yet.</td></tr>';
            return;
        }

        videos.forEach(video => {
            const row = document.createElement('tr');
            const expiresDate = new Date(video.expires_at).toLocaleString();
            const shareUrl = video.share_url; // Use the URL from the backend

            row.innerHTML = `
                <td>${video.share_id}</td>
                <td>${escapeHTML(video.video_name)}</td>
                <td>${video.stash_video_id}</td>
                <td>${expiresDate}</td>
                <td>${video.hits}</td>
                <td>
                    <a href="${shareUrl}" target="_blank">${shareUrl}</a>
                    <button class="copy-button" data-url="${shareUrl}">Copy</button>
                </td>
                <td>
                    <button class="edit-button" data-share-id="${video.share_id}" data-video-name="${escapeHTML(video.video_name)}" data-days-valid="${calculateDaysRemaining(video.expires_at)}">Edit</button>
                    <button class="delete-button" data-share-id="${video.share_id}">Delete</button>
                </td>
            `;
            sharedVideosTableBody.appendChild(row);
        });

        // Add event listeners for new buttons
        addTableButtonListeners();
    }

    function addTableButtonListeners() {
        document.querySelectorAll('.copy-button').forEach(button => {
            button.addEventListener('click', (e) => {
                const url = e.target.getAttribute('data-url');
                navigator.clipboard.writeText(url).then(() => {
                    alert('Link copied to clipboard!');
                }).catch(err => {
                    console.error('Failed to copy link: ', err);
                    alert('Failed to copy link.');
                });
            });
        });

        document.querySelectorAll('.edit-button').forEach(button => {
            button.addEventListener('click', (e) => {
                const shareId = e.target.getAttribute('data-share-id');
                const videoName = e.target.getAttribute('data-video-name');
                const daysValid = e.target.getAttribute('data-days-valid'); 
                
                editShareIdInput.value = shareId;
                editVideoNameInput.value = videoName;
                // Calculate remaining days or use a default if expired/invalid
                editDaysValidInput.value = Math.max(1, parseInt(daysValid) || 7); // Ensure at least 1 day
                
                editModal.style.display = 'block';
                clearMessages();
            });
        });

        document.querySelectorAll('.delete-button').forEach(button => {
            button.addEventListener('click', async (e) => {
                const shareId = e.target.getAttribute('data-share-id');
                if (confirm(`Are you sure you want to delete share ${shareId}?`)) {
                    try {
                        await apiRequest(`/delete_share/${shareId}`, 'DELETE');
                        fetchSharedVideos(); // Refresh list after delete
                    } catch (error) {
                        alert(`Failed to delete share: ${error.message}`);
                    }
                }
            });
        });
    }

    // --- Edit Modal Logic ---
    cancelEditButton.addEventListener('click', () => {
        editModal.style.display = 'none';
    });

    saveEditButton.addEventListener('click', async () => {
        clearMessages();
        const shareId = editShareIdInput.value;
        const updatedData = {
            video_name: editVideoNameInput.value,
             // Note: The backend expects stash_video_id, but we don't allow changing it here
             // It might be better to fetch the original stash_id if the backend requires it for PUT
             // Or adjust the backend PUT endpoint not to require stash_video_id
            stash_video_id: 0, // Placeholder - backend should ignore or fetch this
            days_valid: parseInt(editDaysValidInput.value, 10)
        };

        if (!updatedData.video_name || isNaN(updatedData.days_valid)) {
            editError.textContent = 'Please fill in all fields correctly.';
            return;
        }

        try {
            // *** Backend PUT /edit_share/{share_id} needs to accept ShareVideoRequest ***
            // It currently expects video_name and days_valid (and stash_video_id which we aren't changing)
            await apiRequest(`/edit_share/${shareId}`, 'PUT', updatedData); 
            editModal.style.display = 'none';
            fetchSharedVideos(); // Refresh the list
        } catch (error) { 
            editError.textContent = `Failed to update share: ${error.message}`;
        }
    });

    // --- Utility Functions ---
    function escapeHTML(str) {
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    function calculateDaysRemaining(expiresAt) {
        const now = new Date();
        const expiry = new Date(expiresAt);
        const diffTime = expiry - now;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        return Math.max(0, diffDays); // Return 0 if expired
    }

}); 