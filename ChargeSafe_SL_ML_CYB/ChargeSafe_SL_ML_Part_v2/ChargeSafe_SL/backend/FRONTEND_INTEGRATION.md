# Frontend-Backend Integration Guide

This document explains how to integrate the ChargeSafe SL frontend with the FastAPI backend.

## Overview

The backend provides RESTful APIs that the frontend can consume. All communication happens over HTTP/HTTPS with JSON payloads. Authentication uses JWT tokens.

## Base Configuration

Update your frontend API configuration:

```javascript
// In your React configuration (e.g., env or constants)
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

// Create axios instance or fetch wrapper
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json'
  }
});

// Add request interceptor to include token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 errors (unauthorized)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

## Authentication Flow

### 1. User Registration

```javascript
// Frontend: Register endpoint
async function registerUser(username, email, password) {
  try {
    const response = await api.post('/auth/register', {
      username,
      email,
      password
    });
    return response.data;
  } catch (error) {
    console.error('Registration failed:', error.response?.data?.detail);
    throw error;
  }
}

// Update UI after registration (typically auto-login or redirect to login)
```

### 2. User Login

```javascript
// Frontend: Login endpoint
async function loginUser(email, password) {
  try {
    const response = await api.post('/auth/login', {
      email,
      password
    });
    
    // Store token
    localStorage.setItem('auth_token', response.data.access_token);
    
    // Store user info if needed
    localStorage.setItem('user', JSON.stringify(response.data.user));
    
    return response.data.user;
  } catch (error) {
    console.error('Login failed:', error.response?.data?.detail);
    throw error;
  }
}
```

### 3. Get Current User

```javascript
// Frontend: Get logged-in user info
async function getCurrentUser() {
  try {
