let token = null;

async function login() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    console.debug('Sending login request:', { username, password: '***' });

    try {
        const response = await fetch('/login', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        console.debug('Login response:', data);

        if (response.ok) {
            token = data.access_token;
            document.getElementById('login-form').style.display = 'none';
            document.getElementById('admin-content').style.display = 'block';
            loadVideos();
            document.getElementById('login-error').textContent = '';
        } else {
            let errorMessage = 'Login failed';
            if (data.detail) {
                if (Array.isArray(data.detail)) {
                    errorMessage = data.detail.map(err => err.msg).join(', ');
                } else {
                    errorMessage = data.detail;
                }
            }
            document.getElementById('login-error').textContent = errorMessage;
            console.error('Login error:', data);
        }
    } catch (error) {
        document.getElementById('login-error').textContent = 'Network error during login';
        console.error('Network error:', error);
    }
}

async function loadVideos() {
    try {
        const response = await fetch('/shared_videos', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) {
            console.error('Failed to load videos:', response.status, response.statusText);
            return;
        }
        const videos = await response.json();
        const tbody = document.getElementById('videos-table');
        tbody.innerHTML = '';
        let totalHits = 0;
        videos.forEach(v => {
            totalHits += v.hits;
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${v.share_id}</td>
                <td>${v.video_name}</td>
                <td>${v.stash_video_id}</td>
                <td>${new Date(v.expires_at).toLocaleString()}</td>
                <td>${v.hits}</td>
                <td>
                    <button class="btn btn-sm btn-warning" onclick="editVideo('${v.share_id}')">Edit</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteVideo('${v.share_id}')">Delete</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
        document.getElementById('total-shares').textContent = videos.length;
        document.getElementById('total-hits').textContent = totalHits;
    } catch (error) {
        console.error('Error loading videos:', error);
    }
}

document.getElementById('share-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const video_name = document.getElementById('video-name').value;
    const stash_video_id = document.getElementById('stash-video-id').value;
    const days_valid = document.getElementById('days-valid').value;
    try {
        const response = await fetch('/share', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ video_name, stash_video_id, days_valid })
        });
        if (response.ok) {
            loadVideos();
            document.getElementById('share-form').reset();
        } else {
            console.error('Failed to share video:', response.status, response.statusText);
        }
    } catch (error) {
        console.error('Error sharing video:', error);
    }
});

async function editVideo(share_id) {
    const video_name = prompt('New video name:');
    const days_valid = prompt('New days valid:');
    if (video_name && days_valid) {
        try {
            await fetch(`/edit_share/${share_id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ video_name, days_valid })
            });
            loadVideos();
        } catch (error) {
            console.error('Error editing video:', error);
        }
    }
}

async function deleteVideo(share_id) {
    if (confirm('Delete this share link?')) {
        try {
            await fetch(`/delete_share/${share_id}`, {  // Fixed typo: /edit_share →
