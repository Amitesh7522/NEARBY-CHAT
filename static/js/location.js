/**
 * Nearby Chat — Geolocation Manager
 * Requests device location and syncs privacy-fuzzed coordinates with backend.
 */

window.updateUserLocation = function(onSuccessCallback) {
  if (!('geolocation' in navigator)) {
    if (typeof window.showToast === 'function') {
      window.showToast("Geolocation is not supported by your browser.", "info");
    }
    return;
  }

  if (typeof window.showToast === 'function') {
    window.showToast("Detecting your location...", "info");
  }

  navigator.geolocation.getCurrentPosition(
    async (position) => {
      const lat = position.coords.latitude;
      const lon = position.coords.longitude;

      try {
        let cityName = '';
        // Optional reverse geocode with OpenStreetMap Nominatim for human-readable city
        try {
          const geoRes = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lon}&zoom=10`);
          if (geoRes.ok) {
            const geoData = await geoRes.json();
            cityName = geoData.address.city || geoData.address.town || geoData.address.state_district || geoData.address.state || '';
          }
        } catch (e) {
          // Non-blocking
        }

        const res = await fetch('/accounts/api/location/update/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken') || '',
          },
          body: JSON.stringify({
            latitude: lat,
            longitude: lon,
            location_name: cityName,
          })
        });

        const data = await res.json();
        if (res.ok && data.success) {
          if (typeof window.showToast === 'function') {
            window.showToast("Location updated! Refreshing nearby people...", "success");
          }
          setTimeout(() => {
            if (onSuccessCallback) {
              onSuccessCallback();
            } else {
              window.location.reload();
            }
          }, 800);
        } else {
          if (typeof window.showToast === 'function') {
            window.showToast(data.error || "Could not update location.", "error");
          }
        }
      } catch (err) {
        console.error("Location sync failed:", err);
        if (typeof window.showToast === 'function') {
          window.showToast("Failed to connect to location service.", "error");
        }
      }
    },
    (err) => {
      console.warn("Geolocation permission error:", err);
      if (typeof window.showToast === 'function') {
        window.showToast("Location permission was denied or unavailable.", "error");
      }
    },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
  );
};
