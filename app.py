from flask import Flask, render_template, request, redirect, url_for, flash, Response
from datetime import datetime
import csv
from io import StringIO
import os

# Import models and db
from models import db, Person, Transaction, Bet, BetLeg, Settlement, BetParticipant, LegResult, BetStatus, TransactionType
from sqlalchemy import text
from sqlalchemy.orm import joinedload
from services.odds import american_to_decimal, calculate_parlay_payout, decimal_to_american

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
# Handle both SQLite (local) and PostgreSQL (Render)
database_url = os.environ.get('DATABASE_URL')
print(f"DATABASE_URL environment variable: {database_url}")

if database_url:
    # Render provides PostgreSQL
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
    else:
        # Ensure we're using psycopg driver
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    print(f"Using PostgreSQL database: {database_url[:20]}...")
else:
    # Local development with SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bet_ledger.db'
    print("Using SQLite database for local development")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize db with app
db.init_app(app)

@app.route('/')
def dashboard():
    """Dashboard showing ownership, open bets, and exposure"""
    # Calculate total ownership per person
    ownership_data = []
    persons = Person.query.all()
    
    for person in persons:
        # Sum transactions
        transaction_total = db.session.query(db.func.sum(Transaction.amount_cents)).filter(
            Transaction.person_id == person.id
        ).scalar() or 0
        
        # Sum settlements
        settlement_total = db.session.query(db.func.sum(Settlement.net_cents)).filter(
            Settlement.person_id == person.id
        ).scalar() or 0
        
        # Sum open bet stakes (exposure)
        open_bet_total = db.session.query(db.func.sum(BetParticipant.stake_cents)).join(Bet).filter(
            BetParticipant.person_id == person.id,
            Bet.status == BetStatus.OPEN
        ).scalar() or 0
        
        # Live money = transactions + settlements - open bet exposure
        live_money = transaction_total + settlement_total - open_bet_total
        
        ownership_data.append({
            'person': person,
            'ownership_cents': transaction_total + settlement_total,
            'ownership_dollars': (transaction_total + settlement_total) / 100,
            'live_money_cents': live_money,
            'live_money_dollars': live_money / 100,
            'exposure_cents': open_bet_total,
            'exposure_dollars': open_bet_total / 100
        })
    
    # Get open bets with potential payouts (newest first)
    open_bets = Bet.query.filter(Bet.status == BetStatus.OPEN).order_by(Bet.placed_at.desc()).all()
    open_bets_data = []
    
    for bet in open_bets:
        legs = BetLeg.query.filter(BetLeg.bet_id == bet.id).all()
        participants = BetParticipant.query.filter(BetParticipant.bet_id == bet.id).all()
        
        decimal_odds = 1.0
        for leg in legs:
            leg_decimal = american_to_decimal(leg.american_odds)
            decimal_odds *= leg_decimal
        
        # Calculate total stake and potential payout
        total_stake = sum(p.stake_cents for p in participants)
        potential_payout = calculate_parlay_payout(total_stake, decimal_odds)
        
        open_bets_data.append({
            'bet': bet,
            'legs': legs,
            'participants': participants,
            'total_stake_cents': total_stake,
            'total_stake_dollars': total_stake / 100,
            'potential_payout_cents': potential_payout,
            'potential_payout_dollars': potential_payout / 100
        })
    
    # Calculate total exposure
    total_exposure = db.session.query(db.func.sum(BetParticipant.stake_cents)).join(Bet).filter(
        Bet.status == BetStatus.OPEN
    ).scalar() or 0
    
    return render_template('dashboard.html', 
                          ownership_data=ownership_data,
                          open_bets_data=open_bets_data,
                          total_exposure_cents=total_exposure,
                          total_exposure_dollars=total_exposure / 100)

@app.route('/bet/new', methods=['GET', 'POST'])
def new_bet():
    """Create a new bet"""
    if request.method == 'POST':
        # Get bet legs
        leg_count = int(request.form.get('leg_count', 0))
        legs_data = []
        for i in range(leg_count):
            matchup = request.form.get(f'leg_{i}_matchup')
            bet_description = request.form.get(f'leg_{i}_bet')
            american_odds = request.form.get(f'leg_{i}_odds')
            if matchup and bet_description and american_odds:
                legs_data.append({
                    'matchup': matchup,
                    'bet_description': bet_description,
                    'american_odds': int(american_odds)
                })
        
        if not legs_data:
            flash('At least one bet leg is required', 'error')
            return redirect(url_for('new_bet'))
        
        # Get participants
        participants_data = []
        persons = Person.query.all()
        total_stake = 0
        
        for person in persons:
            stake_str = request.form.get(f'person_{person.id}_stake', '0')
            if stake_str and float(stake_str) > 0:
                stake_cents = int(float(stake_str) * 100)
                participants_data.append({
                    'person_id': person.id,
                    'stake_cents': stake_cents
                })
                total_stake += stake_cents
        
        if not participants_data:
            flash('At least one participant is required', 'error')
            return redirect(url_for('new_bet'))
        
        if total_stake == 0:
            flash('Total stake must be greater than 0', 'error')
            return redirect(url_for('new_bet'))
        
        # Create bet
        bet = Bet(
            stake_cents=total_stake,  # Keep total stake for backward compatibility
            status=BetStatus.OPEN,
            placed_at=datetime.now()
        )
        db.session.add(bet)
        db.session.flush()  # Get the bet ID
        
        # Create bet participants
        for participant_data in participants_data:
            participant = BetParticipant(
                bet_id=bet.id,
                person_id=participant_data['person_id'],
                stake_cents=participant_data['stake_cents']
            )
            db.session.add(participant)
        
        # Create bet legs
        for leg_data in legs_data:
            leg = BetLeg(
                bet_id=bet.id,
                matchup=leg_data['matchup'],
                bet_description=leg_data['bet_description'],
                american_odds=leg_data['american_odds'],
                result=LegResult.PENDING
            )
            db.session.add(leg)
        
        db.session.commit()
        flash('Bet created successfully!', 'success')
        return redirect(url_for('bet_detail', bet_id=bet.id))
    
    persons = Person.query.all()
    return render_template('new_bet.html', persons=persons)

@app.route('/bet/preview', methods=['POST'])
def bet_preview():
    """Preview potential payout for bet legs"""
    # Calculate total stake from participants
    total_stake_cents = 0
    persons = Person.query.all()
    
    for person in persons:
        stake_str = request.form.get(f'person_{person.id}_stake', '0')
        if stake_str and float(stake_str) > 0:
            total_stake_cents += int(float(stake_str) * 100)
    
    if total_stake_cents == 0:
        return render_template('bet_preview.html', 
                             potential_payout_cents=0,
                             potential_payout_dollars=0)
    
    decimal_odds = 1.0
    leg_count = int(request.form.get('leg_count', 0))
    
    for i in range(leg_count):
        american_odds = request.form.get(f'leg_{i}_odds')
        if american_odds:
            decimal_odds *= american_to_decimal(int(american_odds))
    
    potential_payout = calculate_parlay_payout(total_stake_cents, decimal_odds)
    
    # Calculate total American odds for display
    total_american_odds = decimal_to_american(decimal_odds) if decimal_odds > 1.0 else None
    
    return render_template('bet_preview.html', 
                         potential_payout_cents=potential_payout,
                         potential_payout_dollars=potential_payout / 100,
                         total_american_odds=total_american_odds)

@app.route('/bet/<int:bet_id>')
def bet_detail(bet_id):
    """Show bet details and settlement form"""
    bet = Bet.query.get_or_404(bet_id)
    legs = BetLeg.query.filter(BetLeg.bet_id == bet_id).all()
    participants = BetParticipant.query.filter(BetParticipant.bet_id == bet_id).all()
    
    return render_template('bet_detail.html', bet=bet, legs=legs, participants=participants)

@app.route('/bet/<int:bet_id>/settle', methods=['POST'])
def settle_bet(bet_id):
    """Settle a bet based on leg results"""
    bet = Bet.query.get_or_404(bet_id)
    legs = BetLeg.query.filter(BetLeg.bet_id == bet_id).all()
    participants = BetParticipant.query.filter(BetParticipant.bet_id == bet_id).all()
    
    # Update leg results
    for leg in legs:
        result = request.form.get(f'leg_{leg.id}_result')
        if result and result != 'pending':
            if result == 'won':
                leg.result = LegResult.WON
            elif result == 'lost':
                leg.result = LegResult.LOST
            elif result == 'void':
                leg.result = LegResult.VOID
            db.session.add(leg)
        # If result is 'pending' or empty, leave leg.result as PENDING (no change needed)
    
    db.session.flush()
    
    # Apply business rules
    status = BetStatus.OPEN
    
    # Check if any leg lost
    has_lost = any(leg.result == LegResult.LOST for leg in legs)
    if has_lost:
        status = BetStatus.LOST
        # Each participant loses their stake
        for participant in participants:
            settlement = Settlement(
                bet_id=bet_id,
                person_id=participant.person_id,
                net_cents=-participant.stake_cents,
                ts=datetime.now()
            )
            db.session.add(settlement)
    else:
        # Check if all legs have definitive results (no pending legs)
        has_pending = any(leg.result == LegResult.PENDING for leg in legs)
        if has_pending:
            # Keep bet open - some legs still pending
            status = BetStatus.OPEN
        else:
            # All legs have definitive results, check if all winning
            all_winning = all(leg.result in [LegResult.WON, LegResult.VOID] for leg in legs)
            if all_winning:
                # Calculate payout
                decimal_odds = 1.0
                for leg in legs:
                    if leg.result == LegResult.WON:
                        decimal_odds *= american_to_decimal(leg.american_odds)
                    # void legs contribute 1.0 (no change to decimal_odds)
                
                # Calculate total payout and distribute proportionally
                total_stake = sum(p.stake_cents for p in participants)
                total_payout = calculate_parlay_payout(total_stake, decimal_odds)
                
                for participant in participants:
                    # Calculate this participant's share of the payout
                    participant_share = (participant.stake_cents / total_stake) * total_payout
                    net_cents = participant_share - participant.stake_cents
                    
                    settlement = Settlement(
                        bet_id=bet_id,
                        person_id=participant.person_id,
                        net_cents=net_cents,
                        ts=datetime.now()
                    )
                    db.session.add(settlement)
                
                status = BetStatus.WON
            else:
                # Check if all legs are void
                all_void = all(leg.result == LegResult.VOID for leg in legs)
                if all_void:
                    status = BetStatus.VOID
                    # No settlements needed for void bets
    
    # Update bet status
    bet.status = status
    if status != BetStatus.OPEN:
        bet.settled_at = datetime.now()
    db.session.add(bet)
    
    db.session.commit()
    
    if status == BetStatus.OPEN:
        flash('Bet updated! Some legs are still pending.', 'info')
    else:
        flash(f'Bet settled! Status: {status.value}', 'success')
    return redirect(url_for('bet_detail', bet_id=bet_id))

@app.route('/transactions/new', methods=['GET', 'POST'])
def new_transaction():
    """Add deposit/withdraw/adjustment for a person"""
    if request.method == 'POST':
        person_id = request.form.get('person_id')
        transaction_type = request.form.get('type')
        amount_dollars = float(request.form.get('amount', 0))
        amount_cents = int(amount_dollars * 100)
        note = request.form.get('note', '')
        
        transaction = Transaction(
            person_id=person_id,
            type=TransactionType(transaction_type),
            amount_cents=amount_cents,
            note=note,
            ts=datetime.now()
        )
        db.session.add(transaction)
        db.session.commit()
        
        flash('Transaction added successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    persons = Person.query.all()
    return render_template('new_transaction.html', persons=persons)

@app.route('/history')
def history():
    """Show bet history with filters"""
    person_id = request.args.get('person_id', type=int)
    status = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    query = Bet.query
    
    if person_id:
        # Filter by person through BetParticipant
        query = query.join(BetParticipant).filter(BetParticipant.person_id == person_id)
    if status:
        query = query.filter(Bet.status == BetStatus(status))
    if date_from:
        query = query.filter(Bet.placed_at >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(Bet.placed_at <= datetime.fromisoformat(date_to))
    
    bets = query.options(joinedload(Bet.participants)).order_by(Bet.placed_at.desc()).all()
    persons = Person.query.all()
    
    return render_template('history.html', bets=bets, persons=persons)

@app.route('/history.csv')
def history_csv():
    """Export bet history as CSV"""
    bets = Bet.query.order_by(Bet.placed_at.desc()).all()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Participants', 'Stake', 'Status', 'Placed At', 'Settled At'])
    
    for bet in bets:
        participants = BetParticipant.query.filter(BetParticipant.bet_id == bet.id).all()
        participant_names = []
        for participant in participants:
            participant_names.append(f"{participant.person.name} (${participant.stake_cents/100:.2f})")
        
        writer.writerow([
            bet.id,
            '; '.join(participant_names),
            f"${bet.stake_cents/100:.2f}",
            bet.status.value,
            bet.placed_at.strftime('%Y-%m-%d %H:%M') if bet.placed_at else '',
            bet.settled_at.strftime('%Y-%m-%d %H:%M') if bet.settled_at else ''
        ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=bet_history.csv'}
    )

@app.route('/people')
def people():
    """Manage people"""
    persons = Person.query.all()
    return render_template('people.html', persons=persons)

@app.route('/people/edit/<int:person_id>', methods=['GET', 'POST'])
def edit_person(person_id):
    """Edit person name"""
    person = Person.query.get_or_404(person_id)
    
    if request.method == 'POST':
        new_name = request.form.get('name', '').strip()
        if new_name:
            person.name = new_name
            db.session.commit()
            flash(f'Updated {person.name}', 'success')
            return redirect(url_for('people'))
        else:
            flash('Name cannot be empty', 'error')
    
    return render_template('edit_person.html', person=person)

def normalize_enums(flask_app: Flask) -> None:
    """Best-effort normalization of legacy lowercase enum values to enum names.
    Safe to run multiple times; ignores failures on fresh DBs.
    """
    with flask_app.app_context():
        try:
            print("Running enum normalization...")
            
            # Bet.status: open→OPEN, won→WON, lost→LOST, void→VOID, cashed_out→CASHED_OUT
            mappings = [('open','OPEN'), ('won','WON'), ('lost','LOST'), ('void','VOID'), ('cashed_out','CASHED_OUT')]
            for old, new in mappings:
                result = db.session.execute(text("UPDATE bet SET status = :new WHERE status = :old"), {"new": new, "old": old})
                if result.rowcount > 0:
                    print(f"Updated {result.rowcount} bet records: {old} → {new}")

            # BetLeg.result: pending→PENDING, won→WON, lost→LOST, void→VOID
            mappings_leg = [('pending','PENDING'), ('won','WON'), ('lost','LOST'), ('void','VOID')]
            for old, new in mappings_leg:
                result = db.session.execute(text("UPDATE bet_leg SET result = :new WHERE result = :old"), {"new": new, "old": old})
                if result.rowcount > 0:
                    print(f"Updated {result.rowcount} bet_leg records: {old} → {new}")

            # Transaction.type: deposit→DEPOSIT, withdraw→WITHDRAW, adjustment→ADJUSTMENT
            mappings_tx = [('deposit','DEPOSIT'), ('withdraw','WITHDRAW'), ('adjustment','ADJUSTMENT')]
            for old, new in mappings_tx:
                result = db.session.execute(text("UPDATE \"transaction\" SET type = :new WHERE type = :old"), {"new": new, "old": old})
                if result.rowcount > 0:
                    print(f"Updated {result.rowcount} transaction records: {old} → {new}")

            db.session.commit()
            print("Enum normalization completed successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Enum normalization failed: {e}")
            # Ignore silently; DB may already be clean or tables absent


# Initialize database when app starts (for production)
with app.app_context():
    from db import init_db, seed_db
    print("Initializing database...")
    init_db(app)
    print("Seeding database...")
    seed_db(app)
    print("Normalizing enums...")
    normalize_enums(app)
    print("Database initialization complete!")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
