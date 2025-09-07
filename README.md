# Bet Ledger

A personal betting tracker built with Flask, SQLAlchemy, and Tailwind CSS.

## Features

- Track bets with multiple participants and custom stake splits
- Live payout preview with American odds calculation
- Mobile-responsive design with hamburger navigation
- Partial bet settlement (settle early when one leg loses)
- Transaction management and live money tracking
- CSV export for bet history

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Open http://localhost:5000

## Deployment on Render

1. Push your code to GitHub
2. Connect your GitHub repo to Render
3. Create a new Web Service
4. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Python Version**: 3.11.0
5. Add environment variables:
   - `SECRET_KEY`: Generate a secure random key
   - `DATABASE_URL`: Render will provide this automatically
6. Deploy!

## Environment Variables

- `SECRET_KEY`: Flask secret key for sessions
- `DATABASE_URL`: Database connection string (auto-provided by Render)
- `PORT`: Port number (auto-provided by Render)
- `FLASK_ENV`: Set to 'development' for debug mode

## Database

The app uses SQLite locally and PostgreSQL on Render. The database is automatically initialized and seeded on first run.