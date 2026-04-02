# ChargeSafe SL API Documentation

## Overview
ChargeSafe SL API is a FastAPI-based backend service for monitoring and managing EV charging stations across Sri Lanka. It provides endpoints for user authentication, station management, incident reporting, notifications, and admin operations.

## Base URL
```
http://localhost:8000/api
```

## Authentication
Most endpoints require JWT Bearer token authentication. After login, include the token in the Authorization header:
```
Authorization: Bearer <your_access_token>
```

---

## Endpoints

### Authentication

#### Register
```
POST /auth/register
Content-Type: application/json

{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "securepassword123"
}

Response (201):
{
  "id": "uuid",
  "username": "john_doe",
  "email": "john@example.com",
  "role": "standard_user",
  "is_active": true,
  "created_at": "2025-06-01T10:30:00Z",
  "last_login": null
}
```

#### Login
```
POST /auth/login
Content-Type: application/json

{
  "email": "john@example.com",
  "password": "securepassword123"
}

Response (200):
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "john_doe",
    "email": "john@example.com",
    "role": "standard_user",
    "is_active": true,
    "created_at": "2025-06-01T10:30:00Z",
    "last_login": "2025-06-01T11:00:00Z"
  }
}
```

---

### Stations

#### List All Stations
```
GET /stations?city=Colombo&min_score=75&status_filter=operational&limit=50
Authorization: Bearer <token>

Query Parameters:
- city (optional): Filter by city name
- status_filter (optional): operational, faulty, offline, unknown, maintenance
- min_score (optional): Minimum safety score (0-100)
- max_score (optional): Maximum safety score (0-100)
- limit (optional): Max results (default: 50, max: 100)

Response (200):
[
  {
    "id": "uuid",
    "name": "Colombo Fast Charge",
    "latitude": 6.9147,
    "longitude": 79.8512,
    "city": "Colombo",
    "address": "Colpetty",
    "status": "operational",
    "safety_score": 82.0,
    "cyber_risk_level": "LOW",
    "firmware_version": "v2.1.0",
    "firmware_age_days": 15,
    "temperature_celsius": 32.5,
    "power_status": "Stable",
    "fault_count": 0,
    "last_scored_at": "2025-06-01T10:30:00Z",
    "created_at": "2025-05-20T08:00:00Z",
    "updated_at": "2025-06-01T10:30:00Z"
  }
]
```

---

## Response Codes

- `200 OK`: Successful request
- `201 Created`: Resource created successfully
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Missing or invalid JWT token
- `403 Forbidden`: User lacks permissions
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

For complete API documentation, refer to the interactive Swagger UI at `/docs` when the server is running.
