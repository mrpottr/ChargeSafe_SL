import React, { useState, useEffect, useRef, useMemo } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";
import CyberProfile from "./components/CyberProfile";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";
const REGISTER_MFA_SETUP_KEY = "chargesafe_register_mfa_setup";
const LOW_RISK_MAX = 30;
const MEDIUM_RISK_MAX = 70;

// Leaflet's default asset lookup does not play nicely with this React setup, so
// the icon paths are wired manually once at module load time.
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

const seedStations = [];

const createPinIcon = (color) => {
  // The marker is rendered from inline SVG so every risk color can reuse the
  // same shape without depending on a separate generated asset file.
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
  colombo: "No cached data is available for that station right now.",
  safe: "Use the live station list to find currently lower-risk stations.",
  critical: "Use the live station list to find currently higher-risk stations.",
};

const riskOfflineResponses = {
  default: "I'm in offline mode. Cached data: The ChargeSafe SL network monitors 247 stations across Sri Lanka with real-time ML risk scoring. Low risk is 0-30, medium risk is 31-70, and high risk is 71-100.",
  colombo: "No cached data is available for that station right now.",
  safe: "Lower-risk stations are the safest choices. Look for stations closer to the 0-30 range because a lower risk score means a safer station.",
  critical: "High-risk stations are the ones to avoid first. A score in the 71-100 range usually points to overheating, instability, overload, or compatibility concerns.",
};

const seedStationExtrasByName = Object.fromEntries(
  seedStations.map((station) => [station.name.toLowerCase(), station])
);

const mapBackendStation = (station) => {
  const seed = seedStationExtrasByName[(station?.name || "").toLowerCase()] || {};
  const score = Number(station?.risk_score ?? 0);
  const locationParts = [station?.city, station?.address].filter(Boolean);

  return {
    id: station?.id ?? seed.id ?? crypto.randomUUID(),
    name: station?.name || seed.name || "Unknown Station",
    loc: locationParts.join(" - ") || seed.loc || "Sri Lanka",
    pos: [Number(station?.latitude ?? seed?.pos?.[0] ?? 7.8731), Number(station?.longitude ?? seed?.pos?.[1] ?? 80.7718)],
    score,
    faults: Number(station?.fault_count ?? seed.faults ?? 0),
    fw: station?.firmware_version || seed.fw || "Unknown",
    cyber: station?.cyber_risk_level || seed.cyber || "UNKNOWN",
    power: station?.power_status || seed.power || "Unknown",
    tempHistory: seed.tempHistory || [30, 32, 35, 34, 33, 36, 35],
    scoreHistory: seed.scoreHistory || [],
    operator: station?.operator || "Unknown",
    connectorTypes: station?.connector_types || "Unknown",
    chargingPowerKw: station?.charging_power_kw ?? null,
    status: station?.status || "unknown",
    color: station?.color_hex || station?.color || getRiskColor(score),
    riskStatus: station?.risk_status || getRiskMeta(score).label,
    lastScoredAt: station?.last_scored_at || null,
  };
};

const formatNotificationTime = (value) => {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
};

const mapBackendNotification = (notification) => ({
  id: notification?.id,
  icon: notification?.icon || (notification?.notification_type === 'danger' ? '🚨' : notification?.notification_type === 'warn' ? '⚠️' : notification?.notification_type === 'success' ? '✅' : 'ℹ'),
  title: notification?.title || 'Notification',
  msg: notification?.message || '',
  time: formatNotificationTime(notification?.created_at),
  unread: !notification?.is_read,
  type: notification?.notification_type || 'info',
});

const buildOfflineChatResponse = (message, stations) => {
  const lowered = message.toLowerCase();
  const matchedStation = stations.find((station) => lowered.includes(station.name.toLowerCase()));
  if (matchedStation) {
    const meta = getRiskMeta(matchedStation.score);
    return `${matchedStation.name} is currently at ${matchedStation.score}/100, which is ${meta.label.toLowerCase()}. This usually means ${meta.key === 'high' ? 'there may be overheating, instability, overload, or compatibility issues.' : meta.key === 'medium' ? 'there are caution signs worth monitoring before charging for long periods.' : 'the station looks relatively stable right now.'}`;
  }

  if (lowered.includes('lowest') || lowered.includes('safe') || lowered.includes('low risk')) {
    const safest = [...stations].sort((a, b) => a.score - b.score).slice(0, 3);
    return `Using cached station data, the lowest-risk stations right now are ${safest.map((station) => `${station.name} (${station.score}/100)`).join(', ')}.`;
  }

  if (lowered.includes('highest') || lowered.includes('critical') || lowered.includes('high risk') || lowered.includes('danger')) {
    const riskiest = [...stations].sort((a, b) => b.score - a.score).slice(0, 3);
    return `Using cached station data, the highest-risk stations right now are ${riskiest.map((station) => `${station.name} (${station.score}/100)`).join(', ')}.`;
  }

  return "I'm in offline mode, but I can still answer from cached station data. Ask about a station by name, or ask which stations are highest or lowest risk right now.";
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
    mfaEnabled: backendUser?.mfa_enabled ?? false,
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

const PASSWORD_POLICY_MESSAGE = "Password must be at least 8 characters long and include uppercase, lowercase, number, and symbol";

const getPasswordPolicyError = (password) => {
  if (
    password.length < 8 ||
    !/[A-Z]/.test(password) ||
    !/[a-z]/.test(password) ||
    !/\d/.test(password) ||
    !/[^A-Za-z0-9]/.test(password)
  ) {
    return PASSWORD_POLICY_MESSAGE;
  }

  return "";
};

const saveRegistrationMfaSetup = (payload) => {
  if (!payload?.setup_token) return;

  sessionStorage.setItem(
    REGISTER_MFA_SETUP_KEY,
    JSON.stringify({
      email: payload.email || "",
      setup_token: payload.setup_token,
      secret: payload.secret || "",
      otp_auth_url: payload.otp_auth_url || "",
      qr_code_data_url: payload.qr_code_data_url || "",
      message: payload.message || "",
    })
  );
};

const loadRegistrationMfaSetup = () => {
  try {
    const raw = sessionStorage.getItem(REGISTER_MFA_SETUP_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw);
    if (!parsed?.setup_token || !parsed?.qr_code_data_url) {
      sessionStorage.removeItem(REGISTER_MFA_SETUP_KEY);
      return null;
    }

    return parsed;
  } catch {
    sessionStorage.removeItem(REGISTER_MFA_SETUP_KEY);
    return null;
  }
};

const clearRegistrationMfaSetup = () => {
  sessionStorage.removeItem(REGISTER_MFA_SETUP_KEY);
};

const normalizeOtpCode = (value = "") => value.replace(/\D/g, "").slice(0, 6);

const getAuthParamsFromLocation = () => {
  const searchParams = new URLSearchParams(window.location.search);
  const auth = searchParams.get("auth");
  const email = searchParams.get("email") || "";
  const token = searchParams.get("token") || "";
  if (auth || email || token) {
    return { auth, email, token };
  }

  const hash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : window.location.hash;
  if (!hash) {
    return { auth: null, email: "", token: "" };
  }

  const hashQuery = hash.includes("?") ? hash.slice(hash.indexOf("?")) : hash.startsWith("?") ? hash : "";
  const hashParams = new URLSearchParams(hashQuery);
  return {
    auth: hashParams.get("auth"),
    email: hashParams.get("email") || "",
    token: hashParams.get("token") || "",
  };
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
  const [mfaBusy, setMfaBusy] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);
  const [securityBusy, setSecurityBusy] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [stationCyberScore, setStationCyberScore] = useState(null);
  const [showSplash, setShowSplash] = useState(true);
  // Dashboard is the default authenticated landing view because it gives the
  // quickest snapshot of risk, alerts, and station status in one place.
  const [currentView, setCurrentView] = useState("dashboard");
  const [authView, setAuthView] = useState("login");
  const [pendingAdminLogin, setPendingAdminLogin] = useState(false);
  const [pendingMfaToken, setPendingMfaToken] = useState("");
  const [pendingMfaEmail, setPendingMfaEmail] = useState("");
  const [passwordResetContext, setPasswordResetContext] = useState({ email: "", token: "" });
  const [registrationEmail, setRegistrationEmail] = useState("");
  const [pendingRegistrationMfaToken, setPendingRegistrationMfaToken] = useState("");
  const [pendingRegistrationMfaEmail, setPendingRegistrationMfaEmail] = useState("");
  const [registrationMfaSetup, setRegistrationMfaSetup] = useState(null);
  const [mfaSetup, setMfaSetup] = useState(null);
  const [stations, setStations] = useState(seedStations);
  const [currentStation, setCurrentStation] = useState(seedStations[0]);
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
    { id: 'notif-1', icon: '🚨', title: 'Risk Alert — DEMO Colombo High Risk 01', msg: 'Station risk score rose to 88/100. Authentication failure detected.', time: '2025-06-01 09:14', unread: true, type: 'danger' },
    { id: 'notif-2', icon: '⚠️', title: 'Warning — DEMO Kandy High Risk 02 Firmware', msg: 'Firmware version 1.1.0 is out of date. Update recommended.', time: '2025-06-01 08:02', unread: true, type: 'warn' },
    { id: 'notif-3', icon: '📋', title: 'Feedback #102 Status Update', msg: 'Your overheating feedback for Colpetty station is now under review by admin.', time: '2025-05-31 17:30', unread: true, type: 'info' },
    { id: 'notif-4', icon: '✅', title: 'Feedback #98 Resolved', msg: 'Your billing error feedback for Galle station has been resolved.', time: '2025-05-29 12:00', unread: false, type: 'success' },
  ]);
  const [mapFilter, setMapFilter] = useState("all");
  const [mapSearch, setMapSearch] = useState("");
  const [mlScore, setMlScore] = useState(82);
  const [scoreUpdateFlash, setScoreUpdateFlash] = useState(null);

  // Feedback-related state is grouped together because those values travel as a
  // single workflow between the reports list and the submission form.
  const [reportFilter, setReportFilter] = useState("All Status");
  const [userReports, setUserReports] = useState([
    { id: 102, station: 'DEMO Colombo High Risk 01 — Colombo', type: 'Overheating', severity: 3, date: '2025-06-01', desc: 'Unit was unusually hot to touch after 20 minutes of charging.', status: 'PUBLISHED' },
    { id: 98, station: 'DEMO Galle Medium Risk 01 — Galle', type: 'Billing Error', severity: 2, date: '2025-05-28', desc: 'Was charged twice for a single session.', status: 'RESOLVED' },
    { id: 91, station: 'DEMO Kandy High Risk 02 — Kandy', type: 'Network Outage', severity: 4, date: '2025-05-20', desc: 'Station completely offline for 3 hours, no error displayed.', status: 'FLAGGED' },
  ]);

  // Settings state mirrors the backend preference payload so local edits can be
  // reflected immediately before or after persistence.
  const [settings, setSettings] = useState({
    pushNotifications: true,
    alertThreshold: 70,
    unitsSystem: "Metric (°C, km)",
    language: "English",
    mapPinColorMode: "#2ecc71 / #f1c40f / #e74c3c",
    safeThreshold: 30,
    warningThreshold: 70
  });
  const [incidentStationId, setIncidentStationId] = useState("");
  const [incidentType, setIncidentType] = useState("Overheating");
  const [incidentSeverity, setIncidentSeverity] = useState(3);
  const [incidentDescription, setIncidentDescription] = useState("");

  const chatMessagesEndRef = useRef(null);
  const historyInitializedRef = useRef(false);
  const splashTimeoutRef = useRef(null);
  const stationStats = useMemo(() => {
    const low = stations.filter((station) => station.score <= LOW_RISK_MAX).length;
    const medium = stations.filter((station) => station.score > LOW_RISK_MAX && station.score <= MEDIUM_RISK_MAX).length;
    const high = stations.filter((station) => station.score > MEDIUM_RISK_MAX).length;
    return {
      total: stations.length,
      low,
      medium,
      high,
    };
  }, [stations]);

  const adminDashboardRiskSegments = useMemo(() => {
    const total = Math.max(stationStats.total, 1);
    return [
      {
        label: "Safe",
        count: stationStats.low,
        width: `${(stationStats.low / total) * 100}%`,
        color: "var(--green)",
        glow: "rgba(0,230,118,0.16)",
      },
      {
        label: "Warning",
        count: stationStats.medium,
        width: `${(stationStats.medium / total) * 100}%`,
        color: "var(--amber)",
        glow: "rgba(255,179,0,0.16)",
      },
      {
        label: "High Risk",
        count: stationStats.high,
        width: `${(stationStats.high / total) * 100}%`,
        color: "var(--red)",
        glow: "rgba(255,68,68,0.16)",
      },
    ];
  }, [stationStats]);

  const adminDashboardReportMetrics = useMemo(() => {
    const total = Math.max(userReports.length, 1);
    const resolved = userReports.filter((report) => report.status === "RESOLVED").length;
    const published = userReports.filter((report) => report.status === "PUBLISHED").length;
    const flagged = userReports.filter((report) => report.status === "FLAGGED").length;
    const averageSeverity = userReports.length
      ? (userReports.reduce((sum, report) => sum + Number(report.severity || 0), 0) / userReports.length).toFixed(1)
      : "0.0";

    return {
      resolutionRate: `${Math.round((resolved / total) * 100)}%`,
      underReview: published,
      escalated: flagged,
      averageSeverity,
    };
  }, [userReports]);

  const adminDashboardUnreadCount = notifications.filter((notification) => notification.unread).length;

  const adminDashboardSystemStatus = useMemo(() => ([
    {
      label: "API Gateway",
      value: "ONLINE",
      badge: "green",
      meta: "Authentication and station endpoints responding normally.",
    },
    {
      label: "Risk Engine",
      value: "HEALTHY",
      badge: "cyan",
      meta: `${stationStats.total} stations currently available for scoring.`,
    },
    {
      label: "Notification Bus",
      value: settings.pushNotifications ? "ENABLED" : "PAUSED",
      badge: settings.pushNotifications ? "amber" : "red",
      meta: `${adminDashboardUnreadCount} unread notifications awaiting admin attention.`,
    },
    {
      label: "Data Sync",
      value: "SYNCED",
      badge: "green",
      meta: `Last successful refresh ${lastSync}.`,
    },
  ]), [adminDashboardUnreadCount, lastSync, settings.pushNotifications, stationStats.total]);

  const adminDashboardActivity = useMemo(() => {
    const activityFromNotifications = notifications.slice(0, 3).map((notification) => ({
      title: notification.title,
      detail: notification.msg,
      time: notification.time,
      color: notification.type === "danger" ? "var(--red)" : notification.type === "warn" ? "var(--amber)" : "var(--cyan)",
    }));

    return [
      {
        title: "Station fleet sync completed",
        detail: `${stationStats.total} charging stations refreshed and published to the admin workspace.`,
        time: lastSync,
        color: "var(--cyan)",
      },
      ...activityFromNotifications,
    ].slice(0, 4);
  }, [lastSync, notifications, stationStats.total]);

  const adminDashboardSecuritySnapshot = useMemo(() => ([
    {
      label: "Admin MFA",
      value: user?.mfaEnabled ? "ENABLED" : "ACTION NEEDED",
      badge: user?.mfaEnabled ? "green" : "amber",
      meta: "Current administrator account protection status.",
    },
    {
      label: "Critical Alerts",
      value: String(notifications.filter((notification) => notification.type === "danger" && notification.unread).length),
      badge: "red",
      meta: "Unread high-priority alerts in the security pipeline.",
    },
    {
      label: "Push Escalation",
      value: settings.pushNotifications ? "ACTIVE" : "DISABLED",
      badge: settings.pushNotifications ? "cyan" : "amber",
      meta: "Escalation channel used for urgent operational events.",
    },
    {
      label: "Failed Logins 24H",
      value: "14",
      badge: "amber",
      meta: "Suspicious or rejected sign-in attempts across the portal.",
    },
  ]), [notifications, settings.pushNotifications, user?.mfaEnabled]);

  const nav = (viewId) => {
    setCurrentView(viewId);
    // Navigation updates the browser history too, which keeps the back button
    // useful even though the interface behaves like a single-page dashboard.
    window.history.pushState({ view: viewId }, '', `?view=${viewId}`);
  };

  const goBack = () => {
    window.history.back();
  };

  useEffect(() => {
    // This listener keeps SPA navigation and auth entry links from fighting each
    // other when the user moves backward through browser history.
    const { auth } = getAuthParamsFromLocation();
    const isAuthFlow = auth === "verify-email" || auth === "reset";

    if (!historyInitializedRef.current) {
      // Initial auth and recovery URLs are preserved so onboarding flows can
      // complete without the dashboard immediately rewriting the address bar.
      if (!isAuthFlow) {
        window.history.replaceState({ view: 'dashboard' }, '', `?view=dashboard`);
      }
      historyInitializedRef.current = true;
    }

    const handlePopState = (event) => {
      const currentParams = new URLSearchParams(window.location.search);
      const currentAuth = currentParams.get("auth");
      if (currentAuth === "verify-email" || currentAuth === "reset") {
        return;
      }

      if (event.state && event.state.view) {
        setCurrentView(event.state.view);
      } else {
        // Falling back to the dashboard avoids stranding the user on a blank
        // state if the browser history stack runs out inside the app shell.
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
      const { auth } = getAuthParamsFromLocation();
      const storedRegistrationMfa = loadRegistrationMfaSetup();
      if (auth === "verify-email" || auth === "reset" || storedRegistrationMfa) {
        return;
      }

      const accessToken = localStorage.getItem('chargesafe_auth_token');
      const refreshToken = localStorage.getItem('chargesafe_refresh_token');

      // If there is no stored auth state at all, the app simply leaves the user
      // in the unauthenticated flow without making unnecessary requests.
      if (!accessToken && !refreshToken) return;

      try {
        let token = accessToken;

        // A refresh-only restore path lets the session survive a stale or
        // missing access token after the page has been reopened.
        if (!token && refreshToken) {
          const refreshResp = await fetch(`${API_BASE_URL}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });
          const refreshData = await refreshResp.json().catch(() => ({}));
          if (!refreshResp.ok || !refreshData.access_token) {
            localStorage.removeItem('chargesafe_auth_token');
            localStorage.removeItem('chargesafe_refresh_token');
            setUser(null);
            return;
          }
          localStorage.setItem('chargesafe_auth_token', refreshData.access_token);
          if (refreshData.refresh_token) {
            localStorage.setItem('chargesafe_refresh_token', refreshData.refresh_token);
          }
          token = refreshData.access_token;
        }

        const response = await fetch(`${API_BASE_URL}/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!response.ok) {
          // A rejected access token gets one silent refresh attempt before the
          // app gives up and returns the user to login.
          if (response.status === 401 && refreshToken) {
            const refreshResp = await fetch(`${API_BASE_URL}/auth/refresh`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ refresh_token: refreshToken }),
            });
            const refreshData = await refreshResp.json().catch(() => ({}));
            if (!refreshResp.ok || !refreshData.access_token) {
              localStorage.removeItem('chargesafe_auth_token');
              localStorage.removeItem('chargesafe_refresh_token');
              setUser(null);
              return;
            }
            localStorage.setItem('chargesafe_auth_token', refreshData.access_token);
            if (refreshData.refresh_token) {
              localStorage.setItem('chargesafe_refresh_token', refreshData.refresh_token);
            }
            const retryResp = await fetch(`${API_BASE_URL}/me`, {
              headers: { Authorization: `Bearer ${refreshData.access_token}` },
            });
            if (!retryResp.ok) { setUser(null); return; }
            const retryData = await retryResp.json();
            setUser(mapBackendUser(retryData));
            return;
          }
          setUser(null);
          return;
        }

        const data = await response.json();
        setUser(mapBackendUser(data));
      } catch {
        setUser(null);
      }
    };

    restoreSession();
  }, []);

  useEffect(() => {
    const bootstrapAuthFlow = async () => {
      const { auth, email, token } = getAuthParamsFromLocation();
      const storedRegistrationMfa = loadRegistrationMfaSetup();

      if (auth === "reset") {
        setUser(null);
        clearRegistrationMfaSetup();
        setPendingRegistrationMfaToken("");
        setPendingRegistrationMfaEmail("");
        setRegistrationMfaSetup(null);
        setPasswordResetContext({ email, token });
        setAuthView("reset");
        return;
      }

      if (!auth && storedRegistrationMfa) {
        setUser(null);
        setPendingRegistrationMfaToken(storedRegistrationMfa.setup_token || "");
        setPendingRegistrationMfaEmail(storedRegistrationMfa.email || "");
        setRegistrationMfaSetup(storedRegistrationMfa);
        setAuthView("register-mfa");
        return;
      }

      if (auth === "verify-email" && token) {
        setUser(null);
        setAuthView('register-mfa');
        setAuthBusy(true);
        try {
          const response = await fetch(`${API_BASE_URL}/auth/verify-email`, {
            method: 'POST',
            credentials: 'include',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ token }),
          });

          const data = await response.json().catch(() => ({}));
          if (!response.ok) {
            throw new Error(data.detail || 'Unable to verify email');
          }

          setPendingRegistrationMfaToken(data.setup_token || '');
          setPendingRegistrationMfaEmail(data.email || '');
          setRegistrationMfaSetup(data);
          saveRegistrationMfaSetup(data);
          setAuthView('register-mfa');
          addToast(data.message || 'Email verified. Continue with Microsoft Authenticator setup.', 'success');
          window.history.replaceState({}, '', window.location.pathname);
        } catch (error) {
          clearRegistrationMfaSetup();
          addToast(error.message || 'Unable to verify email', 'error');
          setAuthView('login');
        } finally {
          setAuthBusy(false);
        }
      }
    };

    bootstrapAuthFlow();
  }, []);

  useEffect(() => {
    const loadStations = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/stations?limit=100`);
        if (!response.ok) {
          throw new Error("Unable to load stations");
        }

        const data = await response.json();
        if (!Array.isArray(data) || data.length === 0) {
          return;
        }

        const mappedStations = data
          .map(mapBackendStation)
          .filter((station) => Number.isFinite(station.pos[0]) && Number.isFinite(station.pos[1]));

        if (!mappedStations.length) {
          return;
        }

        setStations(mappedStations);
        setCurrentStation((previousStation) => {
          const matchingStation = mappedStations.find((station) => station.id === previousStation?.id);
          return matchingStation || mappedStations[0];
        });
        setLastSync(new Date().toLocaleTimeString());
      } catch (error) {
        console.error("Failed to load stations from backend:", error);
      }
    };

    loadStations();
  }, []);

  useEffect(() => {
    if (chatMessagesEndRef.current) {
      chatMessagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isTyping]);

  useEffect(() => {
    if (currentStation?.score != null) {
      setMlScore(currentStation.score);
    }
  }, [currentStation]);

  useEffect(() => {
    if (currentStation?.id) {
      setIncidentStationId((previousId) => previousId || String(currentStation.id));
    }
  }, [currentStation?.id]);

  useEffect(() => {
    if (!scoreUpdateFlash) return undefined;

    const timeout = setTimeout(() => {
      setScoreUpdateFlash(null);
    }, 2200);

    return () => clearTimeout(timeout);
  }, [scoreUpdateFlash]);

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
    let token = localStorage.getItem('chargesafe_auth_token');
    const refreshToken = localStorage.getItem('chargesafe_refresh_token');

    const makeRequest = (t) => fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(options.headers || {}),
        ...(t ? { Authorization: `Bearer ${t}` } : {}),
        ...((options.body && !options.headers?.['Content-Type']) ? { 'Content-Type': 'application/json' } : {}),
      },
    });

    let response = await makeRequest(token);

    // Authenticated API calls get one silent refresh attempt so short-lived
    // access tokens do not interrupt normal dashboard activity.
    if (response.status === 401 && refreshToken) {
      try {
        const refreshResp = await fetch(`${API_BASE_URL}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        const refreshData = await refreshResp.json().catch(() => ({}));
        if (refreshResp.ok && refreshData.access_token) {
          localStorage.setItem('chargesafe_auth_token', refreshData.access_token);
          if (refreshData.refresh_token) {
            localStorage.setItem('chargesafe_refresh_token', refreshData.refresh_token);
          }
          token = refreshData.access_token;
          response = await makeRequest(token);
        }
      } catch {
        // Any refresh failure falls through to the normal unauthorized handling
        // path so session cleanup stays centralized in one place.
      }
    }

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem('chargesafe_auth_token');
        localStorage.removeItem('chargesafe_refresh_token');
        setUser(null);
        setAuthView('login');
      }
      throw new Error(data.detail || 'Request failed');
    }

    return data;
  };

  const refreshNotifications = async () => {
    if (!user) {
      setNotifications([]);
      return [];
    }

    const data = await authApi('/notifications?limit=50');
    const mapped = Array.isArray(data) ? data.map(mapBackendNotification) : [];
    setNotifications(mapped);
    return mapped;
  };

  const fetchStationHistory = async (stationId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/stations/${stationId}/score-history?days=30`);
      if (!response.ok) {
        throw new Error('Unable to load score history');
      }
      const data = await response.json();
      return Array.isArray(data) ? data : [];
    } catch (error) {
      console.error('Failed to load station score history:', error);
      return [];
    }
  };

  useEffect(() => {
    // The detail view reloads the cyber score when the selected station changes
    // so the assessment panel always matches the current station context.
    if (!currentStation?.id || !user) {
      setStationCyberScore(null);
      return undefined;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const data = await authApi(`/stations/${currentStation.id}/cyber-score`);
        if (!cancelled) setStationCyberScore(data);
      } catch {
        if (!cancelled) setStationCyberScore(null);
      }
    };
    load();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStation?.id, user]);

  useEffect(() => {
    if (!user) {
      setNotifications([]);
      return undefined;
    }

    let cancelled = false;

    const loadNotifications = async () => {
      try {
        const data = await authApi('/notifications?limit=50');
        if (!cancelled) {
          setNotifications(Array.isArray(data) ? data.map(mapBackendNotification) : []);
        }
      } catch (error) {
        if (!cancelled) {
          console.error('Failed to load notifications:', error);
          setNotifications([]);
        }
      }
    };

    loadNotifications();
    const intervalId = setInterval(loadNotifications, 30000);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  useEffect(() => {
    if (user && currentView === 'notifications') {
      refreshNotifications().catch((error) => {
        console.error('Failed to refresh notifications:', error);
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentView, user]);

  const refreshStationRiskState = async (stationId) => {
    const [stationResponse, scoreHistory] = await Promise.all([
      fetch(`${API_BASE_URL}/stations/${stationId}`),
      fetchStationHistory(stationId),
    ]);

    if (!stationResponse.ok) {
      throw new Error('Unable to refresh station risk score');
    }

    const refreshedStation = mapBackendStation(await stationResponse.json());
    const hydratedStation = {
      ...refreshedStation,
      scoreHistory: scoreHistory.length ? scoreHistory : refreshedStation.scoreHistory,
    };

    setStations((previousStations) =>
      previousStations.map((station) => (String(station.id) === String(hydratedStation.id) ? hydratedStation : station))
    );
    setCurrentStation((previousStation) => (
      String(previousStation?.id) === String(hydratedStation.id) ? hydratedStation : previousStation
    ));
    setMlScore(hydratedStation.score);
    setLastSync(new Date().toLocaleTimeString());

    return hydratedStation;
  };

  const doLogin = async (requireAdmin = false) => {
    const email = document.getElementById('login-email')?.value?.trim() || '';
    const password = document.getElementById('login-pass')?.value || '';

    if (!email || !password) {
      addToast('Enter email and password to continue', 'warn');
      return;
    }

    setPendingAdminLogin(requireAdmin);
    setAuthBusy(true);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.detail || 'Login failed');
      }

      if (data.mfa_required) {
        setPendingMfaToken(data.mfa_token || '');
        setPendingMfaEmail(email);
        setAuthView('mfa');
        addToast('Enter the current 6-digit code from Microsoft Authenticator', 'info');
        return;
      }

      if (data.mfa_setup_required) {
      setPendingRegistrationMfaToken(data.mfa_setup_token || '');
      setPendingRegistrationMfaEmail(email);

        const setupResponse = await fetch(`${API_BASE_URL}/auth/mfa/setup-registration`, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            setup_token: data.mfa_setup_token,
          }),
        });

        const setupData = await setupResponse.json().catch(() => ({}));
        if (!setupResponse.ok) {
          throw new Error(setupData.detail || 'Unable to start Microsoft Authenticator setup');
        }

        setRegistrationMfaSetup(setupData);
        saveRegistrationMfaSetup(setupData);
        setAuthView('register-mfa');
        addToast(setupData.message || 'Complete Microsoft Authenticator setup to finish logging in.', 'info');
        return;
      }

      if (requireAdmin && data.user?.role !== 'admin') {
        setPendingAdminLogin(false);
        throw new Error('This account does not have admin access');
      }

      setPendingAdminLogin(false);
      playSplash(1700);
      if (data.access_token) localStorage.setItem('chargesafe_auth_token', data.access_token);
      if (data.refresh_token) localStorage.setItem('chargesafe_refresh_token', data.refresh_token);
      setUser(mapBackendUser(data.user));
      nav('dashboard');
      setLastSync(new Date().toLocaleTimeString());
      addToast('Login successful', 'success');
    } catch (error) {
      setPendingAdminLogin(false);
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

    const passwordPolicyError = getPasswordPolicyError(password);
    if (passwordPolicyError) {
      addToast(passwordPolicyError, 'warn');
      return;
    }

    setAuthBusy(true);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/register`, {
        method: 'POST',
        credentials: 'include',
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

      setRegistrationEmail(email);
      addToast(data.message || 'Verification email sent. Check your inbox to continue.', 'success');
      setAuthView('verify-email-sent');
    } catch (error) {
      addToast(error.message || 'Unable to create account', 'error');
    } finally {
      setAuthBusy(false);
    }
  };

  const requestPasswordReset = async () => {
    const email = passwordResetContext.email || document.getElementById('login-email')?.value?.trim() || '';
    const code = normalizeOtpCode(document.getElementById('forgot-mfa-code')?.value || '');

    if (!email) {
      addToast('Enter your email address on the login form first', 'warn');
      return;
    }

    if (!code) {
      addToast('Enter the current Microsoft Authenticator code to continue', 'warn');
      return;
    }

    setAuthBusy(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/forgot-password`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, code }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Unable to verify authenticator code');
      }

      addToast(data.message || 'Password reset link sent', 'success');
      setPasswordResetContext({ email: data.email || email, token: '' });
      setAuthView('reset-email-sent');
    } catch (error) {
      addToast(error.message || 'Unable to verify authenticator code', 'error');
    } finally {
      setAuthBusy(false);
    }
  };

  const submitMfaLogin = async () => {
    const code = normalizeOtpCode(document.getElementById('mfa-code')?.value || '');
    if (!pendingMfaToken || !code) {
      addToast('Enter the authenticator code to continue', 'warn');
      return;
    }

    setAuthBusy(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/mfa/login-verify`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          mfa_token: pendingMfaToken,
          code,
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'MFA verification failed');
      }

      if (pendingAdminLogin && data.user?.role !== 'admin') {
        setPendingAdminLogin(false);
        setPendingMfaToken('');
        setPendingMfaEmail('');
        setAuthView('login');
        throw new Error('This account does not have admin access');
      }

      setPendingAdminLogin(false);
      setPendingMfaToken('');
      setPendingMfaEmail('');
      playSplash(1700);
      if (data.access_token) localStorage.setItem('chargesafe_auth_token', data.access_token);
      if (data.refresh_token) localStorage.setItem('chargesafe_refresh_token', data.refresh_token);
      setUser(mapBackendUser(data.user));
      nav('dashboard');
      setLastSync(new Date().toLocaleTimeString());
      addToast('Login successful', 'success');
    } catch (error) {
      addToast(error.message || 'Unable to verify authenticator code', 'error');
    } finally {
      setAuthBusy(false);
    }
  };

  const completeRegistrationMfaSetup = async () => {
    const code = normalizeOtpCode(document.getElementById('register-mfa-code')?.value || '');

    if (!pendingRegistrationMfaToken || !code) {
      addToast('Enter the Microsoft Authenticator code to continue', 'warn');
      return;
    }

    setAuthBusy(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/mfa/complete-registration`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          setup_token: pendingRegistrationMfaToken,
          code,
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Unable to complete Microsoft Authenticator setup');
      }

      if (pendingAdminLogin && data.user?.role !== 'admin') {
        setPendingAdminLogin(false);
        setPendingRegistrationMfaToken('');
        setPendingRegistrationMfaEmail('');
        setRegistrationMfaSetup(null);
        setRegistrationEmail('');
        clearRegistrationMfaSetup();
        setAuthView('login');
        throw new Error('This account does not have admin access');
      }

      setPendingAdminLogin(false);
      setPendingRegistrationMfaToken('');
      setPendingRegistrationMfaEmail('');
      setRegistrationMfaSetup(null);
      setRegistrationEmail('');
      clearRegistrationMfaSetup();
      playSplash(1700);
      if (data.access_token) localStorage.setItem('chargesafe_auth_token', data.access_token);
      if (data.refresh_token) localStorage.setItem('chargesafe_refresh_token', data.refresh_token);
      setUser(mapBackendUser(data.user));
      nav('dashboard');
      setLastSync(new Date().toLocaleTimeString());
      addToast('Account verified and Microsoft Authenticator enabled successfully', 'success');
    } catch (error) {
      addToast(error.message || 'Unable to complete Microsoft Authenticator setup', 'error');
    } finally {
      setAuthBusy(false);
    }
  };

  const submitPasswordReset = async () => {
    const email = document.getElementById('reset-email')?.value?.trim() || passwordResetContext.email || '';
    const token = passwordResetContext.token || document.getElementById('reset-token')?.value?.trim() || '';
    const password = document.getElementById('reset-pass')?.value || '';
    const confirmPassword = document.getElementById('reset-confirm-pass')?.value || '';

    if (!email || !token || !password || !confirmPassword) {
      addToast('Fill in email, token, and both password fields', 'warn');
      return;
    }

    const passwordPolicyError = getPasswordPolicyError(password);
    if (passwordPolicyError) {
      addToast(passwordPolicyError, 'warn');
      return;
    }

    if (password !== confirmPassword) {
      addToast('New password and confirmation must match', 'warn');
      return;
    }

    setAuthBusy(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/reset-password`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email,
          token,
          new_password: password,
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Unable to reset password');
      }

      addToast(data.message || 'Password reset successfully', 'success');
      window.history.replaceState({}, '', window.location.pathname);
      setPasswordResetContext({ email: "", token: "" });
      setAuthView('login');
    } catch (error) {
      addToast(error.message || 'Unable to reset password', 'error');
    } finally {
      setAuthBusy(false);
    }
  };

  const submitIncident = async () => {
    const sId = incidentStationId || String(currentStation?.id || '');
    const type = incidentType;
    const isPositiveFeedback = type === 'Positive';
    const severity = isPositiveFeedback ? null : incidentSeverity;
    const desc = incidentDescription;

    if (!desc || !desc.trim()) {
      addToast('Please enter a description', 'warn');
      return;
    }

    try {
      setFeedbackBusy(true);
      const response = await authApi('/reports', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          station_id: sId,
          report_type: type,
          severity: severity,
          description: desc,
        }),
      });

      const previousStation = stations.find((station) => String(station.id) === String(sId));

      // The freshly created report is inserted locally first so the feedback
      // history updates immediately even before any later refetch completes.
      const sName = previousStation?.name || 'Unknown Station';
      const newReport = {
        id: response.id || userReports.length + 103,
        station: sName,
        type,
        severity,
        date: new Date().toISOString().split('T')[0],
        desc,
        status: 'PUBLISHED'
      };
      setUserReports(prev => [newReport, ...prev]);
      setIncidentType('Overheating');
      setIncidentSeverity(3);
      setIncidentDescription('');
      refreshNotifications().catch((refreshError) => {
        console.error('Failed to refresh notifications after feedback submit:', refreshError);
      });

      const refreshedStation = await refreshStationRiskState(sId);
      const previousScore = Number(previousStation?.score ?? refreshedStation.score);
      const nextScore = Number(refreshedStation.score);
      const effect =
        nextScore > previousScore ? 'increased'
          : nextScore < previousScore ? 'decreased'
            : 'maintained';
      setScoreUpdateFlash({
        stationId: String(refreshedStation.id),
        previousScore,
        nextScore,
        delta: Number((nextScore - previousScore).toFixed(1)),
        effect,
      });

      addToast('Feedback published instantly and ML rescore triggered automatically ?', 'success');
      nav('station');
    } catch (error) {
      addToast(error.message || 'Failed to submit feedback', 'error');
    } finally {
      setFeedbackBusy(false);
    }
  };

  const doLogout = async () => {
    const token = localStorage.getItem('chargesafe_auth_token');
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch (error) {
      console.error('Logout request failed:', error);
    }
    localStorage.removeItem('chargesafe_auth_token');
    localStorage.removeItem('chargesafe_refresh_token');
    setUser(null);
    setAuthView("login");
    setPendingAdminLogin(false);
    setPendingMfaToken('');
    setPendingMfaEmail('');
  };

  const startMfaSetup = async () => {
    setMfaBusy(true);
    try {
      const data = await authApi('/auth/mfa/setup');
      setMfaSetup(data);
      addToast(data.message || 'Scan the QR code to continue', 'info');
    } catch (error) {
      addToast(error.message || 'Unable to start MFA setup', 'error');
    } finally {
      setMfaBusy(false);
    }
  };

  const enableMfa = async () => {
    const code = document.getElementById('mfa-setup-code')?.value?.trim() || '';
    if (!code) {
      addToast('Enter the authenticator code shown in Microsoft Authenticator', 'warn');
      return;
    }

    setMfaBusy(true);
    try {
      const data = await authApi('/auth/mfa/enable', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ code }),
      });

      setUser((previousUser) => previousUser ? { ...previousUser, mfaEnabled: true } : previousUser);
      setMfaSetup(null);
      addToast(data.message || 'MFA enabled successfully', 'success');
    } catch (error) {
      addToast(error.message || 'Unable to enable MFA', 'error');
    } finally {
      setMfaBusy(false);
    }
  };

  const disableMfa = async () => {
    const code = document.getElementById('mfa-disable-code')?.value?.trim() || '';
    if (!code) {
      addToast('Enter your current authenticator code to disable MFA', 'warn');
      return;
    }

    setMfaBusy(true);
    try {
      const data = await authApi('/auth/mfa/disable', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ code }),
      });

      setUser((previousUser) => previousUser ? { ...previousUser, mfaEnabled: false } : previousUser);
      addToast(data.message || 'MFA disabled successfully', 'success');
    } catch (error) {
      addToast(error.message || 'Unable to disable MFA', 'error');
    } finally {
      setMfaBusy(false);
    }
  };


  const markAllRead = async () => {
    if (!user) return;
    try {
      await authApi('/notifications/mark-all-read', { method: 'POST' });
      setNotifications(prev => prev.map(n => ({ ...n, unread: false })));
      addToast('All notifications marked as read', 'success');
    } catch (error) {
      addToast(error.message || 'Unable to update notifications', 'error');
    }
  };

  const clearNotifs = async () => {
    if (!user) return;
    try {
      await authApi('/notifications/mark-all-read', { method: 'POST' });
      setNotifications([]);
      addToast('Notifications cleared', 'info');
    } catch (error) {
      addToast(error.message || 'Unable to update notifications', 'error');
    }
  };

  const dismissNotif = async (id) => {
    if (!user) return;
    try {
      await authApi(`/notifications/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ is_read: true }),
      });
      setNotifications(prev => prev.filter(n => n.id !== id));
    } catch (error) {
      addToast(error.message || 'Unable to update notification', 'error');
    }
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
      const resp = buildOfflineChatResponse(msg, stations);
      setTimeout(() => {
        setMessages(prev => [...prev, { role: 'bot', text: resp }]);
      }, 600);
      return;
    }

    setIsTyping(true);
    try {
      const data = await authApi('/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: msg
        })
      });
      setMessages(prev => [...prev, { role: 'bot', text: data.reply || 'Sorry, I could not get a response.' }]);
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          role: 'bot',
          text: `${err?.message ? `Live AI is unavailable: ${err.message}. ` : ''}${buildOfflineChatResponse(msg, stations)}`,
        }
      ]);
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

    const passwordPolicyError = getPasswordPolicyError(newPassword);
    if (passwordPolicyError) {
      addToast(passwordPolicyError, 'warn');
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
        {authView === 'login' && (
          <div id="auth-login" className="auth-box">
            <div className="auth-logo">
              <img src="/logo.png" alt="ChargeSafe SL Logo" className="auth-logo-img" />
              <div className="auth-logo-text">ChargeSafe<span>&nbsp;SL</span></div>
            </div>
            <div className="auth-title">System Login</div>
            <label className="auth-label">Email Address</label>
            <input className="auth-input" id="login-email" type="email" placeholder="you@example.com" />
            <label className="auth-label">Password</label>
            <input className="auth-input" id="login-pass" type="password" placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢" />
            <div className="auth-switch" style={{ marginTop: '10px', marginBottom: '10px', justifyContent: 'flex-end' }}>
              <a onClick={() => {
                const email = document.getElementById('login-email')?.value?.trim() || '';
                setPasswordResetContext({ email, token: '' });
                setAuthView('forgot');
              }}>Forgot password?</a>
            </div>
            <button className="btn-full btn-green" onClick={() => doLogin(false)} style={{ marginBottom: '10px' }} disabled={authBusy}>{authBusy ? 'Please wait...' : 'Login'}</button>
            <button className="btn-full btn-outline" onClick={() => doLogin(true)} disabled={authBusy}>Admin Login</button>
            <div className="auth-switch" style={{ marginTop: '14px' }}>
              No account? <a onClick={() => setAuthView('register')}>Register here</a>
            </div>
          </div>
        )}
        {authView === 'register' && (
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
            <input className="auth-input" id="register-pass" type="password" placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢" />
            <label className="auth-label">Vehicle Model</label>
            <input className="auth-input" id="register-vehicle" placeholder="Nissan Leaf, Tesla Model 3â€¦" />
            <button className="btn-full btn-green" onClick={doRegister} disabled={authBusy}>{authBusy ? 'Please wait...' : 'Create Account'}</button>
            <div className="auth-switch">Already registered? <a onClick={() => setAuthView('login')}>Login here</a></div>
          </div>
        )}
        {authView === 'verify-email-sent' && (
          <div id="auth-verify-email-sent" className="auth-box">
            <div className="auth-logo">
              <img src="/logo.png" alt="ChargeSafe SL Logo" className="auth-logo-img" />
              <div className="auth-logo-text">ChargeSafe<span>&nbsp;SL</span></div>
            </div>
            <div className="auth-title">Verify Your Email</div>
            <div className="auth-switch" style={{ marginBottom: '14px', lineHeight: '1.8' }}>
              We sent a verification link to {registrationEmail || 'your email address'}. Open that link, then set up Microsoft Authenticator before first access.
            </div>
            <button className="btn-full btn-green" onClick={() => setAuthView('login')} disabled={authBusy}>
              Return to Login
            </button>
          </div>
        )}
        {authView === 'register-mfa' && registrationMfaSetup && (
          <div id="auth-register-mfa" className="auth-box">
            <div className="auth-logo">
              <img src="/logo.png" alt="ChargeSafe SL Logo" className="auth-logo-img" />
              <div className="auth-logo-text">ChargeSafe<span>&nbsp;SL</span></div>
            </div>
            <div className="auth-title">Set Up Microsoft Authenticator</div>
            <div className="auth-switch" style={{ marginBottom: '14px', lineHeight: '1.8' }}>
              Your email is verified for {pendingRegistrationMfaEmail || registrationMfaSetup.email}. Scan this QR code in Microsoft Authenticator, then enter the current 6-digit code to finish account access.
            </div>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '14px' }}>
              <img
                src={registrationMfaSetup.qr_code_data_url}
                alt="Microsoft Authenticator QR code"
                style={{ width: '180px', height: '180px', background: '#fff', padding: '10px', borderRadius: '8px' }}
              />
            </div>
            <div style={{ fontSize: '11px', color: 'var(--txt3)', marginBottom: '10px' }}>
              If scanning does not work, enter this secret manually in Microsoft Authenticator:
            </div>
            <div className="mono" style={{ fontSize: '11px', padding: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: '4px', wordBreak: 'break-all', marginBottom: '12px' }}>
              {registrationMfaSetup.secret}
            </div>
            <label className="auth-label">Authenticator Code</label>
            <input className="auth-input" id="register-mfa-code" inputMode="numeric" maxLength="6" placeholder="123456" />
            <button className="btn-full btn-green" onClick={completeRegistrationMfaSetup} disabled={authBusy}>
              {authBusy ? 'Please wait...' : 'Enable MFA & Continue'}
            </button>
            <div className="auth-switch" style={{ marginTop: '14px' }}>
              Back to <a onClick={() => {
                setPendingAdminLogin(false);
                setPendingRegistrationMfaToken('');
                setPendingRegistrationMfaEmail('');
                setRegistrationMfaSetup(null);
                clearRegistrationMfaSetup();
                setAuthView('login');
              }}>Login</a>
            </div>
          </div>
        )}
        {authView === 'forgot' && (
          <div id="auth-forgot" className="auth-box">
            <div className="auth-logo">
              <img src="/logo.png" alt="ChargeSafe SL Logo" className="auth-logo-img" />
              <div className="auth-logo-text">ChargeSafe<span>&nbsp;SL</span></div>
            </div>
            <div className="auth-title">Forgot Password</div>
            <div className="auth-switch" style={{ marginBottom: '14px', lineHeight: '1.7' }}>
              Enter the current Microsoft Authenticator 6-digit code for {passwordResetContext.email || 'your account'}. After verification, we will send a password reset link to your email.
            </div>
            <label className="auth-label">Authenticator Code</label>
            <input className="auth-input" id="forgot-mfa-code" inputMode="numeric" maxLength="6" placeholder="123456" />
            <button className="btn-full btn-green" onClick={requestPasswordReset} disabled={authBusy}>{authBusy ? 'Please wait...' : 'Verify & Send Link'}</button>
            <div className="auth-switch" style={{ marginTop: '14px' }}>
              Back to <a onClick={() => { setPasswordResetContext({ email: '', token: '' }); setAuthView('login'); }}>Login</a>
            </div>
          </div>
        )}
        {authView === 'reset-email-sent' && (
          <div id="auth-reset-email-sent" className="auth-box">
            <div className="auth-logo">
              <img src="/logo.png" alt="ChargeSafe SL Logo" className="auth-logo-img" />
              <div className="auth-logo-text">ChargeSafe<span>&nbsp;SL</span></div>
            </div>
            <div className="auth-title">Check Your Email</div>
            <div className="auth-switch" style={{ marginBottom: '14px', lineHeight: '1.8' }}>
              We sent a password reset link to {passwordResetContext.email || 'your email address'}. Open that link to set a new password securely.
            </div>
            <button className="btn-full btn-green" onClick={() => setAuthView('login')} disabled={authBusy}>
              Return to Login
            </button>
          </div>
        )}
        {authView === 'reset' && (
          <div id="auth-reset" className="auth-box">
            <div className="auth-logo">
              <img src="/logo.png" alt="ChargeSafe SL Logo" className="auth-logo-img" />
              <div className="auth-logo-text">ChargeSafe<span>&nbsp;SL</span></div>
            </div>
            <div className="auth-title">Reset Password</div>
            <div className="auth-switch" style={{ marginBottom: '14px', lineHeight: '1.7' }}>
              Set a new password for {passwordResetContext.email || 'your account'} and confirm it below.
            </div>
            <label className="auth-label">Email Address</label>
            <input className="auth-input" id="reset-email" type="email" placeholder="you@example.com" defaultValue={passwordResetContext.email} />
            {!passwordResetContext.token && (
              <>
                <label className="auth-label">Recovery Token</label>
                <input className="auth-input" id="reset-token" placeholder="Paste the token from your email" />
              </>
            )}
            <label className="auth-label">New Password</label>
            <input className="auth-input" id="reset-pass" type="password" placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢" />
            <label className="auth-label">Confirm New Password</label>
            <input className="auth-input" id="reset-confirm-pass" type="password" placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢" />
            <button className="btn-full btn-green" onClick={submitPasswordReset} disabled={authBusy}>{authBusy ? 'Please wait...' : 'Reset Password'}</button>
            <div className="auth-switch" style={{ marginTop: '10px' }}>
              Back to <a onClick={() => setAuthView('login')}>Login</a>
            </div>
          </div>
        )}
        {authView === 'mfa' && (
          <div id="auth-mfa" className="auth-box">
            <div className="auth-logo">
              <img src="/logo.png" alt="ChargeSafe SL Logo" className="auth-logo-img" />
              <div className="auth-logo-text">ChargeSafe<span>&nbsp;SL</span></div>
            </div>
            <div className="auth-title">Multi-Factor Authentication</div>
            <div className="auth-switch" style={{ marginBottom: '14px' }}>
              Enter the current 6-digit code from Microsoft Authenticator for {pendingMfaEmail || 'your account'}.
            </div>
            <label className="auth-label">Authenticator Code</label>
            <input className="auth-input" id="mfa-code" inputMode="numeric" maxLength="6" placeholder="123456" />
            <button className="btn-full btn-green" onClick={submitMfaLogin} disabled={authBusy}>{authBusy ? 'Please wait...' : 'Verify Code'}</button>
            <div className="auth-switch" style={{ marginTop: '14px' }}>
              Back to <a onClick={() => { setPendingAdminLogin(false); setPendingMfaToken(''); setPendingMfaEmail(''); setAuthView('login'); }}>Login</a>
            </div>
          </div>
        )}
        {false && (
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
        )} {false && (
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
            <span className="nav-icon">📋</span> My Feedback
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
          <div className="sb-status"><div className="status-dot"></div><span className="mono">LIVE — {stationStats.total} stations</span></div>
          <button className="btn-logout" onClick={doLogout}>⏻&nbsp; Logout</button>
        </div>
      </div>

      <div id="main">
        <div id="topbar">
          <div className="topbar-title">{currentView.replace('-', ' ').toUpperCase()}</div>
          <div className="topbar-right">
            <div className="topbar-time mono">{clock}</div>
            <div className="topbar-notif" onClick={() => nav('notifications')}>🔔{unreadCount > 0 && <div className="notif-badge">{unreadCount}</div>}</div>
          </div>
        </div>
        <div id="content">

          {currentView === 'dashboard' && (
            <div className="view active" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div className="live-ticker">
                <div className="ticker-scroll">
                  {stations.concat(stations).map((s, i) => (
                    <span key={i} className="ticker-chip">{s.name.toUpperCase()} <span className={getRiskMeta(s.score).badge}>{s.faults} ALERT{s.faults === 1 ? '' : 'S'}</span></span>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '24px', alignItems: 'stretch', maxWidth: '100%' }}>
                
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
                        icon={getMarkerIcon(s.color || getRiskColor(s.score))}
                        eventHandlers={{ click: () => openStation(s.id) }}
                      />
                    ))}
                    <MapResizer />
                  </MapContainer>
                  <div style={{ position: 'absolute', bottom: '10px', right: '10px', zIndex: 1000, background: 'rgba(10,22,40,0.8)', padding: '2px 8px', borderRadius: '4px', fontSize: '10px', color: 'var(--txt3)', fontFamily: 'Fira Code' }}>
                     {stationStats.total} STATIONS MONITORED
                  </div>
                </div>

                <div className="card" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                  <div className="card-header" style={{ marginBottom: '12px' }}><span className="card-title" style={{ fontSize: '10px' }}>QUICK ACTIONS</span></div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                    <button className="btn btn-accent cyan-a" onClick={() => nav('map')} style={{ flex: 1, minHeight: 0, fontSize: '9px', padding: '6px 12px', color: '#fff' }}>
                      <span style={{ fontSize: '12px' }}>🗺️</span> MAP VIEW
                    </button>
                    <button className="btn btn-accent amber-a" onClick={() => nav('incident')} title="Add Feedback" aria-label="Add Feedback" style={{ flex: 1, minHeight: 0, fontSize: '9px', padding: '6px 12px', color: '#fff' }}>
                      <span style={{ fontSize: '12px' }}>🚨</span> ADD FEEDBACK
                    </button>
                    <button className="btn btn-accent blue-a" onClick={() => nav('chatbot')} style={{ flex: 1, minHeight: 0, fontSize: '9px', padding: '6px 12px', color: '#fff' }}>
                      <span style={{ fontSize: '12px' }}>🤖</span> CHATBOT
                    </button>
                    <button className="btn btn-accent gray-a" onClick={() => nav('notifications')} style={{ flex: 1, minHeight: 0, fontSize: '9px', padding: '6px 12px', color: '#fff' }}>
                      <span style={{ fontSize: '12px' }}>🔔</span> NOTIFICATIONS
                    </button>
                  </div>
                  {false && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1, justifyContent: 'center' }}>
                    <button className="btn btn-accent cyan-a" onClick={() => nav('map')} style={{ fontSize: '9px', padding: '6px 12px' }}>
                      <span style={{ fontSize: '12px' }}>ðŸ—ºï¸</span> MAP VIEW
                    </button>
                    <button className="btn btn-accent amber-a" onClick={() => nav('incident')} title="Add Feedback" aria-label="Add Feedback" style={{ fontSize: '9px', padding: '6px 12px' }}>
                      <span style={{ fontSize: '12px' }}>ðŸš¨</span> ADD FEEDBACK
                    </button>
                    <button className="btn btn-accent blue-a" onClick={() => nav('chatbot')} style={{ fontSize: '9px', padding: '6px 12px' }}>
                      <span style={{ fontSize: '12px' }}>ðŸ¤–</span> CHATBOT
                    </button>
                  </div>
                  )}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gridTemplateRows: 'repeat(4, 1fr)', gap: '16px', flex: 1, minWidth: 0 }}>
                  <div className="card stat-card" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <div className="stat-num green" style={{ fontSize: '20px' }}>{stationStats.low}</div>
                    <div className="stat-label">Safe Stations</div>
                  </div>
                  <div className="card stat-card" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <div className="stat-num red" style={{ fontSize: '20px' }}>{stationStats.high}</div>
                    <div className="stat-label">High-Risk Stations</div>
                  </div>
                  <div className="card stat-card" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <div className="stat-num cyan" style={{ fontSize: '20px' }}>{stationStats.total}</div>
                    <div className="stat-label">Total Stations</div>
                  </div>
                  <div className="card stat-card" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <div className="stat-num amber" style={{ fontSize: '20px' }}>{stationStats.medium}</div>
                    <div className="stat-label">Warning Status</div>
                  </div>

                  {false && (
                  <>
                  <div className="card" style={{ padding: '12px 16px', background: 'rgba(0,255,255,0.03)', border: '1px solid rgba(0,255,255,0.1)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div className="badge badge-cyan" style={{ fontSize: '8px', padding: '2px 6px', flexShrink: 0 }}>LIVE</div>
                      <div style={{ flex: 1, overflow: 'hidden', whiteSpace: 'nowrap', position: 'relative' }}>
                        <div className="marquee" style={{ fontSize: '10px', color: 'var(--cyan)', fontFamily: 'Fira Code' }}>
                          [11:02] DEMO Kandy High Risk 02 — Firmware upgrade initiated ... [10:55] DEMO Colombo High Risk 01 — Score updated to 88/100 ... [10:48] DEMO Galle Medium Risk 01 — Billing error feedback received ...
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="grid2" style={{ gap: '16px' }}>
                    <div className="card">
                      <div className="card-header" style={{ marginBottom: '12px' }}><span className="card-title" style={{ fontSize: '10px' }}>QUICK ACTIONS</span></div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <button className="btn btn-accent cyan-a" onClick={() => nav('map')} style={{ fontSize: '9px', padding: '6px 12px' }}>
                          <span style={{ fontSize: '12px' }}>🗺️</span> MAP VIEW
                        </button>
                        <button className="btn btn-accent amber-a" onClick={() => nav('incident')} title="Add Feedback" aria-label="Add Feedback" style={{ fontSize: '9px', padding: '6px 12px' }}>
                          <span style={{ fontSize: '12px' }}>🚨</span> ADD FEEDBACK
                        </button>
                        <button className="btn btn-accent blue-a" onClick={() => nav('chatbot')} style={{ fontSize: '9px', padding: '6px 12px' }}>
                          <span style={{ fontSize: '12px' }}>🤖</span> CHATBOT
                        </button>
                      </div>
                    </div>

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
                  </>
                  )}
                </div>
              </div>

              {false && (
              <div className="grid2" style={{ gap: '16px' }}>
                <div className="card">
                <div className="card-header" style={{ marginBottom: '12px' }}><span className="card-title" style={{ fontSize: '10px' }}>QUICK ACTIONS</span></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <button className="btn btn-accent cyan-a" onClick={() => nav('map')} style={{ fontSize: '9px', padding: '6px 12px' }}>
                    <span style={{ fontSize: '12px' }}>ðŸ—ºï¸</span> MAP VIEW
                  </button>
                  <button className="btn btn-accent amber-a" onClick={() => nav('incident')} title="Add Feedback" aria-label="Add Feedback" style={{ fontSize: '9px', padding: '6px 12px' }}>
                    <span style={{ fontSize: '12px' }}>ðŸš¨</span> ADD FEEDBACK
                  </button>
                  <button className="btn btn-accent blue-a" onClick={() => nav('chatbot')} style={{ fontSize: '9px', padding: '6px 12px' }}>
                    <span style={{ fontSize: '12px' }}>ðŸ¤–</span> CHATBOT
                  </button>
                </div>
                </div>
                <div></div>
              </div>
              )}

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
                      icon={getMarkerIcon(s.color || getRiskColor(s.score))}
                    >
                      <Popup>
                        <div className="map-popup">
                          <strong style={{ color: '#000', fontSize: '13px' }}>{s.name}</strong><br/>
                          <span style={{ color: '#444', fontSize: '11px' }}>{s.loc}</span><br/>
                          <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ color: s.color || getRiskColor(s.score), fontWeight: 700, fontSize: '14px' }}>{s.score}/100</span>
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
                    <div className="flex-between"><span style={{ fontSize: '12px', color: 'var(--txt3)' }}>Risk Score</span><span className={`orb text-${getRiskMeta(currentStation.score).badge} ${scoreUpdateFlash?.stationId === String(currentStation.id) ? 'score-update-pop' : ''}`} style={{ fontSize: '20px', fontWeight: 700 }}>{currentStation.score}/100</span></div>
                    <div className="risk-bar-wrap"><div className={`risk-bar-fill ${getRiskMeta(currentStation.score).badge}`} style={{ width: `${currentStation.score}%` }}></div></div>
                    {scoreUpdateFlash?.stationId === String(currentStation.id) && (
                      <div className="score-update-banner">
                        ML score {scoreUpdateFlash.effect} live: {scoreUpdateFlash.previousScore}/100 to {scoreUpdateFlash.nextScore}/100 ({scoreUpdateFlash.delta >= 0 ? '+' : ''}{scoreUpdateFlash.delta})
                      </div>
                    )}
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
                    <button className="btn btn-warn" onClick={() => nav('incident')} title="Add Feedback" aria-label="Add Feedback">?? Add Feedback</button>
                    <button className="btn btn-ghost" onClick={() => nav('chatbot')}>🤖 Ask AI Chatbot</button>
                  </div>
                </div>
              </div>

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

          {currentView === 'cyber' && (
            <CyberProfile
              currentStation={currentStation}
              authApi={authApi}
              nav={nav}
              addToast={addToast}
            />
          )}

          {false && (
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

          {currentView === 'mlscore' && (
            <div className="view active">
              <div className="flex-between mb24">
                <div><div className="page-label">AI Risk Engine</div><div className="page-title">ML Risk Score</div></div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button className="btn btn-ghost" onClick={() => nav('station')}>← Station Details</button>
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
                    <div className={`gauge-score ${getRiskMeta(mlScore).badge} ${scoreUpdateFlash?.stationId === String(currentStation.id) ? 'score-update-pop' : ''}`}>{mlScore}</div>
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
                    <button className="btn btn-ghost btn-sm" onClick={() => quickChat('Why is DEMO Colombo High Risk 01 high risk?')}>Why is DEMO Colombo High Risk 01 high risk?</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => quickChat('Which stations are high risk right now?')}>Which stations are high risk right now?</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => quickChat('Which stations are lowest risk right now?')}>Which stations are lowest risk right now?</button>
                  </div>
                </div>

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
                    <option value="PUBLISHED">Published</option>
                    <option value="RESOLVED">Resolved</option>
                    <option value="FLAGGED">Flagged</option>
                  </select>
                  <button className="btn btn-primary" onClick={() => nav('incident')} title="Add Feedback" aria-label="Add Feedback" style={{ paddingLeft: '20px', paddingRight: '20px', background: 'var(--amber)', color: '#000' }}>+ ADD FEEDBACK</button>
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
                            Type: {r.type}{r.severity != null ? ` — Severity: ${r.severity}/5` : ''} — Submitted: {r.date}
                          </div>
                          <div style={{ marginTop: '12px', fontStyle: 'italic', fontSize: '12px', color: 'var(--txt2)', opacity: 0.8 }}>
                            "{r.desc}"
                          </div>
                        </div>
                        <span className={`badge badge-${r.status === 'RESOLVED' ? 'green' : r.status === 'PUBLISHED' ? 'cyan' : 'amber'}`} style={{ padding: '4px 10px' }}>{r.status}</span>
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
                    No feedback entries match the selected filter.
                  </div>
                )}
              </div>
            </div>
          )}

          {currentView === 'incident' && (
            <div className="view active" style={{ padding: '24px' }}>
              <div className="flex-between mb24">
                <div><div className="page-label" style={{ color: 'var(--red)' }}>// STATION FEEDBACK</div><div className="page-title" style={{ fontSize: '24px' }}>ADD FEEDBACK</div></div>
              </div>

              <div className="grid2">
                <div className="card" style={{ padding: '24px' }}>
                  <div className="card-header"><span className="card-title">Feedback Details</span></div>
                  
                  <div className="form-group">
                    <label className="form-label">Select Station *</label>
                    <select
                      className="form-input form-select"
                      id="inc-station"
                      value={incidentStationId}
                      onChange={(e) => setIncidentStationId(e.target.value)}
                    >
                      {stations.map(s => <option key={s.id} value={s.id}>{s.name} ({s.loc})</option>)}
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Category *</label>
                    <select
                      className="form-input form-select"
                      id="inc-type"
                      value={incidentType}
                      onChange={(e) => setIncidentType(e.target.value)}
                    >
                      <option value="Overheating">Overheating</option>
                      <option value="Connectivity / Offline">Connectivity / Offline</option>
                      <option value="Physical Damage">Physical Damage</option>
                      <option value="Billing / Payment Error">Billing / Payment Error</option>
                      <option value="Charging Cable Issue">Charging Cable Issue</option>
                      <option value="Positive">Positive</option>
                      <option value="Other">Other</option>
                    </select>
                  </div>

                  {incidentType !== 'Positive' && (
                    <div className="form-group">
                      <label className="form-label">Severity Level (1-5)</label>
                      <input
                        type="range"
                        className="range-slider"
                        min="1"
                        max="5"
                        value={incidentSeverity}
                        id="inc-severity"
                        onChange={(e) => setIncidentSeverity(parseInt(e.target.value, 10))}
                      />
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--txt3)', marginTop: '4px', fontFamily: 'Fira Code' }}>
                        <span>LOW</span><span>MEDIUM</span><span>CRITICAL</span>
                      </div>
                    </div>
                  )}

                  <div className="form-group">
                    <label className="form-label">Detailed Feedback *</label>
                    <textarea
                      className="form-input"
                      id="inc-desc"
                      rows="4"
                      value={incidentDescription}
                      onChange={(e) => setIncidentDescription(e.target.value)}
                      placeholder="Describe your feedback in detail..."
                      aria-label="Detailed Feedback"
                      style={{ resize: 'none' }}
                    ></textarea>
                  </div>

                  <div style={{ marginTop: '24px', display: 'flex', gap: '12px' }}>
                    <button className="btn btn-primary" style={{ flex: 1 }} onClick={submitIncident} title="Submit Feedback" aria-label="Submit Feedback" disabled={feedbackBusy}>
                      {feedbackBusy ? 'RUNNING ML RESCORE...' : 'SUBMIT FEEDBACK'}
                    </button>
                  </div>
                </div>

                <div className="card" style={{ padding: '24px', background: 'rgba(255,100,100,0.02)', border: '1px solid rgba(255,100,100,0.1)' }}>
                  <div className="card-header"><span className="card-title" style={{ color: 'var(--red)' }}>Feedback Guidelines</span></div>
                  <ul style={{ fontSize: '12px', color: 'var(--txt2)', paddingLeft: '20px', lineHeight: '1.8' }}>
                    <li>Ensure you are selecting the correct station location.</li>
                    <li>Provide visual evidence if possible (Physical damage).</li>
                    <li>Abuse of the feedback system may lead to account flagged status.</li>
                    <li>Security-related feedback triggers immediate system-wide alerts.</li>
                  </ul>
                  <div style={{ marginTop: '24px', padding: '16px', background: 'var(--bg0)', borderRadius: '4px', border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--red)', fontWeight: 800, marginBottom: '8px' }}>EMERGENCY?</div>
                    <div style={{ fontSize: '11px', color: 'var(--txt3)', lineHeight: '1.8' }}>
                      <div>Sri Lankan Emergency: 119</div>
                      <div>Fire Department: 110</div>
                      <div>International Emergency: 112</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

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

                  <div style={{ marginTop: '24px', borderTop: '1px solid var(--border)', paddingTop: '20px' }}>
                    <div className="page-label">Multi-Factor Authentication</div>
                    <div style={{ fontSize: '12px', color: 'var(--txt3)', marginTop: '8px', lineHeight: '1.8' }}>
                      Use Microsoft Authenticator to protect your account with a rotating 6-digit code.
                    </div>
                    <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '12px', background: 'var(--bg0)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                      <div>
                        <div style={{ fontSize: '12px', fontWeight: 600 }}>Status</div>
                        <div style={{ fontSize: '11px', color: 'var(--txt3)', marginTop: '4px' }}>
                          {user.mfaEnabled ? 'Enabled for this account' : 'Not enabled'}
                        </div>
                      </div>
                      <span className={`badge badge-${user.mfaEnabled ? 'green' : 'amber'}`}>
                        {user.mfaEnabled ? 'MFA ON' : 'MFA OFF'}
                      </span>
                    </div>

                    {!user.mfaEnabled && !mfaSetup && (
                      <button className="btn btn-primary" style={{ width: '100%', marginTop: '12px' }} onClick={startMfaSetup} disabled={mfaBusy}>
                        {mfaBusy ? 'Preparing setup...' : 'Set Up Microsoft Authenticator'}
                      </button>
                    )}

                    {!user.mfaEnabled && mfaSetup && (
                      <div style={{ marginTop: '16px', padding: '16px', background: 'var(--bg0)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                        <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '12px' }}>Scan QR Code</div>
                        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '14px' }}>
                          <img
                            src={mfaSetup.qr_code_data_url}
                            alt="Microsoft Authenticator QR code"
                            style={{ width: '180px', height: '180px', background: '#fff', padding: '10px', borderRadius: '8px' }}
                          />
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--txt3)', marginBottom: '10px' }}>
                          If scanning does not work, enter this secret manually in Microsoft Authenticator:
                        </div>
                        <div className="mono" style={{ fontSize: '11px', padding: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: '4px', wordBreak: 'break-all', marginBottom: '12px' }}>
                          {mfaSetup.secret}
                        </div>
                        <div className="form-group">
                          <label className="form-label">Authenticator Code</label>
                          <input className="form-input" id="mfa-setup-code" inputMode="numeric" maxLength="6" placeholder="123456" />
                        </div>
                        <div style={{ display: 'flex', gap: '10px' }}>
                          <button className="btn btn-primary" style={{ flex: 1 }} onClick={enableMfa} disabled={mfaBusy}>
                            {mfaBusy ? 'Verifying...' : 'Enable MFA'}
                          </button>
                          <button className="btn btn-ghost" style={{ flex: 1 }} onClick={() => setMfaSetup(null)} disabled={mfaBusy}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}

                    {user.mfaEnabled && (
                      <div style={{ marginTop: '16px', padding: '16px', background: 'var(--bg0)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                        <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '8px' }}>Disable MFA</div>
                        <div style={{ fontSize: '11px', color: 'var(--txt3)', marginBottom: '12px' }}>
                          Enter a current Microsoft Authenticator code to turn off multi-factor authentication.
                        </div>
                        <div className="form-group">
                          <label className="form-label">Authenticator Code</label>
                          <input className="form-input" id="mfa-disable-code" inputMode="numeric" maxLength="6" placeholder="123456" />
                        </div>
                        <button className="btn btn-outline" style={{ width: '100%' }} onClick={disableMfa} disabled={mfaBusy}>
                          {mfaBusy ? 'Disabling...' : 'Disable MFA'}
                        </button>
                      </div>
                    )}
                  </div>

                  <div style={{ marginTop: '32px', borderTop: '1px solid var(--border)', paddingTop: '20px' }}>
                    <div className="page-label" style={{ color: 'var(--red)' }}>Danger Zone</div>
                    <div style={{ fontSize: '12px', color: 'var(--txt3)', marginTop: '8px' }}>Permanently delete your account and all associated data.</div>
                    <button className="btn btn-danger" style={{ marginTop: '12px' }} onClick={deleteAccount} disabled={securityBusy}>Delete Account</button>
                  </div>
                </div>
              </div>
              <div className="card" style={{ marginTop: '24px' }}>
                <div className="card-header">
                  <span className="card-title">Cyber Profile</span>
                  {stationCyberScore && (
                    <span className={`badge badge-${
                      stationCyberScore.overall_risk_level === 'LOW' ? 'green'
                      : stationCyberScore.overall_risk_level === 'MEDIUM' ? 'amber' : 'red'
                    }`}>{stationCyberScore.overall_risk_level} RISK</span>
                  )}
                </div>

                <div style={{ display: 'grid', gap: '16px' }}>
                  <div className="grid2">
                    <div style={{ padding: '16px', background: 'var(--bg0)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                      <div className="page-label">Composite Score</div>
                      <div style={{ marginTop: '8px', fontSize: '28px', fontWeight: 800, fontFamily: 'Orbitron', color:
                        stationCyberScore
                          ? (stationCyberScore.overall_risk_level === 'LOW' ? 'var(--green)' : stationCyberScore.overall_risk_level === 'MEDIUM' ? 'var(--amber)' : 'var(--red)')
                          : 'var(--txt3)'
                      }}>
                        {stationCyberScore ? stationCyberScore.overall_score.toFixed(1) : '--'}
                      </div>
                      <div style={{ marginTop: '6px', fontSize: '11px', color: 'var(--txt3)' }}>
                        {stationCyberScore ? `${stationCyberScore.criteria_count} criteria assessed` : 'Loading...'}
                      </div>
                    </div>

                    <div style={{ padding: '16px', background: 'var(--bg0)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                      <div className="page-label">Compliance</div>
                      <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        {(() => {
                          const bd = stationCyberScore?.breakdown || [];
                          const hasHigh = bd.some(i => (i.risk_rating || '').match(/HIGH|CRITICAL/));
                          const hasMed = bd.some(i => i.risk_rating === 'MEDIUM' || i.score_value === 2);
                          const iec = !bd.length ? 'PENDING' : hasHigh ? 'NON-COMPLIANT' : hasMed ? 'PARTIAL' : 'COMPLIANT';
                          const owasp = !bd.length ? 'PENDING' : hasHigh ? 'HIGH EXPOSURE' : hasMed ? 'PARTIAL' : 'ALIGNED';
                          return (<>
                            <div className="flex-between" style={{ fontSize: '11px' }}>
                              <span>IEC 62443</span>
                              <span className={`badge badge-${iec === 'COMPLIANT' ? 'green' : iec === 'PARTIAL' ? 'amber' : 'red'}`}>{iec}</span>
                            </div>
                            <div className="flex-between" style={{ fontSize: '11px' }}>
                              <span>OWASP IoT</span>
                              <span className={`badge badge-${owasp === 'ALIGNED' ? 'green' : owasp === 'PARTIAL' ? 'amber' : 'red'}`}>{owasp}</span>
                            </div>
                          </>);
                        })()}
                      </div>
                    </div>
                  </div>

                  <button className="btn btn-ghost" style={{ border: '1px solid var(--cyan)', color: 'var(--cyan)', fontSize: '12px' }} onClick={() => nav('cyber')}>
                    Full Cyber Security Analysis
                  </button>
                </div>
              </div>

            </div>
          )}

          {currentView.startsWith('admin') && (
            <div className="view active">
              <div className="page-header"><div className="page-label">System Control</div><div className="page-title">Admin Panel</div></div>
              
              <div className="admin-tab-row">
                <div className={`admin-tab ${adminSubView === 'dash' ? 'active' : ''}`} onClick={() => setAdminSubView('dash')}>Dashboard</div>
                <div className={`admin-tab ${adminSubView === 'stations' ? 'active' : ''}`} onClick={() => setAdminSubView('stations')}>Manage Stations</div>
                <div className={`admin-tab ${adminSubView === 'reports' ? 'active' : ''}`} onClick={() => setAdminSubView('reports')} title="Review Feedback" aria-label="Review Feedback">Review Feedback</div>
                <div className={`admin-tab ${adminSubView === 'users' ? 'active' : ''}`} onClick={() => setAdminSubView('users')}>Manage Users</div>
              </div>

              {adminSubView === 'dash' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <div className="grid4">
                    <div className="card stat-card"><div className="stat-num cyan">{stationStats.total}</div><div className="stat-label">Total Stations</div></div>
                    <div className="card stat-card"><div className="stat-num amber">12</div><div className="stat-label">Pending Feedback</div></div>
                    <div className="card stat-card"><div className="stat-num green">1,402</div><div className="stat-label">Total Users</div></div>
                    <div className="card stat-card"><div className="stat-num red">{stationStats.high}</div><div className="stat-label">High-Risk Stations</div></div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '20px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                      <div className="card">
                        <div className="card-header">
                          <span className="card-title">Risk Distribution Chart</span>
                          <span className="card-sub">Live portfolio mix</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                          {adminDashboardRiskSegments.map((segment) => (
                            <div key={segment.label}>
                              <div className="flex-between" style={{ fontSize: '11px', marginBottom: '6px' }}>
                                <span style={{ color: 'var(--txt2)' }}>{segment.label}</span>
                                <span className="mono" style={{ color: segment.color }}>{segment.count}</span>
                              </div>
                              <div style={{ height: '10px', borderRadius: '999px', background: 'rgba(255,255,255,0.05)', overflow: 'hidden', border: '1px solid var(--border)' }}>
                                <div style={{ height: '100%', width: segment.width, minWidth: segment.count ? '12%' : '0%', background: `linear-gradient(90deg, ${segment.color}, ${segment.color})`, boxShadow: `0 0 18px ${segment.glow}` }}></div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="card">
                        <div className="card-header">
                          <span className="card-title">Recent Admin Activity</span>
                          <span className="card-sub">Operational timeline</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          {adminDashboardActivity.map((item, index) => (
                            <div key={`${item.title}-${index}`} style={{ padding: '12px 14px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                              <div className="flex-between" style={{ gap: '12px' }}>
                                <div style={{ fontSize: '11px', fontWeight: 600, color: item.color }}>{item.title}</div>
                                <div className="mono" style={{ fontSize: '10px', color: 'var(--txt3)', whiteSpace: 'nowrap' }}>{item.time}</div>
                              </div>
                              <div style={{ marginTop: '6px', fontSize: '11px', color: 'var(--txt3)', lineHeight: '1.6' }}>{item.detail}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                      <div className="card">
                        <div className="card-header">
                          <span className="card-title">System Status Panel</span>
                          <span className="card-sub">Platform health</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                          {adminDashboardSystemStatus.map((item) => (
                            <div key={item.label} style={{ padding: '12px 14px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                              <div className="flex-between" style={{ gap: '12px' }}>
                                <span style={{ fontSize: '11px', color: 'var(--txt2)' }}>{item.label}</span>
                                <span className={`badge badge-${item.badge}`}>{item.value}</span>
                              </div>
                              <div style={{ marginTop: '6px', fontSize: '10px', color: 'var(--txt3)', lineHeight: '1.6' }}>{item.meta}</div>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="card">
                        <div className="card-header">
                          <span className="card-title">Response / Resolution Metrics</span>
                          <span className="card-sub">Feedback performance</span>
                        </div>
                        <div className="grid2" style={{ gap: '12px' }}>
                          <div style={{ padding: '14px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                            <div className="card-sub">Resolution Rate</div>
                            <div style={{ marginTop: '8px', fontSize: '24px', fontWeight: 800, color: 'var(--green)', fontFamily: 'Orbitron' }}>{adminDashboardReportMetrics.resolutionRate}</div>
                          </div>
                          <div style={{ padding: '14px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                            <div className="card-sub">Under Review</div>
                            <div style={{ marginTop: '8px', fontSize: '24px', fontWeight: 800, color: 'var(--amber)', fontFamily: 'Orbitron' }}>{adminDashboardReportMetrics.underReview}</div>
                          </div>
                          <div style={{ padding: '14px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                            <div className="card-sub">Escalated Cases</div>
                            <div style={{ marginTop: '8px', fontSize: '24px', fontWeight: 800, color: 'var(--red)', fontFamily: 'Orbitron' }}>{adminDashboardReportMetrics.escalated}</div>
                          </div>
                          <div style={{ padding: '14px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                            <div className="card-sub">Avg Severity</div>
                            <div style={{ marginTop: '8px', fontSize: '24px', fontWeight: 800, color: 'var(--cyan)', fontFamily: 'Orbitron' }}>{adminDashboardReportMetrics.averageSeverity}</div>
                          </div>
                        </div>
                      </div>

                      <div className="card">
                        <div className="card-header">
                          <span className="card-title">User Security Snapshot</span>
                          <span className="card-sub">Identity posture</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                          {adminDashboardSecuritySnapshot.map((item) => (
                            <div key={item.label} style={{ padding: '12px 14px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: '4px' }}>
                              <div className="flex-between" style={{ gap: '12px' }}>
                                <span style={{ fontSize: '11px', color: 'var(--txt2)' }}>{item.label}</span>
                                <span className={`badge badge-${item.badge}`}>{item.value}</span>
                              </div>
                              <div style={{ marginTop: '6px', fontSize: '10px', color: 'var(--txt3)', lineHeight: '1.6' }}>{item.meta}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
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
                  <div className="card-header"><span className="card-title">Review Feedback (FR-72)</span></div>
                  <table className="data-table">
                    <thead><tr><th>User</th><th>Station</th><th>Issue</th><th>Status</th><th>Action</th></tr></thead>
                    <tbody>
                      {userReports.map(r => (
                        <tr key={r.id}>
                          <td>{user.name}</td>
                          <td>{r.station}</td>
                          <td>{r.type}</td>
                          <td><span className={`badge badge-${r.status === 'RESOLVED' ? 'green' : r.status === 'PUBLISHED' ? 'cyan' : 'amber'}`}>{r.status}</span></td>
                          <td><button className="btn btn-sm btn-primary" onClick={() => addToast('Processing feedback...', 'info')} title="Review Feedback" aria-label="Review Feedback">REVIEW</button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {false && adminSubView === 'data' && (
                <div className="grid2">
                  {false && <div className="card">
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
                  </div>}
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

          {currentView === 'settings' && (
            <div className="view active">
              <div className="page-header"><div className="page-label">System</div><div className="page-title">Settings</div></div>
              
              <div className="settings-grid">
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
                    <button className="btn btn-primary" style={{ width: '100%', marginTop: '24px' }} onClick={saveSettings}>Save Settings</button>
                  </div>

                  {false && <div className="card">
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
                  </div>}
                </div>

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
                      <input className="form-input" value={settings.language} readOnly />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Map Pin Colour Mode</label>
                      <input className="form-input" value={settings.mapPinColorMode} readOnly />
                    </div>
                  </div>

                  <div className="card">
                    <div className="card-header"><span className="card-title">About</span></div>
                    <table className="data-table">
                      <tbody>
                        <tr><td>Version</td><td className="mono">ChargeSafe SL v1.0.0</td></tr>
                        <tr><td>Group</td><td className="mono">ChargeSafeSL dev team</td></tr>
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

        </div>
      </div>

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








