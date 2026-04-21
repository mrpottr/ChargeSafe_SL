# ChargeSafe SL Backend

A FastAPI-based backend for the ChargeSafe SL EV Charging Station Monitoring System. This backend provides APIs for user authentication, station management, incident reporting, and real-time monitoring.

## Features

### Core Features
- **User Management**: Registration, login, and profile management
- **Charging Station Monitoring**: Real-time station status, safety scores, and cyber risk assessment
- **Incident Reporting**: Users can report issues (overheating, billing errors, network issues, etc.)
- **Notifications**: Real-time alerts for critical station issues
- **Chat History**: Persistent storage of user-assistant conversations
- **Settings Management**: User preferences and alert thresholds

### Admin Features
- Station management (create, update, view)
- Report review and status updates
- User management and deactivation
- Comprehensive monitoring of all stations

### Data Models
- **Users**: With roles (admin/standard_user)
- **Charging Stations**: With safety scores, cyber risk levels, and performance metrics
- **Reports**: Incident reports from users with severity levels
- **Notifications**: Real-time alerts with read/unread status
- **Messages**: Chat history for persistence
- **Settings**: User preferences and alert configurations
- **Score/Temperature History**: Historical data for analysis

## Architecture

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app initialization
│   ├── models.py               # SQLAlchemy ORM models
│   ├── schemas.py              # Pydantic request/response schemas
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py           # All API endpoints
│   ├── core/
│   │   ├── config.py           # Configuration settings
│   │   └── security.py         # JWT authentication utilities
│   └── db/
│       └── session.py          # Database session management
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker configuration
├── .env.example               # Environment variables template
└── API_DOCUMENTATION.md       # Detailed API docs
```

## Setup Instructions

### Prerequisites
- Python 3.9+
- PostgreSQL 12+
- pip or conda

### 1. Environment Setup

Clone or navigate to the backend directory and create a `.env` file:

```bash
cp .env.example .env
```

Update `.env` with your database credentials:

```env
DATABASE_URL=postgresql+psycopg://postgres:your_password@localhost:5432/chargesafe_sl
SECRET_KEY=your-very-secret-key-change-this-in-production
BACKEND_CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### 2. Create PostgreSQL Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE chargesafe_sl;

# Exit psql
\q
```

### 3. Install Dependencies

```bash
# Create virtual environment (optional but recommended)
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
