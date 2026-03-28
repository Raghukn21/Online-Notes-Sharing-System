import django
import os
from datetime import datetime
from pymongo import MongoClient
from django.contrib.auth.hashers import make_password

# Setup Django for settings access
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'online_notes_django.settings')
django.setup()

client = MongoClient('mongodb://localhost:27017/')
db = client['notes_db_django']
users_col = db['users']
profiles_col = db['profiles']

def init_mongo_admin():
    # Clear existing if needed or just update
    admin_exists = users_col.find_one({"username": "admin"})
    
    if not admin_exists:
        # Create Admin User
        admin_data = {
            "username": "admin",
            "first_name": "System",
            "last_name": "Admin",
            "email": "admin@onss.com",
            "password": make_password("admin123"),
            "role": "admin",
            "is_admin": True
        }
        user_result = users_col.insert_one(admin_data)
        
        # Create Profile
        profiles_col.insert_one({
            "user_id": str(user_result.inserted_id),
            "username": "admin",
            "role": "admin",
            "course": "Administration",
            "joindate": datetime.now().strftime("%B %d, %Y"),
            "image": "profile.jpg",
            "about": "Administrator of the ONSS platform."
        })
        print("MongoDB Admin initialized: admin / admin123")
    else:
        print("Admin already exists in MongoDB.")

if __name__ == "__main__":
    init_mongo_admin()
