from models import db, Person, Transaction, TransactionType
from datetime import datetime

def init_db(app):
    """Initialize the database"""
    with app.app_context():
        db.create_all()

def seed_db(app):
    """Seed the database with initial data"""
    with app.app_context():
        # Check if persons already exist
        if Person.query.count() > 0:
            print("Database already seeded")
            return
        
        # Create persons
        ryan = Person(name="Ryan")
        friend = Person(name="Friend")
        
        db.session.add(ryan)
        db.session.add(friend)
        db.session.commit()
        
        print("Database seeded with Ryan and Friend")

if __name__ == '__main__':
    from app import app
    init_db(app)
    seed_db(app)
