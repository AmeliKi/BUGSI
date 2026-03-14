// BUGSI Device Web UI

(function () {
  "use strict";

  // Section display names
  var SECTION_LABELS = {
    camera: "Camera",
    telemetry: "Telemetry",
    upload: "Upload",
    power: "Power Management",
    storage: "Storage",
    webserver: "Web Server"
  };

  // Convert snake_case to Title Case
  function toLabel(key) {
    return key.replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  // Detect field type from value
  function fieldType(value) {
    if (typeof value === "boolean") return "boolean";
    if (typeof value === "number") return "number";
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

      if (btn.dataset.tab === "config") loadConfig();
      if (btn.dataset.tab === "status") loadStatus();
      if (btn.dataset.tab === "gallery") loadGallery(true);
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

  // Camera
  var cameraImg = document.getElementById("camera-img");
  var streaming = false;

  document.getElementById("btn-stream").addEventListener("click", function () {
    if (streaming) {
      cameraImg.src = "";
      this.textContent = "Start Stream";
      streaming = false;
    } else {
      cameraImg.src = "/api/camera/stream?" + Date.now();
      this.textContent = "Stop Stream";
      streaming = true;
    }
  });

  document.getElementById("btn-snapshot").addEventListener("click", function () {
    cameraImg.src = "/api/camera/snapshot?" + Date.now();
    if (streaming) {
      document.getElementById("btn-stream").textContent = "Start Stream";
      streaming = false;
    }
  });

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

        var input;
        if (type === "boolean") {
          input = document.createElement("input");
          input.type = "checkbox";
          input.checked = !!value;
          input.setAttribute("data-section", sectionKey);
          input.setAttribute("data-field", fieldKey);
        } else if (type === "number") {
          input = document.createElement("input");
          input.type = "number";
          input.value = value;
          input.setAttribute("data-section", sectionKey);
          input.setAttribute("data-field", fieldKey);
        } else {
          input = document.createElement("input");
          input.type = "text";
          input.value = value;
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
    var inputs = document.querySelectorAll("#config-form input");
    inputs.forEach(function (input) {
      var section = input.getAttribute("data-section");
      var field = input.getAttribute("data-field");
      if (!section || !field) return;

      if (!config[section]) config[section] = {};

      if (input.type === "checkbox") {
        config[section][field] = input.checked;
      } else if (input.type === "number") {
        config[section][field] = input.value === "" ? 0 : Number(input.value);
      } else {
        config[section][field] = input.value;
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
        var msg = data.pushed_to_saas
          ? "Saved and pushed to SaaS (v" + data.version + ")"
          : "Saved locally (v" + data.version + "). Will push to SaaS on next upload.";
        setConfigStatus(msg, "ok");
      })
      .catch(function (err) { setConfigStatus("Save failed: " + err, "err"); });
  });

  document.getElementById("btn-reload-config").addEventListener("click", loadConfig);

  function setConfigStatus(msg, cls) {
    var el = document.getElementById("config-status");
    el.textContent = msg;
    el.className = "status-msg" + (cls ? " " + cls : "");
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

  // Initial load
  loadConfig();
})();
