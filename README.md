Kinpeek
Kinpeek is a FastAPI-based application for securely sharing videos from a Stash adult media management platform. It provides a public-facing video playback interface with a modern, Gruvbox dark-themed UI and an admin panel for managing shared links, protected by JWT authentication.
Features
	•	Public Playback Interface: Sleek video player with Video.js, supporting seeking, playback speed (0.5x, 1x, 1.5x, 2x), and fullscreen, styled in Gruvbox dark theme with a logo placeholder and disclaimer.
	•	Admin Panel: Web interface to share, view, edit, and delete video links, with analytics (hit counts, total shares). Requires username/password login.
	•	Secure Sharing: Generates unique, expiring share links without exposing Stash API keys.
	•	Configuration: Reads Stash server details, admin credentials, and server host/port from config.yaml.
	•	Database: SQLite stores share metadata (video name, Stash ID, expiration, hits).
Prerequisites
	•	Python 3.8+
	•	Mamba (or Conda) for environment management
	•	A running Stash instance with API access enabled
	•	A logo image (e.g., logo-placeholder.png)
Installation
	1	Create and activate a Mamba environment:mamba create -n kinpeek python=3.8 fastapi uvicorn requests pyyaml sqlalchemy pydantic python-jose cryptography passlib
	2	mamba activate kinpeek
	3	
	4	Set up the project structure:mkdir kinpeek
	5	cd kinpeek
	6	mkdir static
	7	Place kinpeek.py, config.yaml, and static files (admin.html, admin.js, styles.css, logo-placeholder.png) in the appropriate directories.
	8	Configure config.yaml: Create config.yaml in the project root:kinpeek:
	9	  host: "0.0.0.0"
	10	  port: 8000
	11	  admin_username: "admin"
	12	  admin_password: "your_secure_password"  # Replace with a strong password
	13	stash:
	14	  server_ip: "192.168.1.100"  # Replace with your Stash server IP
	15	  port: 9999                  # Replace with your Stash server port
	16	  api_key: "your_api_key_here" # Replace with your Stash API key
	17	disclaimer: "This content is shared for private use only. Unauthorized distribution is prohibited."
	18	
	19	Create static files:
	◦	static/admin.html: Admin panel HTML (see implementation details).
	◦	static/admin.js: Admin panel JavaScript for dynamic functionality.
	◦	static/styles.css: Gruvbox dark theme CSS for both interfaces.
	◦	static/logo-placeholder.png: Placeholder logo (replace with your own).
Usage
	1	Run the application:python kinpeek.py
	2	The server starts on the host/port specified in config.yaml (e.g., http://0.0.0.0:8000).
	3	Access the admin panel:
	◦	Open http://:8000/static/admin.html.
	◦	Log in with the admin_username and admin_password from config.yaml.
	◦	Share videos, view/edit/delete links, and check analytics.
	4	Share a video:
	◦	In the admin panel, enter the video name, Stash video ID, and days valid, then click “Share”.
	◦	Copy the share URL (e.g., http://:8000/share/abcd1234).
	5	View a shared video:
	◦	Open the share URL in a browser to access the video player with Gruvbox theme, logo, and disclaimer.
Security Notes
	•	Admin Access: Protected by JWT authentication. Use a strong password in config.yaml.
	•	Share Links: Unique and expiring, with no API key exposure.
	•	Production: Use HTTPS (e.g., via Nginx) to secure traffic.
Customization
	•	Logo: Replace static/logo-placeholder.png with your logo (recommended size: 200x50 pixels).
	•	Disclaimer: Edit the disclaimer field in config.yaml.
	•	Theme: Modify static/styles.css to adjust Gruvbox colors or styles.
Limitations
	•	Video.js supports basic playback; advanced features (e.g., subtitles, multiple resolutions) depend on Stash capabilities.
	•	SQLite is lightweight but may need optimization for large-scale use.
	•	Admin panel is simple; extend admin.js for additional features (e.g., graphs, bulk actions).
Troubleshooting
	•	Server not starting: Verify config.yaml syntax and ensure dependencies are installed.
	•	Videos not streaming: Check Stash server accessibility and valid video IDs.
	•	UI issues: Inspect browser console logs and verify static file paths.
License
MIT License. Use and modify freely, but ensure compliance with Stash’s terms for shared content.
