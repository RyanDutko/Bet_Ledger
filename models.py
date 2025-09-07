from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from enum import Enum

# This will be initialized in app.py
db = SQLAlchemy()

class TransactionType(Enum):
    DEPOSIT = 'deposit'
    WITHDRAW = 'withdraw'
    ADJUSTMENT = 'adjustment'

class BetStatus(Enum):
    OPEN = 'open'
    WON = 'won'
    LOST = 'lost'
    VOID = 'void'
    CASHED_OUT = 'cashed_out'

class LegResult(Enum):
    PENDING = 'pending'
    WON = 'won'
    LOST = 'lost'
    VOID = 'void'

class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    def __repr__(self):
        return f'<Person {self.name}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)
    type = db.Column(db.Enum(TransactionType), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(500))
    ts = db.Column(db.DateTime, default=datetime.utcnow)
    
    person = db.relationship('Person', backref=db.backref('transactions', lazy=True))
    
    def __repr__(self):
        return f'<Transaction {self.type.value} ${self.amount_cents/100:.2f}>'

class Bet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stake_cents = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum(BetStatus), nullable=False, default=BetStatus.OPEN)
    placed_at = db.Column(db.DateTime, default=datetime.utcnow)
    settled_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<Bet ${self.stake_cents/100:.2f} {self.status.value}>'

class BetLeg(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bet_id = db.Column(db.Integer, db.ForeignKey('bet.id'), nullable=False)
    matchup = db.Column(db.String(200), nullable=False)
    bet_description = db.Column(db.String(200), nullable=False)
    american_odds = db.Column(db.Integer, nullable=False)
    result = db.Column(db.Enum(LegResult), nullable=False, default=LegResult.PENDING)
    
    bet = db.relationship('Bet', backref=db.backref('legs', lazy=True))
    
    def __repr__(self):
        return f'<BetLeg {self.matchup} - {self.bet_description} {self.american_odds:+d}>'

class Settlement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bet_id = db.Column(db.Integer, db.ForeignKey('bet.id'), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)
    net_cents = db.Column(db.Integer, nullable=False)
    ts = db.Column(db.DateTime, default=datetime.utcnow)
    
    bet = db.relationship('Bet', backref=db.backref('settlements', lazy=True))
    person = db.relationship('Person', backref=db.backref('settlements', lazy=True))
    
    def __repr__(self):
        return f'<Settlement ${self.net_cents/100:.2f}>'

class BetParticipant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bet_id = db.Column(db.Integer, db.ForeignKey('bet.id'), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)
    stake_cents = db.Column(db.Integer, nullable=False)
    
    bet = db.relationship('Bet', backref=db.backref('participants', lazy=True))
    person = db.relationship('Person', backref=db.backref('bet_participants', lazy=True))
    
    def __repr__(self):
        return f'<BetParticipant {self.person.name} ${self.stake_cents/100:.2f}>'
