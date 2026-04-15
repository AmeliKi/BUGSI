// BUGSI Device Web UI

(function () {
  "use strict";

  // Section display names
  var SECTION_LABELS = {
    still_camera: "Still Camera",
    event_camera: "Event Camera",
    image_capture: "Image Capture",
    telemetry: "Telemetry",
    upload: "Upload",
    power: "Power Management",
    lte: "LTE",
    zigbee: "Zigbee",
    storage: "Storage",
    webserver: "Web Server"
  };

  // Camera type display names
  var CAMERA_TYPE_LABELS = {
    "arducam_64mp": "ArduCam 64MP",
    "ids_rgb": "IDS RGB Camera",
    "prophesee_genx320": "Prophesee GenX320",
    "ids_evs": "IDS uEye EVS",
    "mock": "Mock Camera"
  };

  // Dropdown options for string fields (all non-path strings get a select)
  var SELECT_OPTIONS = {
    "still_camera.type": [
      { value: "arducam_64mp", label: "ArduCam 64MP" },
      { value: "ids_rgb", label: "IDS RGB Camera" },
      { value: "mock", label: "Mock Camera" }
    ],
    "still_camera.autofocus_mode": [
      { value: "continuous", label: "Continuous" },
      { value: "manual", label: "Manual" },
      { value: "fixed", label: "Fixed" }
    ],
    "still_camera.white_balance": [
      { value: "auto", label: "Auto (Continuous)" },
      { value: "once", label: "Once" },
      { value: "off", label: "Off (Manual Ratios)" }
    ],
    "event_camera.type": [
      { value: "prophesee_genx320", label: "Prophesee GenX320" },
      { value: "ids_evs", label: "IDS uEye EVS" },
      { value: "mock", label: "Mock Camera" }
    ],
    "power.night_mode_type": [
      { value: "fixed", label: "Fixed Hours" },
      { value: "location-based", label: "Location-based (Sunrise/Sunset)" }
    ],
    "zigbee.adapter": [
      { value: "ezsp", label: "EZSP (Silicon Labs)" },
      { value: "znp", label: "ZNP (Texas Instruments)" },
      { value: "deconz", label: "deCONZ (Dresden Elektronik)" }
    ],
    "webserver.host": [
      { value: "0.0.0.0", label: "All interfaces (0.0.0.0)" },
      { value: "127.0.0.1", label: "Localhost only (127.0.0.1)" }
    ]
  };

  // Fields that are paths/addresses and should remain text inputs
  var PATH_FIELDS = {
    "image_capture.save_dir": true,
    "storage.buffer_db_path": true,
    "storage.backup_path": true,
    "zigbee.database_path": true,
    "zigbee.serial_port": true,
    "zigbee.device_name": true,
    "event_camera.device_path": true,
    "webserver.detections_dir": true,
    "lte.serial_port": true
  };

  // Field descriptions (shown as tooltips on hover)
  var FIELD_DESCRIPTIONS = {
    "still_camera.resolution_width": "Image resolution width in pixels",
    "still_camera.resolution_height": "Image resolution height in pixels",
    "still_camera.autofocus_mode": "Camera autofocus mode (continuous/manual/fixed)",
    "still_camera.jpeg_quality": "JPEG encoding quality (1-100)",
    "still_camera.camera_id": "Camera device index for multi-camera setups",
    "still_camera.exposure_us": "Exposure time in microseconds (0 = auto exposure)",
    "still_camera.gain_db": "Sensor gain in dB, similar to ISO (0 = auto gain)",
    "event_camera.event_threshold": "Number of events required to trigger detection",
    "event_camera.detection_window_ms": "Time window for event accumulation (ms)",
    "event_camera.min_cluster_area": "Minimum cluster size in pixels to count as detection",
    "event_camera.jpeg_quality": "JPEG encoding quality for event frames (1-100)",
    "event_camera.bias_diff_on": "ON-event contrast threshold (higher = less sensitive)",
    "event_camera.bias_diff_off": "OFF-event contrast threshold (higher = less sensitive)",
    "event_camera.bias_fo": "Source-follower bias (response time)",
    "event_camera.bias_hpf": "High-pass filter cutoff (temporal response)",
    "event_camera.bias_refr": "Refractory period (min time between events per pixel)",
    "image_capture.cooldown_seconds": "Minimum seconds between consecutive captures",
    "image_capture.zigbee_warmup_seconds": "Wait time for Zigbee sensor before capture",
    "power.night_mode_type": "fixed = fixed hours, location-based = sunrise/sunset",
    "power.awake_start_hour": "Hour when device wakes up (0-23)",
    "power.awake_end_hour": "Hour when device enters night mode (0-23)",
    "power.wlan_timeout_minutes": "Disable WLAN after this many minutes of inactivity",
    "power.energy_saving_wlan_minutes": "WLAN on-time per cycle in energy saving mode",
    "zigbee.network_channel": "Zigbee radio channel (11-26)",
    "upload.battery_soc_threshold": "Minimum battery % required to start upload",
    "storage.cleanup_after_days": "Delete old data after this many days",
    "webserver.camera_fps": "Target frames per second for live camera stream",
    "webserver.stream_width": "Downscale still camera to this width for streaming (0 = full resolution)"
  };

  // Convert snake_case to Title Case
  function toLabel(key) {
    return key.replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  // Detect field type from value
  function fieldType(value) {
    if (typeof value === "boolean") return "boolean";
    if (value === null || typeof value === "number") return "number";
    return "string";
  }

  // Current view mode
  var currentView = "form";
  var currentConfig = {};

  // Tab navigation
  document.querySelectorAll(".tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".tab").forEach(function (b) { b.classList.remove("active"); });
      document.querySelectorAll(".panel").forEach(function (p) { p.classList.remove("active"); });
      btn.classList.add("active");
      var panel = document.getElementById(btn.dataset.tab);
      if (panel) panel.classList.add("active");

      if (btn.dataset.tab === "camera") loadCameraInfo();
      if (btn.dataset.tab === "config") loadConfig();
      if (btn.dataset.tab === "status") loadStatus();
      if (btn.dataset.tab === "gallery") loadGallery(true);
      if (btn.dataset.tab === "logs") loadLogs();
    });
  });

  // View toggle
  document.getElementById("btn-view-form").addEventListener("click", function () {
    switchView("form");
  });
  document.getElementById("btn-view-json").addEventListener("click", function () {
    switchView("json");
  });

  function switchView(view) {
    currentView = view;
    document.getElementById("btn-view-form").classList.toggle("active", view === "form");
    document.getElementById("btn-view-json").classList.toggle("active", view === "json");
    document.getElementById("config-form").style.display = view === "form" ? "block" : "none";
    document.getElementById("config-json-view").style.display = view === "json" ? "block" : "none";

    if (view === "json") {
      // Sync form values to JSON
      document.getElementById("config-editor").value = JSON.stringify(collectFormValues(), null, 2);
    } else {
      // Sync JSON to form
      try {
        var parsed = JSON.parse(document.getElementById("config-editor").value);
        currentConfig = parsed;
        renderConfigForm(parsed);
      } catch (e) {
        // Keep current form if JSON is invalid
      }
    }
  }

  // --- Camera ---

  // Still camera controls
  var stillImg = document.getElementById("still-camera-img");
  var stillStreaming = false;
  var fpsTimer = null;

  function updateFps() {
    fetch("/api/camera/info")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var stillFps = document.getElementById("still-fps");
        var eventFps = document.getElementById("event-fps");
        if (stillStreaming && data.still_camera.fps > 0) {
          stillFps.textContent = data.still_camera.fps.toFixed(1) + " fps";
        } else {
          stillFps.textContent = "";
        }
        if (eventStreaming && data.event_camera.fps > 0) {
          eventFps.textContent = data.event_camera.fps.toFixed(1) + " fps";
        } else {
          eventFps.textContent = "";
        }
      })
      .catch(function () {});
  }

  function startFpsPolling() {
    if (!fpsTimer) {
      fpsTimer = setInterval(updateFps, 2000);
      updateFps();
    }
  }

  function stopFpsPolling() {
    if (!stillStreaming && !eventStreaming && fpsTimer) {
      clearInterval(fpsTimer);
      fpsTimer = null;
      document.getElementById("still-fps").textContent = "";
      document.getElementById("event-fps").textContent = "";
    }
  }

  document.getElementById("btn-still-stream").addEventListener("click", function () {
    if (stillStreaming) {
      stillImg.src = "";
      this.textContent = "Start Stream";
      stillStreaming = false;
      stopFpsPolling();
    } else {
      stillImg.src = "/api/camera/stream?" + Date.now();
      this.textContent = "Stop Stream";
      stillStreaming = true;
      startFpsPolling();
    }
  });

  document.getElementById("btn-still-snapshot").addEventListener("click", function () {
    stillImg.src = "/api/camera/snapshot?" + Date.now();
    if (stillStreaming) {
      document.getElementById("btn-still-stream").textContent = "Start Stream";
      stillStreaming = false;
      stopFpsPolling();
    }
  });

  // Event camera controls
  var eventImg = document.getElementById("event-camera-img");
  var eventStreaming = false;

  document.getElementById("btn-event-stream").addEventListener("click", function () {
    if (eventStreaming) {
      eventImg.src = "";
      this.textContent = "Start Stream";
      eventStreaming = false;
      stopFpsPolling();
    } else {
      eventImg.src = "/api/camera/event/stream?" + Date.now();
      this.textContent = "Stop Stream";
      eventStreaming = true;
      startFpsPolling();
    }
  });

  document.getElementById("btn-event-snapshot").addEventListener("click", function () {
    eventImg.src = "/api/camera/event/snapshot?" + Date.now();
    if (eventStreaming) {
      document.getElementById("btn-event-stream").textContent = "Start Stream";
      eventStreaming = false;
      stopFpsPolling();
    }
  });

  // Camera info - show/hide panels and set labels
  function loadCameraInfo() {
    fetch("/api/camera/info")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var stillPanel = document.getElementById("still-camera-panel");
        var eventPanel = document.getElementById("event-camera-panel");
        var dualContainer = document.querySelector(".camera-dual");

        // Show/hide panels based on availability
        stillPanel.style.display = data.still_camera.available ? "block" : "none";
        eventPanel.style.display = data.event_camera.available ? "block" : "none";

        // Set labels
        var stillLabel = CAMERA_TYPE_LABELS[data.still_camera.type] || data.still_camera.type;
        var eventLabel = CAMERA_TYPE_LABELS[data.event_camera.type] || data.event_camera.type;
        document.getElementById("still-camera-label").textContent = stillLabel;
        document.getElementById("event-camera-label").textContent = eventLabel;

        // Single column if only one camera available
        var bothAvailable = data.still_camera.available && data.event_camera.available;
        dualContainer.classList.toggle("single-camera", !bothAvailable);
      })
      .catch(function (err) { console.error("Camera info failed:", err); });
  }

  // Gallery
  var galleryOffset = 0;
  var GALLERY_LIMIT = 50;

  function loadGallery(reset) {
    if (reset) {
      galleryOffset = 0;
      document.getElementById("gallery-grid").innerHTML = "";
    }
    fetch("/api/gallery?limit=" + GALLERY_LIMIT + "&offset=" + galleryOffset)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var grid = document.getElementById("gallery-grid");
        data.crops.forEach(function (crop) {
          var img = document.createElement("img");
          img.src = crop.path;
          img.alt = crop.filename;
          img.title = crop.filename;
          img.loading = "lazy";
          grid.appendChild(img);
        });
        galleryOffset += data.crops.length;
        document.getElementById("btn-load-more").style.display =
          galleryOffset < data.total_crops ? "inline-block" : "none";
      })
      .catch(function (err) { console.error("Gallery load failed:", err); });
  }

  document.getElementById("btn-load-more").addEventListener("click", function () {
    loadGallery(false);
  });

  // Config - Form rendering
  function renderConfigForm(config) {
    var container = document.getElementById("config-form");
    container.innerHTML = "";

    var sections = Object.keys(config);
    sections.forEach(function (sectionKey) {
      var sectionData = config[sectionKey];
      if (typeof sectionData !== "object" || sectionData === null) return;

      var section = document.createElement("div");
      section.className = "config-section";

      var header = document.createElement("button");
      header.className = "config-section-header";
      header.textContent = SECTION_LABELS[sectionKey] || toLabel(sectionKey);
      header.setAttribute("data-section", sectionKey);

      var body = document.createElement("div");
      body.className = "config-section-body";
      body.id = "section-body-" + sectionKey;

      Object.keys(sectionData).forEach(function (fieldKey) {
        var value = sectionData[fieldKey];
        var type = fieldType(value);

        var field = document.createElement("div");
        field.className = "config-field";

        var label = document.createElement("label");
        label.textContent = toLabel(fieldKey);

        // Add tooltip from field descriptions
        var descKey = sectionKey + "." + fieldKey;
        if (FIELD_DESCRIPTIONS[descKey]) {
          label.title = FIELD_DESCRIPTIONS[descKey];
          label.style.cursor = "help";
        }

        var input;
        var optKey = sectionKey + "." + fieldKey;
        if (type === "boolean") {
          input = document.createElement("input");
          input.type = "checkbox";
          input.checked = !!value;
          input.setAttribute("data-section", sectionKey);
          input.setAttribute("data-field", fieldKey);
        } else if (type === "number") {
          input = document.createElement("input");
          input.type = "number";
          input.value = value !== null ? value : "";
          if (value === null) input.placeholder = "default";
          input.setAttribute("data-section", sectionKey);
          input.setAttribute("data-field", fieldKey);
        } else if (type === "string" && SELECT_OPTIONS[optKey] && !PATH_FIELDS[optKey]) {
          input = document.createElement("select");
          input.setAttribute("data-section", sectionKey);
          input.setAttribute("data-field", fieldKey);
          var options = SELECT_OPTIONS[optKey];
          var valueFound = false;
          options.forEach(function (opt) {
            var o = document.createElement("option");
            o.value = opt.value;
            o.textContent = opt.label;
            if (opt.value === value) { o.selected = true; valueFound = true; }
            input.appendChild(o);
          });
          // If current value is not in the predefined options, add it
          if (!valueFound && value) {
            var custom = document.createElement("option");
            custom.value = value;
            custom.textContent = value;
            custom.selected = true;
            input.appendChild(custom);
          }
        } else {
          input = document.createElement("input");
          input.type = "text";
          input.value = value !== null ? value : "";
          input.setAttribute("data-section", sectionKey);
          input.setAttribute("data-field", fieldKey);
        }

        field.appendChild(label);
        field.appendChild(input);
        body.appendChild(field);
      });

      // Toggle collapse
      header.addEventListener("click", function () {
        var b = document.getElementById("section-body-" + sectionKey);
        b.style.display = b.style.display === "none" ? "block" : "none";
      });

      section.appendChild(header);
      section.appendChild(body);
      container.appendChild(section);
    });
  }

  // Collect form values into config object
  function collectFormValues() {
    var config = {};
    var elements = document.querySelectorAll("#config-form input, #config-form select");
    elements.forEach(function (el) {
      var section = el.getAttribute("data-section");
      var field = el.getAttribute("data-field");
      if (!section || !field) return;

      if (!config[section]) config[section] = {};

      if (el.type === "checkbox") {
        config[section][field] = el.checked;
      } else if (el.type === "number") {
        config[section][field] = el.value === "" ? null : Number(el.value);
      } else {
        config[section][field] = el.value;
      }
    });
    return config;
  }

  // Config load
  function loadConfig() {
    fetch("/api/config")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        document.getElementById("config-version").textContent = data.version;
        currentConfig = data.config;
        document.getElementById("config-editor").value = JSON.stringify(data.config, null, 2);
        renderConfigForm(data.config);
        setConfigStatus("", "");
        loadSaasConnection();
      })
      .catch(function (err) { setConfigStatus("Failed to load config: " + err, "err"); });
  }

  document.getElementById("btn-save-config").addEventListener("click", function () {
    var configData;
    if (currentView === "json") {
      try {
        configData = JSON.parse(document.getElementById("config-editor").value);
      } catch (e) {
        setConfigStatus("Invalid JSON: " + e.message, "err");
        return;
      }
    } else {
      configData = collectFormValues();
    }

    fetch("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: configData }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        document.getElementById("config-version").textContent = data.version;
        currentConfig = data.config;
        document.getElementById("config-editor").value = JSON.stringify(data.config, null, 2);
        renderConfigForm(data.config);
        if (data.restart_pending) {
          setConfigStatus(
            "Saved (v" + data.version + "). Daemon is restarting to apply changes — " +
            "this may take up to 30 seconds. The page will reload automatically.",
            "warn"
          );
          setTimeout(function () { waitForRestart(); }, 3000);
        } else {
          var msg = data.pushed_to_saas
            ? "Saved and pushed to SaaS (v" + data.version + ")"
            : "Saved locally (v" + data.version + "). Will push to SaaS on next upload.";
          setConfigStatus(msg, "ok");
        }
      })
      .catch(function (err) { setConfigStatus("Save failed: " + err, "err"); });
  });

  document.getElementById("btn-pull-config").addEventListener("click", function () {
    setConfigStatus("Pulling from SaaS...", "");
    fetch("/api/config/pull", { method: "POST" })
      .then(function (r) { return r.json().then(function (d) { return { status: r.status, data: d }; }); })
      .then(function (result) {
        if (result.status >= 400) {
          setConfigStatus(result.data.error || "Pull failed", "err");
          return;
        }
        var data = result.data;
        document.getElementById("config-version").textContent = data.version;
        currentConfig = data.config;
        document.getElementById("config-editor").value = JSON.stringify(data.config, null, 2);
        renderConfigForm(data.config);
        if (data.restart_pending) {
          setConfigStatus(
            "Pulled v" + data.version + " from SaaS. Daemon is restarting to apply changes — " +
            "this may take up to 30 seconds. The page will reload automatically.",
            "warn"
          );
          setTimeout(function () { waitForRestart(); }, 3000);
        } else if (data.status === "updated") {
          setConfigStatus("Pulled v" + data.version + " from SaaS", "ok");
        } else if (data.status === "no_update") {
          setConfigStatus("Already up to date (v" + data.version + ")", "ok");
        } else {
          setConfigStatus("Config current (v" + data.version + ")", "ok");
        }
      })
      .catch(function (err) { setConfigStatus("Pull failed: " + err, "err"); });
  });

  document.getElementById("btn-reload-config").addEventListener("click", loadConfig);

  // --- SaaS Connection ---

  function loadSaasConnection() {
    fetch("/api/credentials")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        document.getElementById("saas-url").value = data.api_url || "";
        var keyInput = document.getElementById("saas-api-key");
        keyInput.value = "";
        keyInput.placeholder = data.api_key_masked
          ? "Current: " + data.api_key_masked + " (leave blank to keep)"
          : "Enter API key";
        setSaasStatus("", "");
      })
      .catch(function (err) { setSaasStatus("Failed to load: " + err, "err"); });
  }

  document.getElementById("saas-section-toggle").addEventListener("click", function () {
    var body = document.getElementById("saas-section-body");
    body.style.display = body.style.display === "none" ? "block" : "none";
  });

  document.getElementById("btn-save-saas").addEventListener("click", function () {
    var url = document.getElementById("saas-url").value.trim();
    if (!url) {
      setSaasStatus("Server URL is required", "err");
      return;
    }
    var payload = { api_url: url };
    var key = document.getElementById("saas-api-key").value.trim();
    if (key) payload.api_key = key;

    setSaasStatus("Saving...", "");
    fetch("/api/credentials", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json().then(function (d) { return { status: r.status, data: d }; }); })
      .then(function (result) {
        if (result.status >= 400) {
          setSaasStatus(result.data.error || "Save failed", "err");
          return;
        }
        setSaasStatus("Connection saved.", "ok");
        loadSaasConnection();
      })
      .catch(function (err) { setSaasStatus("Save failed: " + err, "err"); });
  });

  function setSaasStatus(msg, cls) {
    var el = document.getElementById("saas-status");
    el.textContent = msg;
    el.className = "status-msg" + (cls ? " " + cls : "");
  }

  function setConfigStatus(msg, cls) {
    var el = document.getElementById("config-status");
    el.textContent = msg;
    el.className = "status-msg" + (cls ? " " + cls : "");
  }

  function waitForRestart() {
    var attempts = 0;
    var maxAttempts = 30;
    var interval = setInterval(function () {
      attempts++;
      fetch("/api/status")
        .then(function (r) {
          if (r.ok) {
            clearInterval(interval);
            setConfigStatus("Daemon restarted successfully.", "ok");
            loadConfig();
          }
        })
        .catch(function () {
          if (attempts >= maxAttempts) {
            clearInterval(interval);
            setConfigStatus("Daemon restart is taking longer than expected. Please refresh the page manually.", "err");
          }
        });
    }, 2000);
  }

  // Status
  function loadStatus() {
    fetch("/api/status")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        document.getElementById("status-output").textContent = JSON.stringify(data, null, 2);
      })
      .catch(function (err) {
        document.getElementById("status-output").textContent = "Error: " + err;
      });
  }

  document.getElementById("btn-refresh-status").addEventListener("click", loadStatus);

  // Logs
  var logAutoRefreshTimer = null;
  var LOG_LEVEL_CLASSES = {
    "ERROR": "log-error",
    "WARNING": "log-warning",
    "INFO": "log-info",
    "DEBUG": "log-debug"
  };

  function loadLogs() {
    var level = document.getElementById("log-level-filter").value;
    var url = "/api/logs?limit=200";
    if (level) url += "&level=" + level;

    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var output = document.getElementById("log-output");
        if (!data.logs || data.logs.length === 0) {
          output.innerHTML = "No log entries.";
          return;
        }
        var html = "";
        data.logs.forEach(function (entry) {
          var cls = LOG_LEVEL_CLASSES[entry.level] || "";
          var line = "[" + entry.level.padEnd(7) + "] " + entry.name + ": " + entry.message;
          if (cls) {
            html += '<span class="' + cls + '">' + escapeHtml(line) + "</span>\n";
          } else {
            html += escapeHtml(line) + "\n";
          }
        });
        output.innerHTML = html;
        output.scrollTop = output.scrollHeight;
      })
      .catch(function (err) {
        document.getElementById("log-output").textContent = "Error loading logs: " + err;
      });
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  document.getElementById("btn-refresh-logs").addEventListener("click", loadLogs);
  document.getElementById("log-level-filter").addEventListener("change", loadLogs);
  document.getElementById("log-auto-refresh").addEventListener("change", function () {
    if (this.checked) {
      loadLogs();
      logAutoRefreshTimer = setInterval(loadLogs, 5000);
    } else {
      if (logAutoRefreshTimer) {
        clearInterval(logAutoRefreshTimer);
        logAutoRefreshTimer = null;
      }
    }
  });

  // Initial load
  loadConfig();
  loadCameraInfo();
})();
