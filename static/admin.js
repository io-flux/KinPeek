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
    const resolutionInput = document.getElementById('resolution');
    const sharePasswordInput = document.getElementById('share-password');
    const lookupTitleButton = document.getElementById('lookup-title-button');
    const shareMessage = document.getElementById('share-message');
    const shareError = document.getElementById('share-error');

    const sharedVideosTableBody = document.querySelector('#shared-videos-table tbody');
    const refreshSharesButton = document.getElementById('refresh-shares');

    const editModal = document.getElementById('edit-modal');
    const editShareIdInput = document.getElementById('edit-share-id');
    const editVideoNameInput = document.getElementById('edit-video-name');
    const editDaysValidInput = document.getElementById('edit-days-valid');
    const editResolutionInput = document.getElementById('edit-resolution');
    const editSharePasswordInput = document.getElementById('edit-share-password');
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
            if (response.status === 204 || response.headers.get('content-length') === '0') {
                return null;
            }
            return await response.json();
        } catch (error) {
            console.error('API Request Error:', error);
            throw error;
        }
    }

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
        return Math.max(0, diffDays);
    }

    function copyToClipboard(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(() => {
                alert('Link copied to clipboard!');
            }).catch(err => {
                console.error('Failed to copy link:', err);
                fallbackCopy(text);
            });
        } else {
            fallbackCopy(text);
        }
    }

    function fallbackCopy(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        try {
            document.execCommand('copy');
            alert('Link copied to clipboard!');
        } catch (err) {
            console.error('Fallback copy failed:', err);
            alert('Failed to copy link. Please copy manually: ' + text);
        }
        document.body.removeChild(textarea);
    }

    // --- Initialization ---
    if (authToken) {
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
            showLogin();
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
            const data = await apiRequest(`/get_video_title/${stashId}`);
            if (data && data.title) {
                videoNameInput.value = data.title;
            } else {
                shareError.textContent = 'Could not find title for this ID.';
                videoNameInput.value = '';
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
            resolution: resolutionInput.value,
            password: sharePasswordInput.value || null
        };

        if (!shareData.video_name || isNaN(shareData.stash_video_id) || isNaN(shareData.days_valid) || !shareData.resolution) {
            shareError.textContent = 'Please fill in all required fields correctly.';
            return;
        }

        try {
            const result = await apiRequest('/share', 'POST', shareData);
            shareMessage.textContent = `Video shared successfully! URL: ${result.share_url}`;
            shareForm.reset();
            fetchSharedVideos();
        } catch (error) {
            shareError.textContent = `Failed to share video: ${error.message}`;
        }
    });

    refreshSharesButton.addEventListener('click', fetchSharedVideos);

    async function fetchSharedVideos() {
        try {
            const videos = await apiRequest('/shared_videos');
            renderSharedVideos(videos);
        } catch (error) {
            console.error('Failed to fetch shared videos:', error);
            sharedVideosTableBody.innerHTML = '<tr><td colspan="4">Failed to load shared videos. Please try again.</td></tr>';
        }
    }

    function renderSharedVideos(videos) {
        sharedVideosTableBody.innerHTML = '';
        if (!videos || videos.length === 0) {
            sharedVideosTableBody.innerHTML = '<tr><td colspan="4">No videos shared yet.</td></tr>';
            return;
        }

        videos.forEach(video => {
            const row = document.createElement('tr');
            const expiresDate = new Date(video.expires_at).toLocaleString();
            const shareUrl = video.share_url;

            row.innerHTML = `
                <td>${escapeHTML(video.video_name)}</td>
                <td>${video.hits}</td>
                <td>${expiresDate}</td>
                <td>
                    <a href="${shareUrl}" target="_blank">${shareUrl}</a>
                    <button class="copy-button" data-url="${shareUrl}">Copy</button>
                    <button class="edit-button" data-share-id="${video.share_id}" data-video-name="${escapeHTML(video.video_name.split(' (')[0])}" data-days-valid="${calculateDaysRemaining(video.expires_at)}" data-resolution="${video.resolution}" data-has-password="${video.has_password}">Edit</button>
                    <button class="delete-button" data-share-id="${video.share_id}">Delete</button>
                </td>
            `;
            sharedVideosTableBody.appendChild(row);
        });

        addTableButtonListeners();
    }

    function addTableButtonListeners() {
        document.querySelectorAll('.copy-button').forEach(button => {
            button.addEventListener('click', (e) => {
                const url = e.target.getAttribute('data-url');
                copyToClipboard(url);
            });
        });

        document.querySelectorAll('.edit-button').forEach(button => {
            button.addEventListener('click', (e) => {
                const shareId = e.target.getAttribute('data-share-id');
                const videoName = e.target.getAttribute('data-video-name');
                const daysValid = e.target.getAttribute('data-days-valid');
                const resolution = e.target.getAttribute('data-resolution');
                
                editShareIdInput.value = shareId;
                editVideoNameInput.value = videoName;
                editDaysValidInput.value = Math.max(1, parseInt(daysValid) || 7);
                editResolutionInput.value = resolution;
                editSharePasswordInput.value = '';
                
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
                        fetchSharedVideos();
                    } catch (error) {
                        alert(`Failed to delete share: ${error.message}`);
                    }
                }
            });
        });
    }

    cancelEditButton.addEventListener('click', () => {
        editModal.style.display = 'none';
    });

    saveEditButton.addEventListener('click', async () => {
        clearMessages();
        const shareId = editShareIdInput.value;
        const updatedData = {
            video_name: editVideoNameInput.value,
            stash_video_id: 0,
            days_valid: parseInt(editDaysValidInput.value, 10),
            resolution: editResolutionInput.value,
            password: editSharePasswordInput.value || null
        };

        if (!updatedData.video_name || isNaN(updatedData.days_valid) || !updatedData.resolution) {
            editError.textContent = 'Please fill in all required fields correctly.';
            return;
        }

        try {
            await apiRequest(`/edit_share/${shareId}`, 'PUT', updatedData);
            editModal.style.display = 'none';
            fetchSharedVideos();
        } catch (error) {
            editError.textContent = `Failed to update share: ${error.message}`;
        }
    });
});
