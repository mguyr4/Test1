'use strict';

// --- State ---
const state = {
  loc1: null, // { lat, lon, display_name }
  loc2: null,
  markers: [],
  map: null,
  pubMarkers: [],
  midpointMarker: null,
  activeCard: null,
};

// --- DOM refs ---
const input1 = document.getElementById('location1');
const input2 = document.getElementById('location2');
const suggestions1 = document.getElementById('suggestions1');
const suggestions2 = document.getElementById('suggestions2');
const findBtn = document.getElementById('findBtn');
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');
const pubListEl = document.getElementById('pub-list');

// --- Geocoding (Nominatim) ---
let debounceTimers = {};

function setupAutocomplete(input, suggestionsEl, person) {
  input.addEventListener('input', () => {
    clearTimeout(debounceTimers[person]);
    const q = input.value.trim();
    if (q.length < 3) {
      suggestionsEl.innerHTML = '';
      return;
    }
    debounceTimers[person] = setTimeout(() => fetchSuggestions(q, suggestionsEl, input, person), 350);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') suggestionsEl.innerHTML = '';
  });

  document.addEventListener('click', (e) => {
    if (!input.contains(e.target) && !suggestionsEl.contains(e.target)) {
      suggestionsEl.innerHTML = '';
    }
  });
}

async function fetchSuggestions(query, suggestionsEl, input, person) {
  try {
    const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=5&addressdetails=1`;
    const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
    const data = await res.json();

    suggestionsEl.innerHTML = '';
    data.forEach(item => {
      const div = document.createElement('div');
      div.className = 'suggestion-item';
      div.textContent = item.display_name;
      div.addEventListener('click', () => {
        input.value = item.display_name;
        state[`loc${person}`] = { lat: parseFloat(item.lat), lon: parseFloat(item.lon), display_name: item.display_name };
        suggestionsEl.innerHTML = '';
      });
      suggestionsEl.appendChild(div);
    });
  } catch {
    // silently ignore autocomplete errors
  }
}

// --- Geolocation ---
document.querySelectorAll('.locate-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const person = btn.dataset.person;
    if (!navigator.geolocation) {
      showStatus('Geolocation is not supported by your browser.', 'error');
      return;
    }
    btn.textContent = '⏳';
    navigator.geolocation.getCurrentPosition(
      async pos => {
        const { latitude: lat, longitude: lon } = pos.coords;
        // Reverse geocode
        try {
          const url = `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`;
          const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
          const data = await res.json();
          const name = data.display_name || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
          state[`loc${person}`] = { lat, lon, display_name: name };
          document.getElementById(`location${person}`).value = name;
        } catch {
          state[`loc${person}`] = { lat, lon, display_name: `${lat.toFixed(5)}, ${lon.toFixed(5)}` };
          document.getElementById(`location${person}`).value = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
        }
        btn.textContent = '📍';
      },
      err => {
        btn.textContent = '📍';
        showStatus(`Could not get your location: ${err.message}`, 'error');
      }
    );
  });
});

// --- Geocode a raw text input if not already resolved ---
async function geocodeIfNeeded(person) {
  const input = document.getElementById(`location${person}`);
  const text = input.value.trim();
  if (!text) return false;

  // Already resolved and matches current input
  if (state[`loc${person}`] && state[`loc${person}`].display_name === text) return true;
  // Or coordinates match
  if (state[`loc${person}`]) return true;

  // Geocode
  const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(text)}&format=json&limit=1`;
  const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
  const data = await res.json();
  if (!data.length) return false;
  state[`loc${person}`] = { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon), display_name: data[0].display_name };
  return true;
}

// --- Midpoint ---
function midpoint(loc1, loc2) {
  return {
    lat: (loc1.lat + loc2.lat) / 2,
    lon: (loc1.lon + loc2.lon) / 2,
  };
}

// Haversine distance in metres
function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function formatDist(m) {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
}

// --- Overpass (pub search) ---
async function findPubs(lat, lon, radius, limit) {
  const query = `
    [out:json][timeout:25];
    (
      node["amenity"="pub"](around:${radius},${lat},${lon});
      way["amenity"="pub"](around:${radius},${lat},${lon});
      node["amenity"="bar"](around:${radius},${lat},${lon});
      way["amenity"="bar"](around:${radius},${lat},${lon});
    );
    out center ${limit * 3};
  `.trim();

  const res = await fetch('https://overpass-api.de/api/interpreter', {
    method: 'POST',
    body: `data=${encodeURIComponent(query)}`,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });

  if (!res.ok) throw new Error('Overpass API error');
  const data = await res.json();
  return data.elements || [];
}

// --- Map ---
function initMap(midLat, midLon) {
  if (state.map) {
    state.map.remove();
    state.map = null;
  }

  state.map = L.map('map').setView([midLat, midLon], 14);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(state.map);
}

function personIcon(label) {
  return L.divIcon({
    html: `<div style="background:#4a90d9;color:#fff;border-radius:50%;width:32px;height:32px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.4)">${label}</div>`,
    className: '',
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });
}

function midpointIcon() {
  return L.divIcon({
    html: `<div style="background:#f4c430;color:#1a1a2e;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:16px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.4)">⟷</div>`,
    className: '',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function pubIcon(rank) {
  return L.divIcon({
    html: `<div style="background:#2d3561;color:#f4c430;border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:2px solid #f4c430;box-shadow:0 2px 6px rgba(0,0,0,0.4)">${rank}</div>`,
    className: '',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

// --- Main flow ---
findBtn.addEventListener('click', async () => {
  showStatus('Resolving locations...', 'info');
  findBtn.disabled = true;
  resultsEl.classList.add('hidden');
  pubListEl.innerHTML = '';

  // Clear old pub markers
  state.pubMarkers.forEach(m => m.remove());
  state.pubMarkers = [];

  try {
    const ok1 = await geocodeIfNeeded(1);
    const ok2 = await geocodeIfNeeded(2);

    if (!ok1 || !ok2) {
      showStatus('Could not find one or both locations. Please check your input.', 'error');
      findBtn.disabled = false;
      return;
    }

    const mid = midpoint(state.loc1, state.loc2);
    const radius = parseInt(document.getElementById('radius').value);
    const limit = parseInt(document.getElementById('limit').value);

    showStatus('Searching for pubs...', 'info');

    const elements = await findPubs(mid.lat, mid.lon, radius, limit);

    if (!elements.length) {
      showStatus(`No pubs found within ${formatDist(radius)} of the midpoint. Try increasing the search radius.`, 'error');
      findBtn.disabled = false;
      return;
    }

    // Enrich with distances
    const pubs = elements.map(el => {
      const lat = el.lat ?? el.center?.lat;
      const lon = el.lon ?? el.center?.lon;
      const tags = el.tags || {};
      const d1 = haversine(state.loc1.lat, state.loc1.lon, lat, lon);
      const d2 = haversine(state.loc2.lat, state.loc2.lon, lat, lon);
      const midDist = haversine(mid.lat, mid.lon, lat, lon);
      const fairness = Math.abs(d1 - d2); // lower = fairer
      return { lat, lon, tags, d1, d2, midDist, fairness, name: tags.name || 'Unnamed Pub' };
    });

    // Sort by closeness to midpoint first, then fairness
    pubs.sort((a, b) => a.midDist - b.midDist || a.fairness - b.fairness);

    const topPubs = pubs.slice(0, limit);

    // Draw map
    initMap(mid.lat, mid.lon);

    // Person markers
    L.marker([state.loc1.lat, state.loc1.lon], { icon: personIcon('1') })
      .addTo(state.map)
      .bindPopup(`<b>Person 1</b><br>${state.loc1.display_name}`);
    L.marker([state.loc2.lat, state.loc2.lon], { icon: personIcon('2') })
      .addTo(state.map)
      .bindPopup(`<b>Person 2</b><br>${state.loc2.display_name}`);

    // Midpoint marker
    L.marker([mid.lat, mid.lon], { icon: midpointIcon() })
      .addTo(state.map)
      .bindPopup('<b>Midpoint</b>');

    // Line between the two people
    L.polyline(
      [[state.loc1.lat, state.loc1.lon], [state.loc2.lat, state.loc2.lon]],
      { color: '#4a90d9', weight: 2, dashArray: '6 4', opacity: 0.6 }
    ).addTo(state.map);

    // Pub markers + cards
    topPubs.forEach((pub, i) => {
      const rank = i + 1;
      const marker = L.marker([pub.lat, pub.lon], { icon: pubIcon(rank) })
        .addTo(state.map)
        .bindPopup(`<b>${pub.name}</b><br>From P1: ${formatDist(pub.d1)}<br>From P2: ${formatDist(pub.d2)}`);
      state.pubMarkers.push(marker);

      const card = createPubCard(pub, rank, marker);
      pubListEl.appendChild(card);
    });

    // Fit map to all points
    const allCoords = [
      [state.loc1.lat, state.loc1.lon],
      [state.loc2.lat, state.loc2.lon],
      ...topPubs.map(p => [p.lat, p.lon]),
    ];
    state.map.fitBounds(L.latLngBounds(allCoords), { padding: [40, 40] });

    statusEl.classList.add('hidden');
    resultsEl.classList.remove('hidden');
  } catch (err) {
    showStatus(`Error: ${err.message}`, 'error');
  }

  findBtn.disabled = false;
});

function createPubCard(pub, rank, marker) {
  const maxFairness = 500; // metres difference considered "fair enough"
  const fairnessScore = Math.max(0, 1 - pub.fairness / maxFairness);

  const card = document.createElement('div');
  card.className = 'pub-card';
  card.innerHTML = `
    <div class="pub-card-inner">
      <span class="rank-badge">${rank}</span>
      <div class="pub-info">
        <h3>${escHtml(pub.name)}</h3>
        <div class="address">${buildAddress(pub.tags)}</div>
        <div class="fairness-bar-wrap">
          <div class="fairness-label">Fairness</div>
          <div class="fairness-bar"><div class="fairness-fill" style="width:${(fairnessScore * 100).toFixed(0)}%"></div></div>
        </div>
      </div>
    </div>
    <div class="pub-meta">
      <div class="distance">P1: <span>${formatDist(pub.d1)}</span></div>
      <div class="distance">P2: <span>${formatDist(pub.d2)}</span></div>
      <div class="distance" style="margin-top:4px;font-size:0.8rem;color:#777;">diff: ${formatDist(pub.fairness)}</div>
    </div>
  `;

  card.addEventListener('click', () => {
    if (state.activeCard) state.activeCard.classList.remove('active');
    card.classList.add('active');
    state.activeCard = card;
    state.map.setView([pub.lat, pub.lon], 16, { animate: true });
    marker.openPopup();
  });

  return card;
}

function buildAddress(tags) {
  const parts = [
    tags['addr:housenumber'] && tags['addr:street'] ? `${tags['addr:housenumber']} ${tags['addr:street']}` : tags['addr:street'],
    tags['addr:city'],
    tags['addr:postcode'],
  ].filter(Boolean);
  return parts.join(', ') || 'Address not available';
}

function escHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function showStatus(msg, type) {
  statusEl.textContent = msg;
  statusEl.className = `status ${type}`;
  statusEl.classList.remove('hidden');
}

// --- Setup autocomplete ---
setupAutocomplete(input1, suggestions1, 1);
setupAutocomplete(input2, suggestions2, 2);
