import os
import django

# Set the settings module BEFORE any django imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'online_notes_django.settings')
django.setup()

# Now we can safely import Django models and utilities
from django.contrib.auth.models import User
from django.utils import timezone
from pymongo import MongoClient
from datetime import datetime

def init_db():
    print("Checking database initialization...")
    
    # 1. Django Auth User (SQLite)
    if not User.objects.filter(username='admin').exists():
        user = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        user.first_name = 'Administrator'
        user.save()
        
        # 2. NoSQL Profile (MongoDB)
        client = MongoClient('mongodb://localhost:27017/')
        db = client['notes_db_django']
        profiles_col = db['profiles']
        
        # Ensure we don't duplicate profile if user exists (shouldn't happen here but safer)
        if not profiles_col.find_one({"username": "admin"}):
            profiles_col.insert_one({
                "user_id": user.id,
                "username": 'admin',
                "role": 'admin',
                "course": 'Computer Science',
                "gender": 'N/A',
                "joindate": timezone.now().strftime("%B %d, %Y"),
                "image": "profile.jpg",
                "about": "System Administrator"
            })
        print("Admin user created in SQLite & MongoDB: admin / admin123")
    else:
        print("Admin user already exists.")

    # 3. NoSQL Samples (MongoDB)
    client = MongoClient('mongodb://localhost:27017/')
    db = client['notes_db_django']
    uploads_col = db['uploads']
    
    samples = [
        {"file_name": "demo preview", "file_description": "demo", "file_type": "pdf", "file_uploader": "user", "file_uploaded_on": datetime(2017, 7, 19, 5, 8, 23), "file_uploaded_to": "Computer Science", "file": "578090.pdf", "status": "approved"},
        {"file_name": "teacher3 demo", "file_description": "demo", "file_type": "txt", "file_uploader": "teacher2", "file_uploaded_on": datetime(2017, 7, 19, 5, 8, 16), "file_uploaded_to": "Mechanical", "file": "565834.txt", "status": "approved"},
    ]
    
    added_count = 0
    for sample in samples:
        if not uploads_col.find_one({"file": sample["file"]}):
            uploads_col.insert_one(sample)
            added_count += 1
    
    if added_count > 0:
        print(f"Added {added_count} sample notes to MongoDB.")
    else:
        print("Sample notes already exist in MongoDB.")

if __name__ == "__main__":
    init_db()
