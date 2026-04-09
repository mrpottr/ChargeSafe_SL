import React, { useState, useEffect, useRef, useMemo } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8001/api";
const AUTH_TOKEN_KEY = "chargesafe_auth_token";
const LOW_RISK_MAX = 30;
const MEDIUM_RISK_MAX = 70;

// Fix Leaflet marker icon issues in React
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png",
});

const srilankaBounds = [[5.8, 79.5], [9.9, 81.9]];

const MapResizer = () => {
  const map = useMap();
  useEffect(() => {
    map.invalidateSize();
    map.fitBounds(srilankaBounds);
  }, [map]);
  return null;
};

const stations = [
  { 
    id: 1, name: 'Colombo Fast Charge', loc: 'Colpetty', pos: [6.9147, 79.8512], score: 82, faults: 0, fw: 'v2.1.0 (15d)', cyber: 'LOW',
    power: 'Stable',
    tempHistory: [32, 35, 38, 34, 33, 42, 45],
    scoreHistory: [
      { date: '2025-05-25', score: 92, level: 'HIGH', trigger: 'System' },
      { date: '2025-05-26', score: 90, level: 'HIGH', trigger: 'Auto' },
      { date: '2025-05-27', score: 45, level: 'MEDIUM', trigger: 'Manual' },
      { date: '2025-05-28', score: 55, level: 'MEDIUM', trigger: 'System' },
      { date: '2025-05-29', score: 78, level: 'HIGH', trigger: 'Manual' },
      { date: '2025-05-30', score: 82, level: 'HIGH', trigger: 'Auto' }
    ]
  },
  { 
    id: 2, name: 'Galle Rd Charger', loc: 'Galle', pos: [6.0333, 80.2167], score: 68, faults: 2, fw: 'v1.4.1 (60d)', cyber: 'MEDIUM',
    power: 'Fluctuation',
    tempHistory: [30, 31, 33, 35, 40, 38, 39],
    scoreHistory: [
      { date: '2025-05-25', score: 72, level: 'HIGH', trigger: 'System' },
      { date: '2025-05-26', score: 75, level: 'HIGH', trigger: 'Auto' },
      { date: '2025-05-27', score: 65, level: 'MEDIUM', trigger: 'Manual' },
      { date: '2025-05-28', score: 68, level: 'MEDIUM', trigger: 'Auto' }
    ]
  },
  { 
    id: 3, name: 'Kandy Central EV', loc: 'Kandy', pos: [7.2906, 80.6337], score: 32, faults: 5, fw: 'v1.2.0 (180d)', cyber: 'CRITICAL',
    power: 'Unstable',
    tempHistory: [45, 48, 52, 55, 60, 58, 62],
    scoreHistory: [
      { date: '2025-05-25', score: 40, level: 'MEDIUM', trigger: 'System' },
      { date: '2025-05-26', score: 35, level: 'MEDIUM', trigger: 'Auto' },
      { date: '2025-05-27', score: 32, level: 'MEDIUM', trigger: 'Manual' }
    ]
  },
  { 
    id: 4, name: 'Negombo Hub', loc: 'Negombo', pos: [7.2008, 79.8737], score: 91, faults: 0, fw: 'v2.0.1', cyber: 'LOW',
    power: 'Stable',
  },
  { 
    id: 5, name: 'Jaffna North', loc: 'Jaffna', pos: [9.6615, 80.0255], score: 78, faults: 1, fw: 'v1.8.0', cyber: 'LOW',
    power: 'Stable',
  }
];

const createPinIcon = (color) => {
  // SVG pin icon matching the design
  const svgString = `
    <svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="32" height="40">
      <defs>
        <filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">
          <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.4"/>
        </filter>
      </defs>
      <path d="M 32 2 C 18 2 7 13 7 27 C 7 42 32 62 32 62 C 32 62 57 42 57 27 C 57 13 46 2 32 2 Z" fill="${color}" filter="url(#shadow)"/>
      <circle cx="32" cy="27" r="10" fill="white"/>
    </svg>
  `;
  
  return L.divIcon({
    className: 'custom-pin-icon',
    html: svgString,
    iconSize: [32, 40],
    iconAnchor: [16, 40],
    popupAnchor: [0, -40]
  });
};

const getMarkerIcon = (color) => {
  return createPinIcon(color);
};

const pinColors = {
  green: '#00e676',
  amber: '#ffb300',
  red: '#ff4444',
};

const getRiskMeta = (score = 0) => {
  if (score <= LOW_RISK_MAX) {
    return { key: 'low', badge: 'green', label: 'LOW RISK', shortLabel: 'LOW', color: pinColors.green };
  }
  if (score <= MEDIUM_RISK_MAX) {
    return { key: 'medium', badge: 'amber', label: 'MEDIUM RISK', shortLabel: 'MEDIUM', color: pinColors.amber };
  }
  return { key: 'high', badge: 'red', label: 'HIGH RISK', shortLabel: 'HIGH', color: pinColors.red };
};

const getRiskColor = (score) => {
  return getRiskMeta(score).color;
};

const getHistoryLevelMeta = (level) => {
  if (level === 'LOW' || level === 'SAFE') return { badge: 'green', label: 'LOW' };
  if (level === 'MEDIUM' || level === 'WARN') return { badge: 'amber', label: 'MEDIUM' };
  return { badge: 'red', label: 'HIGH' };
};

const offlineResponses = {
  default: "I'm in offline mode. Cached data: The ChargeSafe SL network monitors 247 stations across Sri Lanka with real-time ML risk scoring. Safe stations score ≥75, Warning 50–74, Critical below 50.",
  colombo: "Colombo Fast Charge (Colpetty, WP): Score 82/100 — Medium Risk. 2 faults detected. Authentication security flagged. Power stability is good. Cyber risk: MEDIUM.",
  safe: "Current safe stations include Negombo Hub (91/100) and Jaffna Charger (78/100). Both show low cyber risk and minimal fault counts.",
  critical: "Critical stations: Galle Rd Charger (38/100) — 7 faults, CRITICAL cyber risk. Avoid this station until maintenance is completed.",
};

const riskOfflineResponses = {
  default: "I'm in offline mode. Cached data: The ChargeSafe SL network monitors 247 stations across Sri Lanka with real-time ML risk scoring. Low risk is 0-30, medium risk is 31-70, and high risk is 71-100.",
  colombo: "Colombo Fast Charge (Colpetty, WP): Risk score 82/100 - High Risk. This usually means the station needs extra caution even if charging is still available. Cyber risk: MEDIUM.",
  safe: "Lower-risk stations are the safest choices. Look for stations closer to the 0-30 range because a lower risk score means a safer station.",
  critical: "High-risk stations are the ones to avoid first. A score in the 71-100 range usually points to overheating, instability, overload, or compatibility concerns.",
};


const toDisplayName = (value) => {
  if (!value) return "User";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const toInitials = (value) => {
  const words = toDisplayName(value).split(" ").filter(Boolean);
  if (!words.length) return "US";
  return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase();
};

const mapBackendUser = (backendUser) => {
  const isAdmin = backendUser?.role === "admin";
  const displayName = toDisplayName(backendUser?.username || backendUser?.email?.split("@")[0]);

  return {
    id: backendUser?.id,
    name: displayName,
    email: backendUser?.email || "",
    role: isAdmin ? "Admin" : "User",
    initials: toInitials(displayName),
    username: backendUser?.username || "",
    isActive: backendUser?.is_active ?? true,
  };
};

const buildUsername = (fullName, email) => {
  const base = (fullName || email || "user")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9_ ]/g, "")
    .replace(/\s+/g, "_")
    .replace(/^_+|_+$/g, "");

  return (base || "user").slice(0, 100);
};

const formatChatMessage = (text = "") => {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  return escaped
    .replace(/\*\*\s*(.+?)\s*\*\*/g, "<strong>$1</strong>")
    .replace(/__(.+?)__/g, "<strong>$1</strong>")
    .replace(/\*\s*(.+?)\s*\*/g, "<em>$1</em>")
    .replace(/_(.+?)_/g, "<em>$1</em>")
    .replace(/\*\*/g, "")
    .replace(/__/g, "")
    .replace(/\n/g, "<br>");
};

function App() {
  const [user, setUser] = useState(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);
  const [securityBusy, setSecurityBusy] = useState(false);
  const [showSplash, setShowSplash] = useState(true);
  const [currentView, setCurrentView] = useState("dashboard"); // default when logged in
  const [authView, setAuthView] = useState("login");
  const [currentStation, setCurrentStation] = useState(stations[0]);
  const [offlineMode, setOfflineMode] = useState(false);
  const [adminSubView, setAdminSubView] = useState('dash');
  const [lastSync, setLastSync] = useState('2025-06-01 11:30');
  const [toasts, setToasts] = useState([]);
  const [messages, setMessages] = useState([
    { role: 'bot', text: "Hello! I'm the ChargeSafe AI assistant. I can help you understand station risk scores, cyber risks, or EV charging safety across Sri Lanka. What would you like to know?" }
  ]);
  const [isTyping, setIsTyping] = useState(false);
  const [clock, setClock] = useState("");
  const [notifications, setNotifications] = useState([
    { id: 'notif-1', icon: '🚨', title: 'Risk Alert — Galle Rd Charger', msg: 'Station risk score rose to 82/100. Authentication failure detected.', time: '2025-06-01 09:14', unread: true, type: 'danger' },
    { id: 'notif-2', icon: '⚠️', title: 'Warning — Kandy Central EV Firmware', msg: 'Firmware version 1.9.2 is 8 months old. Update recommended.', time: '2025-06-01 08:02', unread: true, type: 'warn' },
    { id: 'notif-3', icon: '📋', title: 'Report #102 Status Update', msg: 'Your overheating report for Colpetty station is now under review by admin.', time: '2025-05-31 17:30', unread: true, type: 'info' },
    { id: 'notif-4', icon: '✅', title: 'Report #98 Resolved', msg: 'Your billing error report for Galle station has been resolved.', time: '2025-05-29 12:00', unread: false, type: 'success' },
  ]);
  const [mapFilter, setMapFilter] = useState("all");
  const [mapSearch, setMapSearch] = useState("");
  const [mlScore, setMlScore] = useState(82);

  // Reports State
  const [reportFilter, setReportFilter] = useState("All Status");
  const [userReports, setUserReports] = useState([
    { id: 102, station: 'Colombo Fast Charge — Colpetty', type: 'Overheating', severity: 3, date: '2025-06-01', desc: 'Unit was unusually hot to touch after 20 minutes of charging.', status: 'UNDER REVIEW' },
    { id: 98, station: 'Galle Rd Charger — Galle', type: 'Billing Error', severity: 2, date: '2025-05-28', desc: 'Was charged twice for a single session.', status: 'RESOLVED' },
    { id: 91, station: 'Kandy Central EV — Kandy', type: 'Network Outage', severity: 4, date: '2025-05-20', desc: 'Station completely offline for 3 hours, no error displayed.', status: 'FLAGGED' },
  ]);

  // Settings State
  const [settings, setSettings] = useState({
    pushNotifications: true,
    alertThreshold: 70,
    unitsSystem: "Metric (°C, km)",
    language: "English",
    mapPinColorMode: "Risk Score (Green/Amber/Red)",
    safeThreshold: 30,
    warningThreshold: 70
  });

  const chatMessagesEndRef = useRef(null);
  const historyInitializedRef = useRef(false);
  const splashTimeoutRef = useRef(null);

  const nav = (viewId) => {
    setCurrentView(viewId);
    // Add to browser history so back button works
    window.history.pushState({ view: viewId }, '', `?view=${viewId}`);
  };

  const goBack = () => {
    window.history.back();
  };

  // Handle browser back button
  useEffect(() => {
    if (!historyInitializedRef.current) {
      // Initialize history on app load
      window.history.replaceState({ view: 'dashboard' }, '', `?view=dashboard`);
      historyInitializedRef.current = true;
    }

    const handlePopState = (event) => {
      if (event.state && event.state.view) {
        setCurrentView(event.state.view);
      } else {
        // If back button goes past app history, stay on dashboard
        setCurrentView('dashboard');
        window.history.pushState({ view: 'dashboard' }, '', `?view=dashboard`);
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setClock(now.toLocaleDateString('en-GB') + ' ' + now.toLocaleTimeString('en-GB'));
    };
    tick();
    const interval = setInterval(tick, 1000);
    setLastSync(new Date().toLocaleTimeString());
    return () => clearInterval(interval);
  }, []);

  const playSplash = (duration = 2200) => {
    if (splashTimeoutRef.current) {
      clearTimeout(splashTimeoutRef.current);
    }

    setShowSplash(true);
    splashTimeoutRef.current = setTimeout(() => {
      setShowSplash(false);
      splashTimeoutRef.current = null;
    }, duration);
  };

  useEffect(() => {
    playSplash(2200);

    return () => {
      if (splashTimeoutRef.current) {
        clearTimeout(splashTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const restoreSession = async () => {
      const token = localStorage.getItem(AUTH_TOKEN_KEY);
      if (!token) return;

      try {
        const response = await fetch(`${API_BASE_URL}/me`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          throw new Error("Session expired");
        }

        const data = await response.json();
        setUser(mapBackendUser(data));
      } catch (error) {
        localStorage.removeItem(AUTH_TOKEN_KEY);
      }
    };

    restoreSession();
  }, []);

  useEffect(() => {
    if (chatMessagesEndRef.current) {
      chatMessagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isTyping]);

  const addToast = (msg, type = 'info') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, msg, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3800);
  };

  const openStation = (id) => {
    const s = stations.find(x => x.id === id) || stations[0];
    setCurrentStation(s);
    nav('station');
  };

  const authApi = async (path, options = {}) => {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(options.headers || {}),
        Authorization: `Bearer ${token}`,
      },
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem(AUTH_TOKEN_KEY);
        setUser(null);
        setAuthView('login');
      }
      throw new Error(data.detail || 'Request failed');
    }

    return data;
  };

  const doLogin = async (requireAdmin = false) => {
    const email = document.getElementById('login-email')?.value?.trim() || '';
    const password = document.getElementById('login-pass')?.value || '';

    if (!email || !password) {
      addToast('Enter email and password to continue', 'warn');
      return;
    }

    setAuthBusy(true);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.detail || 'Login failed');
      }

      if (requireAdmin && data.user?.role !== 'admin') {
        throw new Error('This account does not have admin access');
      }

      localStorage.setItem(AUTH_TOKEN_KEY, data.access_token);
      playSplash(1700);
      setUser(mapBackendUser(data.user));
      nav('dashboard');
      setLastSync(new Date().toLocaleTimeString());
      addToast('Login successful', 'success');
    } catch (error) {
      localStorage.removeItem(AUTH_TOKEN_KEY);
      addToast(error.message || 'Unable to login', 'error');
    } finally {
      setAuthBusy(false);
    }
  };

  const doRegister = async () => {
    const fullName = document.getElementById('register-name')?.value?.trim() || '';
    const email = document.getElementById('register-email')?.value?.trim() || '';
    const password = document.getElementById('register-pass')?.value || '';

    if (!fullName || !email || !password) {
      addToast('Fill in name, email, and password', 'warn');
      return;
    }

    setAuthBusy(true);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: buildUsername(fullName, email),
          email,
          password,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.detail || 'Registration failed');
      }

      addToast('Account created! Please login.', 'success');
      setAuthView('login');
    } catch (error) {
      addToast(error.message || 'Unable to create account', 'error');
    } finally {
      setAuthBusy(false);
    }
  };

  const submitIncident = () => {
    const sId = document.getElementById('inc-station')?.value;
    const sName = stations.find(s => s.id == sId)?.name || 'Unknown Station';
    const type = document.getElementById('inc-type')?.value;
    const severity = document.getElementById('inc-severity')?.value;
    const desc = document.getElementById('inc-desc')?.value;

    const newReport = {
      id: userReports.length + 103,
      station: sName,
      type,
      severity,
      date: new Date().toISOString().split('T')[0],
      desc,
      status: 'UNDER REVIEW'
    };

    setUserReports(prev => [newReport, ...prev]);
    addToast('Incident report submitted successfully', 'success');
    nav('my-reports');
  };

  const submitIncidentRescore = () => {
    const sId = document.getElementById('inc-station')?.value;
    const sName = stations.find(s => s.id == sId)?.name || 'Unknown Station';
    const type = document.getElementById('inc-type')?.value;
    const severity = document.getElementById('inc-severity')?.value;
    const desc = document.getElementById('inc-desc')?.value;

    const newReport = {
      id: userReports.length + 103,
      station: sName,
      type,
      severity,
      date: new Date().toISOString().split('T')[0],
      desc,
      status: 'UNDER REVIEW'
    };

    setUserReports(prev => [newReport, ...prev]);
    addToast('Report submitted & ML rescore triggered ↺', 'success');
    nav('mlscore');
  };

  const doLogout = () => {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    setUser(null);
    setAuthView("login");
  };

  const recalculateMlScore = () => {
    addToast('ML rescore triggered… recalculating ↺', 'info');
    setTimeout(() => {
      const newScore = Math.floor(Math.random() * 30) + 70;
      setMlScore(newScore);
      addToast(`New score: ${newScore}/100`, newScore <= LOW_RISK_MAX ? 'success' : 'warn');
    }, 1800);
  };

  const markAllRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, unread: false })));
    addToast('All notifications marked as read', 'success');
  };

  const clearNotifs = () => {
    setNotifications([]);
    addToast('Notifications cleared', 'info');
  };

  const dismissNotif = (id) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  const toggleOfflineMode = () => {
    setOfflineMode(!offlineMode);
    addToast(!offlineMode ? 'Offline mode enabled — using cached data' : 'Online mode — AI enabled', 'info');
  };

  const sendChat = async () => {
    const inputEl = document.getElementById('chat-input');
    const msg = inputEl?.value.trim();
    if (!msg) return;
    inputEl.value = '';
    setMessages(prev => [...prev, { role: 'user', text: msg }]);

    if (offlineMode) {
      let resp = riskOfflineResponses.default;
      const ml = msg.toLowerCase();
      if (ml.includes('colombo')) resp = riskOfflineResponses.colombo;
      else if (ml.includes('safe') || ml.includes('safest') || ml.includes('low risk')) resp = riskOfflineResponses.safe;
      else if (ml.includes('critical') || ml.includes('dangerous') || ml.includes('high risk')) resp = riskOfflineResponses.critical;
      setTimeout(() => {
        setMessages(prev => [...prev, { role: 'bot', text: resp }]);
      }, 600);
      return;
    }

    setIsTyping(true);
    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: msg
        })
      });

      if (!response.ok) throw new Error("API failed");
      const data = await response.json();
      setMessages(prev => [...prev, { role: 'bot', text: data.reply || 'Sorry, I could not get a response.' }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'bot', text: 'Connection error. Switching to Offline Mode or simulated response: Based on our data, Colombo Fast Charge is currently at 82/100 risk score, which is high risk.' }]);
    } finally {
      setIsTyping(false);
    }
  };

  const quickChat = (msg) => {
    document.getElementById('chat-input').value = msg;
    sendChat();
  };

  const saveProfile = async () => {
    const nameInput = document.getElementById('prof-name');
    if (!nameInput || !user) return;

    const name = nameInput.value.trim();
    if (!name) {
      addToast('Please enter your name', 'warn');
      return;
    }

    setProfileBusy(true);

    try {
      const username = buildUsername(name, user.email);
      const data = await authApi(`/me?username=${encodeURIComponent(username)}`, {
        method: 'PUT',
      });
      setUser(mapBackendUser(data));
      addToast('Profile saved successfully', 'success');
    } catch (error) {
      addToast(error.message || 'Unable to save profile', 'error');
    } finally {
      setProfileBusy(false);
    }
  };

  const changePassword = async () => {
    const currentPassword = document.getElementById('sec-current-pass')?.value || '';
    const newPassword = document.getElementById('sec-new-pass')?.value || '';
    const confirmPassword = document.getElementById('sec-confirm-pass')?.value || '';

    if (!currentPassword || !newPassword || !confirmPassword) {
      addToast('Fill in all password fields', 'warn');
      return;
    }

    if (newPassword !== confirmPassword) {
      addToast('New password and confirmation must match', 'warn');
      return;
    }

    setSecurityBusy(true);

    try {
      const data = await authApi('/me/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });

      ['sec-current-pass', 'sec-new-pass', 'sec-confirm-pass'].forEach((id) => {
        const element = document.getElementById(id);
        if (element) element.value = '';
      });

      addToast(data.message || 'Password changed successfully', 'success');
    } catch (error) {
      const message = error?.message === 'INCORRECT CURRENT PASSWORD'
        ? 'INCORRECT CURRENT PASSWORD'
        : (error?.message || 'Unable to change password');
      addToast(message, 'error');
    } finally {
      setSecurityBusy(false);
    }
  };

  const deleteAccount = async () => {
    const currentPassword = document.getElementById('sec-current-pass')?.value || '';

    if (!currentPassword) {
      addToast('Enter your current password before deleting your account', 'warn');
      return;
    }

    if (!window.confirm('Are you sure you want to permanently delete your account and associated data?')) {
      return;
    }

    setSecurityBusy(true);

    try {
      const data = await authApi('/me/delete', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          current_password: currentPassword,
        }),
      });

      localStorage.removeItem(AUTH_TOKEN_KEY);
      setUser(null);
      setAuthView('login');
      addToast(data.message || 'Account deleted successfully', 'success');
    } catch (error) {
      addToast(error.message || 'Unable to delete account', 'error');
    } finally {
      setSecurityBusy(false);
    }
  };

  const saveSettings = () => {
    addToast('Settings saved successfully', 'success');
  };

  const updateSetting = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const splashOverlay = showSplash ? (
    <div id="splash-screen">
      <div className="splash-grid"></div>
      <div className="splash-glow splash-glow-left"></div>
      <div className="splash-glow splash-glow-right"></div>
      <div className="splash-brand">
        <img src="/logo.png" alt="ChargeSafe SL Logo" className="splash-logo-img" />
        <div className="splash-logo-text">ChargeSafe<span>&nbsp;SL</span></div>
        <div className="splash-tag">Secure EV Charging Intelligence</div>
      </div>
    </div>
  ) : null;

  if (!user) {
    return (
      <div id="auth-wrapper">
        {authView === 'login' ? (
          <div id="auth-login" className="auth-box">
            <div className="auth-logo">
              <img src="/logo.png" alt="ChargeSafe SL Logo" className="auth-logo-img" />
              <div className="auth-logo-text">ChargeSafe<span>&nbsp;SL</span></div>
            </div>
            <div className="auth-title">System Login</div>
            <label className="auth-label">Email Address</label>
            <input className="auth-input" id="login-email" type="email" placeholder="you@example.com" />
            <label className="auth-label">Password</label>
            <input className="auth-input" id="login-pass" type="password" placeholder="••••••••" />
            <button className="btn-full btn-green" onClick={() => doLogin(false)} style={{ marginBottom: '10px' }} disabled={authBusy}>{authBusy ? 'Please wait...' : 'Login'}</button>
            <button className="btn-full btn-outline" onClick={() => doLogin(true)} disabled={authBusy}>Admin Login</button>
            <div className="auth-switch" style={{ marginTop: '14px' }}>
              No account? <a onClick={() => setAuthView('register')}>Register here</a>
            </div>
          </div>
        ) : (
          <div id="auth-register" className="auth-box">
            <div className="auth-logo">
              <img src="/logo.png" alt="ChargeSafe SL Logo" className="auth-logo-img" />
              <div className="auth-logo-text">ChargeSafe<span>&nbsp;SL</span></div>
            </div>
            <div className="auth-title">Create Account</div>
            <div className="form-row">
              <div className="form-group"><label className="auth-label">Full Name</label><input className="auth-input" id="register-name" placeholder="Kavindu Perera" style={{ marginBottom: 0 }} /></div>
            </div>
            <label className="auth-label">Email Address</label>
            <input className="auth-input" id="register-email" type="email" placeholder="you@example.com" />
            <label className="auth-label">Password</label>
            <input className="auth-input" id="register-pass" type="password" placeholder="••••••••" />
            <label className="auth-label">Vehicle Model</label>
            <input className="auth-input" id="register-vehicle" placeholder="Nissan Leaf, Tesla Model 3…" />
            <button className="btn-full btn-green" onClick={doRegister} disabled={authBusy}>{authBusy ? 'Please wait...' : 'Create Account'}</button>
            <div className="auth-switch">Already registered? <a onClick={() => setAuthView('login')}>Login here</a></div>
          </div>
        )}
        <div id="toast-container">
          {toasts.map(t => (
            <div key={t.id} className={`toast ${t.type}`}>
              <span>{t.type === 'success' ? '✓' : t.type === 'warn' ? '⚠' : t.type === 'error' ? '✕' : 'ℹ'}</span>
              <span>{t.msg}</span>
            </div>
          ))}
        </div>
        {splashOverlay}
      </div>
    );
  }

  const unreadCount = notifications.filter(n => n.unread).length;

  return (
    <div id="app">
      {/* SIDEBAR */}
      <div id="sidebar">
        <div className="sb-logo">
          <img src="/logo.png" alt="Logo" className="sb-logo-img" />
          <div className="sb-logo-txt">ChargeSafe<span>&nbsp;SL</span></div>
        </div>
        <div className="sb-user">
          <div className="sb-avatar">{user.initials}</div>
          <div className="sb-user-info">
            <div className="sb-user-name">{user.name}</div>
            <div className="sb-user-role">{user.role}</div>
          </div>
        </div>
        <nav>
        <div className="sidebar-group">
          <div className="sidebar-label">MONITOR</div>
          <div className={`nav-item ${currentView === 'dashboard' ? 'active' : ''}`} onClick={() => nav('dashboard')}>
            <span className="nav-icon">📊</span> Dashboard
          </div>
          <div className={`nav-item ${currentView === 'map' ? 'active' : ''}`} onClick={() => nav('map')}>
            <span className="nav-icon">🗺️</span> Map View
          </div>
        </div>

        <div className="sidebar-group">
          <div className="sidebar-label">USER</div>
          <div className={`nav-item ${currentView === 'my-reports' ? 'active' : ''}`} onClick={() => nav('my-reports')}>
            <span className="nav-icon">📋</span> My Reports
          </div>
          <div className={`nav-item ${currentView === 'chatbot' ? 'active' : ''}`} onClick={() => nav('chatbot')}>
            <span className="nav-icon">🤖</span> AI Chatbot
          </div>
          <div className={`nav-item ${currentView === 'notifications' ? 'active' : ''}`} onClick={() => nav('notifications')}>
            <span className="nav-icon">🔔</span> Notifications
            {unreadCount > 0 && <span className="notif-badge-count">{unreadCount}</span>}
          </div>
        </div>

        <div className="sidebar-group">
          <div className="sidebar-label">ACCOUNT</div>
          <div className={`nav-item ${currentView === 'profile' ? 'active' : ''}`} onClick={() => nav('profile')}>
            <span className="nav-icon">👤</span> Profile
          </div>
          <div className={`nav-item ${currentView === 'settings' ? 'active' : ''}`} onClick={() => nav('settings')}>
            <span className="nav-icon">⚙️</span> Settings
          </div>
        </div>

        {user.role === 'Admin' && (
          <div className="sidebar-group">
            <div className="sidebar-label">ADMIN</div>
            <div className={`nav-item ${currentView.startsWith('admin') ? 'active' : ''}`} onClick={() => nav('admin-dash')}>
              <span className="nav-icon">🛡️</span> Admin Panel
            </div>
          </div>
        )}
        </nav>
        <div className="sb-bottom">
          <div className="sb-status"><div className="status-dot"></div><span className="mono">LIVE — 247 stations</span></div>
          <button className="btn-logout" onClick={doLogout}>⏻&nbsp; Logout</button>
        </div>
      </div>

      {/* MAIN */}
      <div id="main">
        <div id="topbar">
          <div className="topbar-title">{currentView.replace('-', ' ').toUpperCase()}</div>
          <div className="topbar-right">
            <div className="topbar-time mono">{clock}</div>
            <div className="topbar-notif" onClick={() => nav('notifications')}>🔔{unreadCount > 0 && <div className="notif-badge">{unreadCount}</div>}</div>
          </div>
        </div>
        <div id="content">

          {/* DASHBOARD */}
          {currentView === 'dashboard' && (
            <div className="view active" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div className="live-ticker">
                <div className="ticker-scroll">
                  {stations.concat(stations).map((s, i) => (
                    <span key={i} className="ticker-chip">{s.name.toUpperCase()} <span className={getRiskMeta(s.score).badge}>{getRiskMeta(s.score).shortLabel} {s.score}/100</span></span>
                  ))}
                </div>
              </div>

              {/* MAIN DASHBOARD LAYOUT - MAP ON LEFT, ALL CONTENT ON RIGHT - NO SCROLLING */}
              <div style={{ display: 'flex', gap: '24px', alignItems: 'flex-start', maxWidth: '100%' }}>
                
                {/* LEFT SIDE - MAP (FIXED WIDTH) */}
                <div className="card interactive-banner-map" style={{ padding: 0, width: '320px', flexShrink: 0, aspectRatio: '3/4', overflow: 'hidden', borderBottom: '2px solid var(--border)' }}>
                  <MapContainer 
                    center={[7.8731, 80.7718]} 
                    zoom={6} 
                    minZoom={6}
                    maxBounds={srilankaBounds}
                    maxBoundsViscosity={1.0}
                    zoomControl={false} 
                    style={{ height: '100%', width: '100%', background: 'var(--bg0)' }}
                  >
                    <TileLayer
                      url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                      attribution='&copy; OpenStreetMap contributors'
                    />
                    {stations.map(s => (
                      <Marker 
                        key={s.id} 
                        position={s.pos} 
                        icon={getMarkerIcon(getRiskColor(s.score))}
                        eventHandlers={{ click: () => openStation(s.id) }}
                      />
                    ))}
                    <MapResizer />
                  </MapContainer>
                  <div style={{ position: 'absolute', bottom: '10px', right: '10px', zIndex: 1000, background: 'rgba(10,22,40,0.8)', padding: '2px 8px', borderRadius: '4px', fontSize: '10px', color: 'var(--txt3)', fontFamily: 'Fira Code' }}>
                     247 STATIONS MONITORED
                  </div>
                </div>

                {/* RIGHT SIDE - CONTENT (STACKED VERTICALLY) */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1, minWidth: 0 }}>
                  {/* DASHBOARD SUMMARY CARDS - 2x2 GRID */}
                  <div className="grid2">
                    <div className="card stat-card">
                      <div className="stat-num cyan" style={{ fontSize: '20px' }}>247</div>
                      <div className="stat-label">Total Stations</div>
                    </div>
                    <div className="card stat-card">
                      <div className="stat-num green" style={{ fontSize: '20px' }}>184</div>
                      <div className="stat-label">Safe Stations</div>
                    </div>
                    <div className="card stat-card">
                      <div className="stat-num amber" style={{ fontSize: '20px' }}>42</div>
                      <div className="stat-label">Warning Status</div>
                    </div>
                    <div className="card stat-card">
                      <div className="stat-num red" style={{ fontSize: '20px' }}>21</div>
                      <div className="stat-label">High-Risk Stations</div>
                    </div>
                  </div>

                  {/* LIVE NETWORK FEED */}
                  <div className="card" style={{ padding: '12px 16px', background: 'rgba(0,255,255,0.03)', border: '1px solid rgba(0,255,255,0.1)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div className="badge badge-cyan" style={{ fontSize: '8px', padding: '2px 6px', flexShrink: 0 }}>LIVE</div>
                      <div style={{ flex: 1, overflow: 'hidden', whiteSpace: 'nowrap', position: 'relative' }}>
                        <div className="marquee" style={{ fontSize: '10px', color: 'var(--cyan)', fontFamily: 'Fira Code' }}>
                          [11:02] Kandy Central EV — Firmware upgrade initiated ... [10:55] Colombo Fast Charge — Score updated to 94/100 ... [10:48] Galle Rd Charger — Billing error report received ...
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* QUICK ACTIONS & RECENT ALERTS - 2 COLUMN */}
                  <div className="grid2" style={{ gap: '16px' }}>
                    {/* QUICK ACTIONS */}
                    <div className="card">
                      <div className="card-header" style={{ marginBottom: '12px' }}><span className="card-title" style={{ fontSize: '10px' }}>QUICK ACTIONS</span></div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <button className="btn btn-accent cyan-a" onClick={() => nav('map')} style={{ fontSize: '9px', padding: '6px 12px' }}>
                          <span style={{ fontSize: '12px' }}>🗺️</span> MAP VIEW
                        </button>
                        <button className="btn btn-accent amber-a" onClick={() => nav('incident')} style={{ fontSize: '9px', padding: '6px 12px' }}>
                          <span style={{ fontSize: '12px' }}>🚨</span> INCIDENT
                        </button>
                        <button className="btn btn-accent blue-a" onClick={() => nav('chatbot')} style={{ fontSize: '9px', padding: '6px 12px' }}>
                          <span style={{ fontSize: '12px' }}>🤖</span> CHATBOT
                        </button>
                      </div>
                    </div>

                    {/* RECENT ALERTS */}
                    <div className="card">
                      <div className="card-header" style={{ marginBottom: '12px' }}>
                        <span className="card-title" style={{ fontSize: '10px' }}>ALERTS</span>
                        <span className="badge badge-red" style={{ fontSize: '8px' }}>3 NEW</span>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {notifications.slice(0, 2).map(n => (
                          <div key={n.id} style={{ padding: '8px', background: 'rgba(255,255,255,0.02)', borderRadius: '3px', fontSize: '9px' }}>
                            <div style={{ color: n.type === 'danger' ? 'var(--red)' : 'var(--amber)', fontWeight: 600 }}>{n.title}</div>
                            <div style={{ color: 'var(--txt3)', fontSize: '8px', marginTop: '2px' }}>{n.time}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* TOP STATIONS TABLE */}
              <div className="card">
                <div className="card-header">
                  <span className="card-title">Network Status — Top Stations</span>
                  <button className="btn btn-sm btn-ghost" onClick={() => nav('map')}>VIEW ALL ON MAP →</button>
                </div>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Station</th>
                      <th>Location</th>
                      <th>Risk Score</th>
                      <th>Cyber Risk</th>
                      <th>Faults</th>
                      <th>Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stations.slice(0, 5).map(s => (
                      <tr key={s.id}>
                        <td style={{ fontWeight: 600, color: 'var(--txt)' }}>{s.name}</td>
                        <td>{s.loc}</td>
                        <td><span style={{ color: getRiskMeta(s.score).color, fontWeight: 700 }}>{s.score}/100</span></td>
                        <td><span className={`badge badge-${getRiskMeta(s.score).badge}`}>{s.cyber}</span></td>
                        <td className="mono">{s.faults}</td>
                        <td><span className={`badge badge-${getRiskMeta(s.score).badge}`}>{getRiskMeta(s.score).label}</span></td>
                        <td><button className="btn btn-sm btn-primary" onClick={() => openStation(s.id)}>DETAILS</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* MAP VIEW (Interactive OSM) */}
          {currentView === 'map' && (
            <div className="view active" style={{ padding: 0, height: 'calc(100vh - 52px)', position: 'relative' }}>
              <div className="map-overlay-controls">
                <div className="page-header" style={{ marginBottom: '16px' }}>
                  <div className="page-label">// GEOSPATIAL MONITORING</div>
                  <div className="page-title" style={{ fontSize: '18px' }}>STATION NETWORK MAP</div>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <input 
                    className="form-input" 
                    placeholder="Search stations..." 
                    style={{ width: '180px', margin: 0, height: '32px', fontSize: '12px' }}
                    value={mapSearch}
                    onChange={(e) => setMapSearch(e.target.value)}
                  />
                  <select 
                    className="form-input" 
                    style={{ width: '120px', margin: 0, height: '32px', fontSize: '12px' }}
                    value={mapFilter}
                    onChange={(e) => setMapFilter(e.target.value)}
                  >
                    <option value="all">All Risks</option>
                    <option value="low">Low Risk</option>
                    <option value="medium">Medium Risk</option>
                    <option value="high">High Risk</option>
                  </select>
                </div>
              </div>

              <MapContainer 
                center={[7.8731, 80.7718]} 
                zoom={8} 
                minZoom={7}
                maxBounds={srilankaBounds}
                maxBoundsViscosity={1.0}
                style={{ height: '100%', width: '100%' }}
              >
                <TileLayer
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  attribution='&copy; OpenStreetMap contributors'
                />
                <MapResizer />
                {stations
                  .filter(s => mapFilter === 'all' || getRiskMeta(s.score).key === mapFilter)
                  .filter(s => s.name.toLowerCase().includes(mapSearch.toLowerCase()) || s.loc.toLowerCase().includes(mapSearch.toLowerCase()))
                  .map(s => (
                    <Marker 
                      key={s.id} 
                      position={s.pos} 
                      icon={getMarkerIcon(getRiskColor(s.score))}
                    >
                      <Popup>
                        <div className="map-popup">
                          <strong style={{ color: '#000', fontSize: '13px' }}>{s.name}</strong><br/>
                          <span style={{ color: '#444', fontSize: '11px' }}>{s.loc}</span><br/>
                          <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ color: getRiskColor(s.score), fontWeight: 700, fontSize: '14px' }}>{s.score}/100</span>
                            <button className="btn btn-sm btn-primary" style={{ padding: '4px 8px', fontSize: '9px' }} onClick={() => openStation(s.id)}>DETAILS</button>
                          </div>
                        </div>
                      </Popup>
                    </Marker>
                  ))
                }
              </MapContainer>
            </div>
          )}

          {/* STATION DETAILS */}
          {currentView === 'station' && (
            <div className="view active">
              <div className="flex-between mb24">
                <div>
                  <div className="page-label">Station Details</div>
                  <div className="page-title">{currentStation.name}</div>
                  <div style={{ fontFamily: 'Fira Code,monospace', fontSize: '11px', color: 'var(--txt3)', marginTop: '4px' }}>{currentStation.loc}</div>
                </div>
                <button className="btn btn-ghost" onClick={() => nav('map')}>← Back to Map</button>
              </div>
              <div className="grid2 mb16">
                <div className="card">
                  <div className="card-header"><span className="card-title">Station Info</span><span className={`badge badge-${getRiskMeta(currentStation.score).badge}`}>{getRiskMeta(currentStation.score).label}</span></div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div className="flex-between"><span style={{ fontSize: '12px', color: 'var(--txt3)' }}>Risk Score</span><span className={`orb text-${getRiskMeta(currentStation.score).badge}`} style={{ fontSize: '20px', fontWeight: 700 }}>{currentStation.score}/100</span></div>
                    <div className="risk-bar-wrap"><div className={`risk-bar-fill ${getRiskMeta(currentStation.score).badge}`} style={{ width: `${currentStation.score}%` }}></div></div>
                    <div className="flex-between"><span style={{ fontSize: '12px', color: 'var(--txt3)' }}>Fault Count</span><span className="mono">{currentStation.faults} faults</span></div>
                    <div className="flex-between"><span style={{ fontSize: '12px', color: 'var(--txt3)' }}>Firmware Age</span><span className="mono">{currentStation.fw}</span></div>
                    <div className="flex-between"><span style={{ fontSize: '12px', color: 'var(--txt3)' }}>Power Stability</span><span className="mono text-green">{currentStation.power}</span></div>
                  </div>
                </div>
                <div className="card">
                  <div className="card-header"><span className="card-title">Actions</span></div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <button className="btn btn-primary" onClick={() => nav('mlscore')}>⚡ View ML Risk Score</button>
                    <button className="btn btn-ghost" style={{ border: '1px solid var(--cyan)', color: 'var(--cyan)' }} onClick={() => nav('cyber')}>🛡️ Cyber Risk Assessment</button>
                    <button className="btn btn-warn" onClick={() => nav('incident')}>🚨 Report Incident</button>
                    <button className="btn btn-ghost" onClick={() => nav('chatbot')}>🤖 Ask AI Chatbot</button>
                  </div>
                </div>
              </div>

              {/* TEMP HISTORY CHART (FR-15) */}
              <div className="card mb16">
                <div className="card-header"><span className="card-title">7-Day Temperature History trend</span></div>
                <div style={{ width: '100%', height: '120px', display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', padding: '0 20px', gap: '10px' }}>
                  {(currentStation.tempHistory || [30,32,35,40,38,36,34]).map((t, i) => (
                    <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                      <div style={{ width: '100%', height: `${t * 2}px`, background: t > 45 ? 'var(--red)' : t > 38 ? 'var(--amber)' : 'var(--cyan)', borderRadius: '2px 2px 0 0', position: 'relative' }}>
                        <div style={{ position: 'absolute', top: '-18px', width: '100%', textAlign: 'center', fontSize: '9px', color: 'var(--txt3)' }}>{t}°</div>
                      </div>
                      <div style={{ fontSize: '9px', color: 'var(--txt3)', marginTop: '6px' }}>Day {i+1}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* CYBER RISK ASSESSMENT (FR-25 to FR-28) */}
          {currentView === 'cyber' && (
            <div className="view active" style={{ padding: '24px' }}>
              <div className="flex-between mb24">
                <div><div className="page-label" style={{ color: 'var(--cyan)' }}>// SECURITY ANALYTICS</div><div className="page-title" style={{ fontSize: '24px' }}>CYBER RISK ASSESSMENT</div></div>
                <button className="btn btn-ghost" onClick={() => nav('station')}>← STATION DETAILS</button>
              </div>

              <div className="grid2 mb24">
                <div className="card" style={{ padding: '20px' }}>
                  <div className="card-header"><span className="card-title">Overall Risk Rating (FR-28)</span><span className={`badge badge-${currentStation.cyber === 'LOW' ? 'green' : currentStation.cyber === 'MEDIUM' ? 'amber' : 'red'}`}>{currentStation.cyber} RISK</span></div>
                  <div style={{ textAlign: 'center', padding: '24px 0' }}>
                    <div style={{ fontSize: '10px', color: 'var(--txt3)', marginBottom: '8px', fontFamily: 'Fira Code' }}>COMPOSITE SECURITY SCORE</div>
                    <div className={currentStation.cyber === 'LOW' ? 'green' : currentStation.cyber === 'MEDIUM' ? 'amber' : 'red'} style={{ fontSize: '56px', fontWeight: 800, fontFamily: 'Orbitron' }}>
                      {currentStation.cyber === 'LOW' ? '92' : currentStation.cyber === 'MEDIUM' ? '64' : '28'}
                    </div>
                    <div style={{ marginTop: '12px', fontSize: '11px', color: 'var(--txt2)' }}>Last scan: Today, 08:45 AM</div>
                  </div>
                </div>
                <div className="card" style={{ padding: '20px' }}>
                  <div className="card-header"><span className="card-title">Compliance Status</span></div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '10px' }}>
                    <div className="flex-between" style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '4px', border: '1px solid var(--border)' }}>
                      <div style={{ fontSize: '12px', fontWeight: 500 }}>IEC 62443 Standard</div>
                      <span className="badge badge-green">COMPLIANT</span>
                    </div>
                    <div className="flex-between" style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '4px', border: '1px solid var(--border)' }}>
                      <div style={{ fontSize: '12px', fontWeight: 500 }}>OWASP IoT Top 10</div>
                      <button className="btn btn-sm btn-ghost" onClick={() => addToast('Scan initiated...', 'info')}>RUN CHECK</button>
                    </div>
                    <div className="flex-between" style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '4px', border: '1px solid var(--border)' }}>
                      <div style={{ fontSize: '12px', fontWeight: 500 }}>ISO/SAE 21434</div>
                      <span className="badge badge-amber">PARTIAL</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="card" style={{ padding: '20px' }}>
                <div className="card-header"><span className="card-title">Security Check Results (FR-25)</span></div>
                <table className="data-table">
                  <thead>
                    <tr><th>Category</th><th>Details</th><th>Status</th></tr>
                  </thead>
                  <tbody>
                    <tr><td>Firmware Security</td><td>Encrypted & Signed with v2.1 keys</td><td><span className="text-green" style={{ fontWeight: 600 }}>PASS</span></td></tr>
                    <tr><td>Authentication</td><td>Multi-factor auth enforced</td><td><span className="text-green" style={{ fontWeight: 600 }}>PASS</span></td></tr>
                    <tr><td>Network Security</td><td>TLS 1.3 encryption, port lockdowns</td><td><span className="text-amber" style={{ fontWeight: 600 }}>PARTIAL</span></td></tr>
                    <tr><td>Physical Security</td><td>Tamper-detection hardware active</td><td><span className="text-red" style={{ fontWeight: 600 }}>FAIL</span></td></tr>
                    <tr><td>Data Privacy</td><td>Fully anonymized PII telemetry</td><td><span className="text-green" style={{ fontWeight: 600 }}>PASS</span></td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ML RISK SCORE */}
          {currentView === 'mlscore' && (
            <div className="view active">
              <div className="flex-between mb24">
                <div><div className="page-label">AI Risk Engine</div><div className="page-title">ML Risk Score</div></div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button className="btn btn-ghost" onClick={() => nav('station')}>← Station Details</button>
                  <button className="btn btn-primary" onClick={recalculateMlScore}>⟳ Recalculate Score</button>
                </div>
              </div>
              <div className="grid2 mb16">
                <div className="card">
                  <div className="card-header"><span className="card-title">{currentStation.name} — Risk Score</span><span className={`badge badge-${getRiskMeta(mlScore).badge}`}>{getRiskMeta(mlScore).label}</span></div>
                  <div className="gauge-wrap">
                    <svg className="gauge-svg" viewBox="0 0 180 110">
                      <path d="M 18 95 A 72 72 0 0 1 162 95" fill="none" stroke="#1a3050" strokeWidth="11" strokeLinecap="round" />
                      <path d="M 18 95 A 72 72 0 0 1 162 95" fill="none" stroke={getRiskMeta(mlScore).badge === 'green' ? "var(--green)" : getRiskMeta(mlScore).badge === 'amber' ? "var(--amber)" : "var(--red)"} strokeWidth="11" strokeLinecap="round" strokeDasharray="226" strokeDashoffset={226 - (mlScore / 100) * 226} style={{ transition: 'stroke-dashoffset 1.2s ease, stroke .4s ease' }} />
                    </svg>
                    <div className={`gauge-score ${getRiskMeta(mlScore).badge}`}>{mlScore}</div>
                    <div className="gauge-sub">/ 100 — ML RISK SCORE</div>
                  </div>
                </div>
                <div className="card">
                  <div className="card-header"><span className="card-title">Risk Factors (FR-22)</span></div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <div className="factor-row"><span className="factor-label">Temp History</span><div className="factor-bar-wrap"><div className="factor-fill pass" style={{ width: '95%' }}></div></div><span className="factor-status pass">PASS</span></div>
                    <div className="factor-row"><span className="factor-label">Fault Count</span><div className="factor-bar-wrap"><div className={`factor-fill ${currentStation.faults < 3 ? 'pass' : 'warn'}`} style={{ width: '60%' }}></div></div><span className={`factor-status ${currentStation.faults < 3 ? 'pass' : 'warn'}`}>{currentStation.faults < 3 ? 'PASS' : 'WARN'}</span></div>
                    <div className="factor-row"><span className="factor-label">Firmware Age</span><div className="factor-bar-wrap"><div className="factor-fill pass" style={{ width: '85%' }}></div></div><span className="factor-status pass">PASS</span></div>
                    <div className="factor-row"><span className="factor-label">Power Stability</span><div className="factor-bar-wrap"><div className="factor-fill pass" style={{ width: '92%' }}></div></div><span className="factor-status pass">PASS</span></div>
                    <div className="factor-row"><span className="factor-label">Auth Security</span><div className="factor-bar-wrap"><div className="factor-fill pass" style={{ width: '100%' }}></div></div><span className="factor-status pass">PASS</span></div>
                    <div className="factor-row"><span className="factor-label">Network Security</span><div className="factor-bar-wrap"><div className="factor-fill fail" style={{ width: '40%' }}></div></div><span className="factor-status fail">FAIL</span></div>
                  </div>
                </div>
              </div>

              {/* SCORE HISTORY TABLE (FR-24) */}
              <div className="card">
                <div className="card-header"><span className="card-title">Risk Score History (Last 6 Readings)</span></div>
                <table className="data-table">
                  <thead>
                    <tr><th>Date</th><th>Score</th><th>Level</th><th>Trigger</th></tr>
                  </thead>
                  <tbody>
                    {(currentStation.scoreHistory || []).slice(-6).reverse().map((h, i) => (
                      <tr key={i}>
                        <td className="mono">{h.date}</td>
                        <td style={{ fontWeight: 600 }}>{h.score}/100</td>
                        <td><span className={`badge badge-${getHistoryLevelMeta(h.level).badge}`}>{getHistoryLevelMeta(h.level).label}</span></td>
                        <td className="mono">{h.trigger}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* AI CHATBOT */}
          {currentView === 'chatbot' && (
            <div className="view active">
              <div className="page-header">
                <div className="page-label">AI Assistant</div>
                <div className="page-title">AI Chatbot (Gemini)</div>
              </div>
              <div className="grid2" style={{ alignItems: 'start' }}>
                <div className="card" style={{ padding: 0 }}>
                  <div className="card-header" style={{ padding: '14px 16px' }}>
                    <span className="card-title">ChargeSafe AI</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span className={`badge badge-${offlineMode ? 'amber' : 'green'}`}>{offlineMode ? '⚡ OFFLINE' : '● ONLINE'}</span>
                      <button className="btn btn-sm btn-ghost" onClick={toggleOfflineMode}>⇌ Offline Mode</button>
                    </div>
                  </div>
                  {offlineMode && <div className="offline-banner" style={{ display: 'block' }}>⚠️ Offline mode — using cached responses only</div>}
                  <div className="chat-messages">
                    {messages.map((m, i) => (
                      <div key={i} className={`chat-msg ${m.role}`}>
                        <div className={`chat-avatar ${m.role}`}>{m.role === 'bot' ? 'AI' : '👤'}</div>
                        <div className="chat-bubble" dangerouslySetInnerHTML={{ __html: formatChatMessage(m.text) }}></div>
                      </div>
                    ))}
                    {isTyping && (
                      <div className="chat-msg bot">
                        <div className="chat-avatar bot">AI</div>
                        <div className="typing-indicator"><div className="typing-dot"></div><div className="typing-dot"></div><div className="typing-dot"></div></div>
                      </div>
                    )}
                    <div ref={chatMessagesEndRef} />
                  </div>
                  <div className="chat-input-row">
                    <input className="chat-input" id="chat-input" placeholder="Ask about any station…" onKeyDown={(e) => e.key === 'Enter' && sendChat()} />
                    <button className="chat-send" onClick={sendChat}>Send →</button>
                  </div>
                </div>
                <div className="card">
                  <div className="card-header"><span className="card-title">Quick Questions</span></div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <button className="btn btn-ghost btn-sm" onClick={() => quickChat('Why is Colombo Fast Charge high risk?')}>Why is Colombo Fast Charge high risk?</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => quickChat('Which stations are high risk right now?')}>Which stations are high risk right now?</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => quickChat('Which stations are lowest risk in Western Province?')}>Which stations are lowest risk in Western Province?</button>
                  </div>
                </div>

                {/* STATION LOOKUP TABLE (FR-40) */}
                <div className="card">
                  <div className="card-header"><span className="card-title">Station Quick Lookup</span></div>
                  <div className="scrollable" style={{ maxHeight: '300px' }}>
                    <table className="data-table" style={{ fontSize: '11px' }}>
                      <thead><tr><th>Station</th><th>Score</th><th>Status</th></tr></thead>
                      <tbody>
                        {stations.map(s => (
                          <tr key={s.id}>
                            <td>{s.name}</td>
                            <td className="mono">{s.score}</td>
                            <td><span className={`badge badge-${getRiskMeta(s.score).badge}`} style={{ fontSize: '9px' }}>{getRiskMeta(s.score).shortLabel}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* NOTIFICATIONS */}
          {currentView === 'notifications' && (
            <div className="view active">
              <div className="flex-between mb24">
                <div><div className="page-label">Alerts & Updates</div><div className="page-title">Notifications</div></div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button className="btn btn-ghost btn-sm" onClick={markAllRead}>✓ Mark All Read</button>
                  <button className="btn btn-danger btn-sm" onClick={clearNotifs}>✕ Clear All</button>
                </div>
              </div>
              <div id="notif-list">
                {notifications.length === 0 ? (
                  <div style={{ padding: '24px', textAlign: 'center', fontFamily: 'Fira Code,monospace', fontSize: '11px', color: 'var(--txt3)' }}>No notifications</div>
                ) : (
                  notifications.map(n => (
                    <div key={n.id} className={`notif-item ${n.unread ? 'unread' : ''}`} style={{ borderLeft: n.unread ? `3px solid var(--${n.type === 'danger' ? 'red' : n.type === 'warn' ? 'amber' : 'cyan'})` : '' }}>
                      <div className="notif-icon">{n.icon}</div>
                      <div className="notif-content">
                        <div className="notif-title">{n.title}</div>
                        <div className="notif-msg">{n.msg}</div>
                        <div className="notif-time">{n.time}</div>
                        <div className="notif-actions">
                          <button className="btn btn-sm btn-ghost" onClick={() => dismissNotif(n.id)}>Dismiss</button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* MY REPORTS */}
          {currentView === 'my-reports' && (
            <div className="view active" style={{ padding: '24px' }}>
              <div className="page-header flex-between" style={{ marginBottom: '32px' }}>
                <div>
                  <div className="page-label" style={{ color: 'var(--cyan)', fontSize: '10px' }}>// SUBMITTED ISSUES</div>
                  <div className="page-title" style={{ fontSize: '24px' }}>MY REPORTS</div>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                  <select 
                    className="form-input form-select" 
                    style={{ width: '140px', background: 'rgba(26,48,80,0.4)', borderColor: 'var(--border)' }}
                    value={reportFilter}
                    onChange={(e) => setReportFilter(e.target.value)}
                  >
                    <option value="All Status">All Status</option>
                    <option value="UNDER REVIEW">Under Review</option>
                    <option value="RESOLVED">Resolved</option>
                    <option value="FLAGGED">Flagged</option>
                  </select>
                  <button className="btn btn-primary" onClick={() => nav('incident')} style={{ paddingLeft: '20px', paddingRight: '20px', background: 'var(--amber)', color: '#000' }}>+ NEW REPORT</button>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {userReports
                  .filter(r => reportFilter === 'All Status' || r.status === reportFilter)
                  .map(r => (
                    <div key={r.id} className="card" style={{ padding: '20px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontFamily: 'Fira Code', fontSize: '11px', color: 'var(--txt3)' }}>#{r.id}</span>
                            <span style={{ fontWeight: 600, fontSize: '14px' }}>{r.station}</span>
                          </div>
                          <div style={{ marginTop: '6px', fontSize: '11px', color: 'var(--txt3)', fontFamily: 'Fira Code' }}>
                            Type: {r.type} — Severity: {r.severity}/5 — Submitted: {r.date}
                          </div>
                          <div style={{ marginTop: '12px', fontStyle: 'italic', fontSize: '12px', color: 'var(--txt2)', opacity: 0.8 }}>
                            "{r.desc}"
                          </div>
                        </div>
                        <span className={`badge badge-${r.status === 'RESOLVED' ? 'green' : r.status === 'UNDER REVIEW' ? 'amber' : 'cyan'}`} style={{ padding: '4px 10px' }}>{r.status}</span>
                      </div>
                      <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                        <button className="btn btn-sm btn-ghost" onClick={() => nav('map')}>VIEW STATION</button>
                        <button className="btn btn-sm btn-ghost" style={{ borderColor: 'var(--cyan)', color: 'var(--cyan)' }} onClick={() => nav('mlscore')}>VIEW ML SCORE</button>
                      </div>
                    </div>
                  ))
                }
                {userReports.filter(r => reportFilter === 'All Status' || r.status === reportFilter).length === 0 && (
                  <div style={{ textAlign: 'center', padding: '40px', color: 'var(--txt3)', fontFamily: 'Fira Code', fontSize: '12px' }}>
                    No reports match the selected filter.
                  </div>
                )}
              </div>
            </div>
          )}

          {/* INCIDENT REPORT FORM (FR-29 to FR-35) */}
          {currentView === 'incident' && (
            <div className="view active" style={{ padding: '24px' }}>
              <div className="flex-between mb24">
                <div><div className="page-label" style={{ color: 'var(--red)' }}>// EMERGENCY REPORTING</div><div className="page-title" style={{ fontSize: '24px' }}>NEW INCIDENT REPORT</div></div>
                <button className="btn btn-ghost" onClick={() => nav('dashboard')}>✕ CANCEL</button>
              </div>

              <div className="grid2">
                <div className="card" style={{ padding: '24px' }}>
                  <div className="card-header"><span className="card-title">Incident Details</span></div>
                  
                  <div className="form-group">
                    <label className="form-label">Select Station *</label>
                    <select className="form-input form-select" id="inc-station" defaultValue={currentStation.id}>
                      {stations.map(s => <option key={s.id} value={s.id}>{s.name} ({s.loc})</option>)}
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Issue Category *</label>
                    <select className="form-input form-select" id="inc-type">
                      <option>Overheating</option>
                      <option>Connectivity / Offline</option>
                      <option>Physical Damage</option>
                      <option>Billing / Payment Error</option>
                      <option>Charging Cable Issue</option>
                      <option>Other</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Severity Level (1-5)</label>
                    <input type="range" className="range-slider" min="1" max="5" defaultValue="3" id="inc-severity" />
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--txt3)', marginTop: '4px', fontFamily: 'Fira Code' }}>
                      <span>LOW</span><span>MEDIUM</span><span>CRITICAL</span>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Detailed Description *</label>
                    <textarea className="form-input" id="inc-desc" rows="4" placeholder="Describe the problem in detail..." style={{ resize: 'none' }}></textarea>
                  </div>

                  <div className="form-group">
                    <label className="switch-row" style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                      <input type="checkbox" id="inc-rescore" />
                      <span style={{ fontSize: '12px', color: 'var(--txt2)' }}>Trigger ML Risk Rescore on submission</span>
                    </label>
                  </div>

                  <div style={{ marginTop: '24px', display: 'flex', gap: '12px' }}>
                    <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => {
                        const d = document.getElementById('inc-desc')?.value;
                        const rescore = document.getElementById('inc-rescore')?.checked;
                        if(!d) { addToast('Please enter a description', 'warn'); return; }
                        if(rescore) submitIncidentRescore(); else submitIncident();
                    }}>SUBMIT REPORT</button>
                    <button className="btn btn-ghost" style={{ flex: 1 }} onClick={() => addToast('Simulated image upload...', 'info')}>📸 UPLOAD IMAGE</button>
                  </div>
                </div>

                <div className="card" style={{ padding: '24px', background: 'rgba(255,100,100,0.02)', border: '1px solid rgba(255,100,100,0.1)' }}>
                  <div className="card-header"><span className="card-title" style={{ color: 'var(--red)' }}>Reporting Guidelines</span></div>
                  <ul style={{ fontSize: '12px', color: 'var(--txt2)', paddingLeft: '20px', lineHeight: '1.8' }}>
                    <li>Ensure you are reporting the correct station location.</li>
                    <li>Provide visual evidence if possible (Physical damage).</li>
                    <li>Abuse of the reporting system may lead to account flagged status.</li>
                    <li>Security-related incidents trigger immediate system-wide alerts.</li>
                  </ul>
                  <div style={{ marginTop: '24px', padding: '16px', background: 'var(--bg0)', borderRadius: '4px', border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--red)', fontWeight: 800, marginBottom: '4px' }}>EMERGENCY?</div>
                    <div style={{ fontSize: '11px', color: 'var(--txt3)' }}>If there is active fire or electrical hazard, evacuate the area and call local emergency services immediately.</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* PROFILE */}
          {currentView === 'profile' && (
            <div className="view active">
              <div className="page-header"><div className="page-label">Account</div><div className="page-title">Profile Settings</div></div>
              <div className="grid2">
                <div className="card">
                  <div className="card-header"><span className="card-title">Personal Info</span></div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '20px' }}>
                    <div style={{ width: '60px', height: '60px', borderRadius: '50%', background: 'linear-gradient(135deg,var(--cyan-d),var(--green-d))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Orbitron,sans-serif', fontSize: '20px', fontWeight: 700, color: '#fff' }}>{user.initials}</div>
                    <div>
                      <div style={{ fontSize: '16px', fontWeight: 600 }}>{user.name}</div>
                      <div className="mono" style={{ fontSize: '11px', color: 'var(--txt3)' }}>{user.email}</div>
                      <div className="badge badge-cyan" style={{ marginTop: '4px' }}>{user.role}</div>
                    </div>
                  </div>
                  <div className="form-group"><label className="form-label">Full Name</label><input className="form-input" id="prof-name" defaultValue={user.name} /></div>
                  <div className="form-group"><label className="form-label">Email</label><input className="form-input" id="prof-email" defaultValue={user.email} readOnly /></div>
                  <button className="btn btn-primary" onClick={saveProfile} disabled={profileBusy}>{profileBusy ? 'Saving...' : 'Save Changes'}</button>
                </div>

                <div className="card">
                  <div className="card-header"><span className="card-title">Security</span></div>
                  <div className="form-group"><label className="form-label">Current Password</label><input className="form-input" id="sec-current-pass" type="password" placeholder="��������" /></div>
                  <div className="form-group"><label className="form-label">New Password</label><input className="form-input" id="sec-new-pass" type="password" placeholder="��������" /></div>
                  <div className="form-group"><label className="form-label">Confirm New Password</label><input className="form-input" id="sec-confirm-pass" type="password" placeholder="��������" /></div>
                  <button className="btn btn-primary" style={{ width: '100%' }} onClick={changePassword} disabled={securityBusy}>{securityBusy ? 'Please wait...' : 'Change Password'}</button>

                  <div style={{ marginTop: '32px', borderTop: '1px solid var(--border)', paddingTop: '20px' }}>
                    <div className="page-label" style={{ color: 'var(--red)' }}>Danger Zone</div>
                    <div style={{ fontSize: '12px', color: 'var(--txt3)', marginTop: '8px' }}>Permanently delete your account and all associated data.</div>
                    <button className="btn btn-danger" style={{ marginTop: '12px' }} onClick={deleteAccount} disabled={securityBusy}>Delete Account</button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ADMIN PANEL (FR-64 to FR-80) */}
          {currentView.startsWith('admin') && (
            <div className="view active">
              <div className="page-header"><div className="page-label">System Control</div><div className="page-title">Admin Panel</div></div>
              
              <div className="admin-tab-row">
                <div className={`admin-tab ${adminSubView === 'dash' ? 'active' : ''}`} onClick={() => setAdminSubView('dash')}>Dashboard</div>
                <div className={`admin-tab ${adminSubView === 'stations' ? 'active' : ''}`} onClick={() => setAdminSubView('stations')}>Manage Stations</div>
                <div className={`admin-tab ${adminSubView === 'reports' ? 'active' : ''}`} onClick={() => setAdminSubView('reports')}>Review Reports</div>
                <div className={`admin-tab ${adminSubView === 'data' ? 'active' : ''}`} onClick={() => setAdminSubView('data')}>Update Data</div>
                <div className={`admin-tab ${adminSubView === 'users' ? 'active' : ''}`} onClick={() => setAdminSubView('users')}>Manage Users</div>
              </div>

              {adminSubView === 'dash' && (
                <div className="grid4">
                  <div className="card stat-card"><div className="stat-num cyan">247</div><div className="stat-label">Total Stations</div></div>
                  <div className="card stat-card"><div className="stat-num amber">12</div><div className="stat-label">Pending Reports</div></div>
                  <div className="card stat-card"><div className="stat-num green">1,402</div><div className="stat-label">Total Users</div></div>
                  <div className="card stat-card"><div className="stat-num red">21</div><div className="stat-label">High-Risk Stations</div></div>
                </div>
              )}

              {adminSubView === 'stations' && (
                <div className="card">
                  <div className="card-header"><span className="card-title">Manage Stations (FR-66)</span><button className="btn btn-sm btn-primary">+ ADD STATION</button></div>
                  <table className="data-table">
                    <thead><tr><th>ID</th><th>Name</th><th>Location</th><th>Risk</th><th>Action</th></tr></thead>
                    <tbody>
                      {stations.map(s => (
                        <tr key={s.id}>
                          <td className="mono">{s.id}</td>
                          <td style={{ fontWeight: 600 }}>{s.name}</td>
                          <td>{s.loc}</td>
                          <td><span className={`badge badge-${getRiskMeta(s.score).badge}`}>{getRiskMeta(s.score).shortLabel}</span></td>
                          <td style={{ display: 'flex', gap: '4px' }}>
                            <button className="btn btn-sm btn-ghost">EDIT</button>
                            <button className="btn btn-sm btn-ghost text-red" onClick={() => window.confirm('Delete station?') && addToast('success', 'Station deleted')}>DEL</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div style={{ marginTop: '16px', textAlign: 'right' }}><button className="btn btn-sm btn-ghost">📥 EXPORT CSV (FR-71)</button></div>
                </div>
              )}

              {adminSubView === 'reports' && (
                <div className="card">
                  <div className="card-header"><span className="card-title">Review Reports (FR-72)</span></div>
                  <table className="data-table">
                    <thead><tr><th>User</th><th>Station</th><th>Issue</th><th>Status</th><th>Action</th></tr></thead>
                    <tbody>
                      {userReports.map(r => (
                        <tr key={r.id}>
                          <td>{user.name}</td>
                          <td>{r.station}</td>
                          <td>{r.type}</td>
                          <td><span className={`badge badge-${r.status === 'RESOLVED' ? 'green' : r.status === 'UNDER REVIEW' ? 'amber' : 'cyan'}`}>{r.status}</span></td>
                          <td><button className="btn btn-sm btn-primary" onClick={() => addToast('Processing report...', 'info')}>REVIEW</button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {adminSubView === 'data' && (
                <div className="grid2">
                  <div className="card">
                    <div className="card-header"><span className="card-title">Update Station Data (FR-76)</span></div>
                    <div className="form-group">
                      <label className="form-label">Select Station</label>
                      <select className="form-input form-select">
                        {stations.map(s => <option key={s.id}>{s.name}</option>)}
                      </select>
                    </div>
                    <div className="form-group"><label className="form-label">Temperature (°C)</label><input type="number" className="form-input" defaultValue="42" /></div>
                    <div className="form-group"><label className="form-label">Fault Count</label><input type="number" className="form-input" defaultValue="2" /></div>
                    <button className="btn btn-primary" style={{ width: '100%' }}>SAVE & RESCORE (FR-77)</button>
                  </div>
                </div>
              )}

              {adminSubView === 'users' && (
                <div className="card">
                  <div className="card-header"><span className="card-title">Manage Users (FR-78)</span></div>
                  <table className="data-table">
                    <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Action</th></tr></thead>
                    <tbody>
                      <tr><td>Kavindu Perera</td><td>kavindu@chargesafe.lk</td><td>ADMIN</td><td><span className="badge badge-green">ACTIVE</span></td><td><button className="btn btn-sm btn-ghost">DEACTIVATE</button></td></tr>
                      <tr><td>John Doe</td><td>john@example.com</td><td>USER</td><td><span className="badge badge-green">ACTIVE</span></td><td><button className="btn btn-sm btn-ghost">EDIT</button></td></tr>
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* SETTINGS VIEW */}
          {currentView === 'settings' && (
            <div className="view active">
              <div className="page-header"><div className="page-label">System</div><div className="page-title">Settings</div></div>
              
              <div className="settings-grid">
                {/* Left Column */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                  <div className="card">
                    <div className="card-header"><span className="card-title">Notification Preferences</span></div>
                    <div className="setting-item">
                      <div className="setting-info">
                        <div className="setting-label">Push Notifications</div>
                        <div className="setting-desc">Real-time alerts for critical events</div>
                      </div>
                      <label className="switch">
                        <input type="checkbox" checked={settings.pushNotifications} onChange={(e) => updateSetting('pushNotifications', e.target.checked)} />
                        <span className="slider-toggle"></span>
                      </label>
                    </div>
                    <div className="form-group" style={{ marginTop: '20px' }}>
                      <label className="form-label">High-Risk Alert Threshold</label>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                        <input type="range" className="range-slider" min="0" max="100" value={settings.alertThreshold} onChange={(e) => updateSetting('alertThreshold', parseInt(e.target.value))} />
                        <div className="threshold-val">{settings.alertThreshold}</div>
                      </div>
                      <div className="setting-desc">Alert when a station risk score rises above this value</div>
                    </div>
                  </div>

                  <div className="card">
                    <div className="card-header"><span className="card-title">Risk Thresholds</span></div>
                    <div className="form-group">
                      <label className="form-label">Low Risk Threshold (Default: 30)</label>
                      <input type="number" className="form-input" value={settings.safeThreshold} onChange={(e) => updateSetting('safeThreshold', parseInt(e.target.value))} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Medium Risk Threshold (Default: 70)</label>
                      <input type="number" className="form-input" value={settings.warningThreshold} onChange={(e) => updateSetting('warningThreshold', parseInt(e.target.value))} />
                    </div>
                    <div style={{ marginTop: '12px', fontSize: '11px', fontFamily: 'Fira Code, monospace' }}>
                      <div className="text-green">0-30 — LOW RISK</div>
                      <div className="text-amber">31-70 — MEDIUM RISK</div>
                      <div className="text-red">71-100 — HIGH RISK</div>
                    </div>
                    <button className="btn btn-primary" style={{ width: '100%', marginTop: '24px' }} onClick={saveSettings}>Save Settings</button>
                  </div>
                </div>

                {/* Right Column */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                  <div className="card">
                    <div className="card-header"><span className="card-title">Display & Units</span></div>
                    <div className="form-group">
                      <label className="form-label">Units System</label>
                      <select className="form-input form-select" value={settings.unitsSystem} onChange={(e) => updateSetting('unitsSystem', e.target.value)}>
                        <option>Metric (°C, km)</option>
                        <option>Imperial (°F, mi)</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Language</label>
                      <select className="form-input form-select" value={settings.language} onChange={(e) => updateSetting('language', e.target.value)}>
                        <option>English</option>
                        <option>Sinhala</option>
                        <option>Tamil</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Map Pin Colour Mode</label>
                      <select className="form-input form-select" value={settings.mapPinColorMode} onChange={(e) => updateSetting('mapPinColorMode', e.target.value)}>
                        <option>Risk Score (Green/Amber/Red)</option>
                        <option>Occupancy (Blue/Grey)</option>
                      </select>
                    </div>
                  </div>

                  <div className="card">
                    <div className="card-header"><span className="card-title">About</span></div>
                    <table className="data-table">
                      <tbody>
                        <tr><td>Version</td><td className="mono">ChargeSafe SL v1.0.0</td></tr>
                        <tr><td>Group</td><td className="mono">Group 28 - Week 05</td></tr>
                        <tr><td>ML Model</td><td className="mono">Risk Scorer v2.3</td></tr>
                        <tr><td>Cyber Engine</td><td className="mono">IEC 62443 + OWASP IoT</td></tr>
                        <tr><td>AI Chatbot</td><td className="mono">Gemini</td></tr>
                        <tr><td>Last Sync</td><td className="mono">{lastSync}</td></tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

        </div>{/* /content */}
      </div>{/* /main */}

      <div id="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>
            <span>{t.type === 'success' ? '✓' : t.type === 'warn' ? '⚠' : t.type === 'error' ? '✕' : 'ℹ'}</span>
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
      {splashOverlay}
    </div>
  );
}

export default App;








