import os

class Config:
    # Cryptographically secure random key for signing cookies and CSRF tokens.
    # In production, this should be set via an environment variable.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'billflow-dev-secret-key-3b7d8a9e2f1c4a0b'
    
    # Path to the SQLite database file (placed in the project root)
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    # Supabase Session Pooler (if DATABASE_URL env var is set) or fallback to local SQLite:
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f"sqlite:///{os.path.join(BASE_DIR, 'billflow.db')}"
    
    # Disable tracking modifications to save memory and CPU overhead
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File Upload Settings
    # 1. Directory where company logo uploads are stored
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    
    # 2. Maximum file size allowed for uploads (10 Megabytes)
    # Flask automatically intercepts requests exceeding this limit.
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    
    # 3. Allowed file extensions for logo images
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
