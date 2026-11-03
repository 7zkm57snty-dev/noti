(function () {
  "use strict";

  const CONSENT_KEY = "cev-consent-v1";
  const GA_ID = "G-ERGNTK4W26";
  const DENIED = {
    analytics_storage: "denied",
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied"
  };

  function readChoice() {
    try {
      const value = JSON.parse(window.localStorage.getItem(CONSENT_KEY) || "null");
      if (value && value.version === 1 && typeof value.analytics === "boolean") {
        return value;
      }
    } catch (error) {
      // Si el navegador bloquea el almacenamiento, no se activa analítica.
    }
    return null;
  }

  function updateGoogleConsent(analyticsAllowed) {
    if (typeof window.gtag === "function") {
      window.gtag("consent", "update", {
        analytics_storage: analyticsAllowed ? "granted" : "denied",
        ad_storage: "denied",
        ad_user_data: "denied",
        ad_personalization: "denied"
      });
    }
  }

  function removeAnalyticsCookies() {
    try {
      const names = document.cookie
        .split(";")
        .map(function (part) { return part.split("=")[0].trim(); })
        .filter(function (name) {
          return /^_ga(?:_.+)?$|^_gid$|^_gat(?:_.+)?$|^_gac_.+$/i.test(name);
        });

      const domains = ["", "; domain=cevnoticias.com", "; domain=.cevnoticias.com"];
      names.forEach(function (name) {
        domains.forEach(function (domain) {
          document.cookie = name + "=; Max-Age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/" + domain + "; SameSite=Lax";
        });
      });
    } catch (error) {
      // El rechazo sigue guardado aunque el navegador no permita limpiar cookies.
    }
  }

  function loadGoogleAnalytics() {
    if (window.__cevGoogleAnalyticsStarted) return;

    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () {
      window.dataLayer.push(arguments);
    };

    // Se declara el estado antes de configurar la etiqueta.
    window.gtag("consent", "default", DENIED);
    window.gtag("consent", "update", {
      analytics_storage: "granted",
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied"
    });
    window.gtag("js", new Date());
    window.gtag("config", GA_ID);

    const script = document.createElement("script");
    script.async = true;
    script.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(GA_ID);
    script.onerror = function () {
      window.__cevGoogleAnalyticsStarted = false;
    };
    document.head.appendChild(script);
    window.__cevGoogleAnalyticsStarted = true;
  }

  function saveChoice(analyticsAllowed) {
    const choice = {
      version: 1,
      analytics: Boolean(analyticsAllowed),
      savedAt: new Date().toISOString()
    };

    try {
      window.localStorage.setItem(CONSENT_KEY, JSON.stringify(choice));
    } catch (error) {
      // Sin almacenamiento persistente no activamos analítica en esta visita.
      if (analyticsAllowed) {
        loadGoogleAnalytics();
      }
    }

    if (analyticsAllowed) {
      loadGoogleAnalytics();
    } else {
      updateGoogleConsent(false);
      removeAnalyticsCookies();
    }
    return choice;
  }

  function initBanner() {
    const banner = document.getElementById("cev-cookie-banner");
    const settingsButton = document.getElementById("cev-cookie-settings");
    const acceptButton = document.getElementById("cev-cookie-accept");
    const rejectButton = document.getElementById("cev-cookie-reject");
    const configureButton = document.getElementById("cev-cookie-configure");
    const options = document.getElementById("cev-cookie-options");
    const analyticsCheckbox = document.getElementById("cev-cookie-analytics");
    const saveButton = document.getElementById("cev-cookie-save");

    if (!banner || !settingsButton || !acceptButton || !rejectButton ||
        !configureButton || !options || !analyticsCheckbox || !saveButton) {
      return;
    }

    function showSettings() {
      const current = readChoice();
      analyticsCheckbox.checked = Boolean(current && current.analytics);
      options.hidden = false;
      banner.hidden = false;
      configureButton.setAttribute("aria-expanded", "true");
    }

    function closeBanner() {
      banner.hidden = true;
      options.hidden = true;
      configureButton.setAttribute("aria-expanded", "false");
    }

    acceptButton.addEventListener("click", function () {
      saveChoice(true);
      closeBanner();
    });

    rejectButton.addEventListener("click", function () {
      saveChoice(false);
      closeBanner();
    });

    configureButton.addEventListener("click", function () {
      if (options.hidden) {
        showSettings();
      } else {
        options.hidden = true;
        configureButton.setAttribute("aria-expanded", "false");
      }
    });

    saveButton.addEventListener("click", function () {
      saveChoice(analyticsCheckbox.checked);
      closeBanner();
    });

    settingsButton.addEventListener("click", showSettings);

    const current = readChoice();
    if (current && current.analytics) {
      loadGoogleAnalytics();
    } else if (!current) {
      banner.hidden = false;
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initBanner, { once: true });
  } else {
    initBanner();
  }
})();