/**
 * Enterprise ESG Reports & PDF Export Frontend (Member 5 Phase 5E - Stage 2)
 *
 * Connects to live Member 5 reporting APIs:
 * - GET  /api/platform/reports/types        (dynamic catalog of 6 report templates)
 * - POST /api/platform/reports/preview      (live multi-tenant JSON preview)
 * - POST /api/platform/reports/export-pdf   (pure in-memory streaming PDF binary download)
 *
 * Enforces:
 * - Role-Based Access Control (RBAC) & tenant isolation
 * - Honest metric reporting: unassessed suppliers strictly separated from Low risk
 * - Missing metrics rendered as 'Pending Assessment' or null, never 0 or 80
 * - Pure in-memory streaming PDF export via Blob/object URL handling
 * - Comprehensive UI states: loading, previewing, exporting, success, error, unauthorized
 */

(function () {
  "use strict";

  // DOM Container
  const appContainer = document.getElementById("page-app");
  const refreshBtn = document.getElementById("page-refresh-action");

  // State
  let availableTypes = [];
  let selectedTypeId = "ENTERPRISE_SUMMARY";
  let selectedPeriod = "FY 2025–26";
  let selectedCategory = "All";
  let selectedSections = new Set();
  let executiveNotes = "";
  let currentPreview = null;
  let isExporting = false;
  let isPreviewing = false;

  // Formatting helpers
  function escape(str) {
    if (window.escapeHtml) return window.escapeHtml(str);
    return String(str ?? "").replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[m];
    });
  }

  function formatDateTime(isoStr) {
    if (!isoStr) return "—";
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      });
    } catch (_) {
      return isoStr;
    }
  }

  function renderRiskBadge(riskStr) {
    const r = String(riskStr || "").trim().toUpperCase();
    if (r === "CRITICAL") {
      return `<span class="badge badge-high" style="background:#fee2e2;color:#991b1b;border-color:#f87171;">CRITICAL</span>`;
    }
    if (r === "HIGH" || r.includes("HIGH")) {
      return `<span class="badge badge-high">HIGH</span>`;
    }
    if (r === "MEDIUM" || r === "MODERATE" || r.includes("MODERATE") || r.includes("MEDIUM")) {
      return `<span class="badge badge-medium">MODERATE</span>`;
    }
    if (r === "LOW" || r.includes("LOW")) {
      return `<span class="badge badge-low">LOW</span>`;
    }
    if (r.includes("NOT_ASSESSED") || r.includes("NOT ASSESSED") || r.includes("PENDING")) {
      return `<span class="badge badge-neutral" style="background:#f1f5f9;color:#475569;border-color:#cbd5e1;font-weight:700;">NOT ASSESSED</span>`;
    }
    return `<span class="badge badge-neutral">${escape(riskStr || "PENDING")}</span>`;
  }

  // ─── Main View Initializer ──────────────────────────────────────────────────

  async function init() {
    if (!appContainer) return;
    renderLoading("Loading available report templates from platform engine...");

    try {
      const types = await window.ESGApi.reportTypes();
      if (!Array.isArray(types) || types.length === 0) {
        throw new Error("No report templates returned by reporting service.");
      }
      availableTypes = types;

      // Select default report type
      const defaultType = availableTypes.find(function (t) {
        return t.id === "ENTERPRISE_SUMMARY";
      }) || availableTypes[0];
      selectedTypeId = defaultType.id;
      initSectionsForType(defaultType);

      renderApp();

      // Trigger default preview on initial load
      await generatePreview();
    } catch (err) {
      renderError("Failed to initialize reporting engine", err.message);
    }
  }

  function initSectionsForType(typeDef) {
    selectedSections.clear();
    if (typeDef && Array.isArray(typeDef.default_sections)) {
      typeDef.default_sections.forEach(function (sec) {
        selectedSections.add(sec);
      });
    }
  }

  function getSelectedTypeDef() {
    return availableTypes.find(function (t) {
      return t.id === selectedTypeId;
    }) || availableTypes[0];
  }

  // ─── UI Rendering: App Shell & Configuration ───────────────────────────────

  function renderLoading(msg) {
    appContainer.innerHTML = `
      <div class="card" style="padding:48px 24px;text-align:center;">
        <div class="loading-state">
          <div class="spinner"></div>
          <p style="margin-top:12px;font-weight:600;color:#24322e;">${escape(msg || "Loading...")}</p>
        </div>
      </div>
    `;
  }

  function renderError(title, detail) {
    const isAuth = detail && (detail.includes("401") || detail.includes("Unauthorized") || detail.includes("Forbidden"));
    appContainer.innerHTML = `
      <div class="card" style="padding:32px 24px;">
        <div class="alert alert-error">
          <div style="font-weight:700;font-size:14px;margin-bottom:6px;">${escape(title)}</div>
          <div>${escape(detail)}</div>
          ${
            isAuth
              ? `<div style="margin-top:12px;"><a href="login.html" class="btn btn-primary" style="padding:6px 12px;font-size:11px;">Log In Again</a></div>`
              : `<div style="margin-top:12px;"><button class="btn btn-secondary" id="btn-retry-init" style="padding:6px 12px;font-size:11px;">Retry</button></div>`
          }
        </div>
      </div>
    `;
    const retryBtn = document.getElementById("btn-retry-init");
    if (retryBtn) retryBtn.onclick = init;
  }

  function renderApp() {
    const currentType = getSelectedTypeDef();
    const supportsCategory = currentType && currentType.supported_filters && currentType.supported_filters.includes("category");

    appContainer.innerHTML = `
      <div class="grid-2" style="align-items:start;">
        <!-- Left: Configuration Card -->
        <div class="card" id="report-config-card">
          <div class="section-head">
            <div>
              <h2>Report Configuration</h2>
              <p>Select template, reporting period and audit scope.</p>
            </div>
            <span class="badge badge-success">LIVE PLATFORM ENGINE</span>
          </div>

          <!-- Report Type Selection -->
          <div class="field" style="margin-bottom:14px;">
            <label for="cfg-report-type">Report Template</label>
            <select id="cfg-report-type" class="filter">
              ${availableTypes
                .map(function (t) {
                  return `<option value="${escape(t.id)}" ${t.id === selectedTypeId ? "selected" : ""}>${escape(t.title)} (${escape(t.category)})</option>`;
                })
                .join("")}
            </select>
            <div id="cfg-type-desc" style="font-size:11px;color:#64716d;margin-top:4px;line-height:1.4;">
              ${escape(currentType ? currentType.description : "")}
            </div>
          </div>

          <!-- Reporting Period Selection -->
          <div class="field" style="margin-bottom:14px;">
            <label for="cfg-reporting-period">Reporting Period</label>
            <select id="cfg-reporting-period" class="filter">
              <option value="FY 2025–26" ${selectedPeriod === "FY 2025–26" ? "selected" : ""}>FY 2025–26 (Current Active Fiscal Year)</option>
              <option value="FY 2024–25" ${selectedPeriod === "FY 2024–25" ? "selected" : ""}>FY 2024–25 (Prior Fiscal Year)</option>
              <option value="FY 2023–24" ${selectedPeriod === "FY 2023–24" ? "selected" : ""}>FY 2023–24 (Historical Baseline)</option>
              <option value="FY 2026–27 (Projected)" ${selectedPeriod === "FY 2026–27 (Projected)" ? "selected" : ""}>FY 2026–27 (Projected Roadmap)</option>
            </select>
            <div style="font-size:10px;color:#7e8992;margin-top:4px;line-height:1.35;">
              <i>Transparency Notice:</i> Supplier profiles and verified compliance evidence in the platform database reflect current lifecycle status; historical fiscal-year partitioning is not supported for these records.
            </div>
          </div>

          <!-- Category Filter (if supported) -->
          ${
            supportsCategory
              ? `
            <div class="field" style="margin-bottom:14px;">
              <label for="cfg-category">ESG Pillar Filter</label>
              <select id="cfg-category" class="filter">
                <option value="All" ${selectedCategory === "All" ? "selected" : ""}>All Pillars (Comprehensive)</option>
                <option value="Environmental" ${selectedCategory === "Environmental" ? "selected" : ""}>Environmental Only</option>
                <option value="Social" ${selectedCategory === "Social" ? "selected" : ""}>Social Only</option>
                <option value="Governance" ${selectedCategory === "Governance" ? "selected" : ""}>Governance Only</option>
              </select>
            </div>
          `
              : ""
          }

          <!-- Section Customization -->
          <div class="field" style="margin-bottom:14px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
              <label style="margin:0;">Included Report Sections</label>
              <div style="display:flex;gap:8px;">
                <button type="button" class="btn btn-ghost" id="btn-select-all-sec" style="padding:2px 6px;font-size:10px;">Select All</button>
                <button type="button" class="btn btn-ghost" id="btn-clear-sec" style="padding:2px 6px;font-size:10px;">Clear</button>
              </div>
            </div>
            <div id="cfg-sections-list" style="display:grid;gap:8px;background:#f8faf9;border:1px solid #e2e8e4;border-radius:8px;padding:12px;max-height:220px;overflow-y:auto;">
              ${renderSectionCheckboxes(currentType)}
            </div>
          </div>

          <!-- Optional Executive Notes -->
          <div class="field" style="margin-bottom:18px;">
            <label for="cfg-notes">Executive Remarks / Audit Scope Notes (Optional)</label>
            <textarea id="cfg-notes" rows="2" placeholder="e.g., Prepared for Q1 Board Sustainability Committee review..." style="font-size:12px;resize:vertical;">${escape(executiveNotes)}</textarea>
          </div>

          <!-- Action Buttons -->
          <div class="toolbar" style="gap:10px;">
            <button class="btn btn-primary" id="btn-generate-preview" ${isPreviewing ? "disabled" : ""}>
              ${isPreviewing ? `<span class="spinner" style="width:14px;height:14px;border-width:2px;margin:0 4px 0 0;display:inline-block;vertical-align:middle;"></span> Generating Preview...` : `<span class="icon">▤</span> Generate Preview`}
            </button>
            <button class="btn btn-secondary" id="btn-export-pdf" ${isExporting || !currentPreview ? "disabled" : ""}>
              ${isExporting ? `<span class="spinner" style="width:14px;height:14px;border-width:2px;margin:0 4px 0 0;display:inline-block;vertical-align:middle;"></span> Compiling PDF...` : `<span class="icon">↓</span> Export PDF Document`}
            </button>
          </div>
        </div>

        <!-- Right: Live Report Preview Card -->
        <div class="card" id="report-preview-card">
          <div class="section-head">
            <div>
              <h2>Live Executive Preview</h2>
              <p id="preview-meta-sub">Structured platform report rendering before binary export.</p>
            </div>
            <span class="badge badge-processing" id="preview-status-badge">Preview</span>
          </div>

          <!-- Preview Content Scroll Container -->
          <div class="report-preview" id="report-preview-container" style="background:#fff;border:1px solid #e2e7e4;border-radius:10px;overflow:hidden;min-height:550px;">
            <div class="loading-state" style="padding:80px 20px;">
              <div class="spinner"></div>
              <div class="muted">Initializing report preview...</div>
            </div>
          </div>

          <!-- Preview Footer Toolbar -->
          <div class="toolbar" style="margin-top:14px;justify-content:space-between;">
            <div style="font-size:11px;color:#7e8992;" id="preview-footer-timestamp">—</div>
            <div style="display:flex;gap:8px;">
              <button class="btn btn-secondary" id="btn-scroll-preview" style="padding:6px 12px;font-size:11px;"><span class="icon">↑</span> Top</button>
              <button class="btn btn-primary" id="btn-footer-export-pdf" style="padding:6px 14px;font-size:11px;" ${isExporting || !currentPreview ? "disabled" : ""}>
                ${isExporting ? `Exporting...` : `Download PDF`}
              </button>
            </div>
          </div>
        </div>
      </div>
    `;

    bindConfigEvents();
  }

  function renderSectionCheckboxes(typeDef) {
    if (!typeDef || !Array.isArray(typeDef.default_sections)) return `<div class="muted">No sections available.</div>`;
    return typeDef.default_sections
      .map(function (secKey) {
        const readable = secKey.replace(/_/g, " ").replace(/\b\w/g, function (l) {
          return l.toUpperCase();
        });
        const isChecked = selectedSections.has(secKey);
        return `
        <label style="display:flex;gap:9px;align-items:center;font-size:12px;cursor:pointer;">
          <input type="checkbox" class="cfg-sec-chk" data-section="${escape(secKey)}" ${isChecked ? "checked" : ""}>
          <span>${escape(readable)}</span>
        </label>
      `;
      })
      .join("");
  }

  // ─── Event Bindings ─────────────────────────────────────────────────────────

  function bindConfigEvents() {
    const typeSelect = document.getElementById("cfg-report-type");
    if (typeSelect) {
      typeSelect.onchange = function () {
        selectedTypeId = this.value;
        const tDef = getSelectedTypeDef();
        initSectionsForType(tDef);
        renderApp();
        generatePreview();
      };
    }

    const periodSelect = document.getElementById("cfg-reporting-period");
    if (periodSelect) {
      periodSelect.onchange = function () {
        selectedPeriod = this.value;
      };
    }

    const catSelect = document.getElementById("cfg-category");
    if (catSelect) {
      catSelect.onchange = function () {
        selectedCategory = this.value;
      };
    }

    const notesArea = document.getElementById("cfg-notes");
    if (notesArea) {
      notesArea.oninput = function () {
        executiveNotes = this.value;
      };
    }

    const secList = document.getElementById("cfg-sections-list");
    if (secList) {
      secList.onchange = function (e) {
        if (e.target && e.target.classList.contains("cfg-sec-chk")) {
          const sec = e.target.getAttribute("data-section");
          if (e.target.checked) {
            selectedSections.add(sec);
          } else {
            selectedSections.delete(sec);
          }
        }
      };
    }

    const selectAllBtn = document.getElementById("btn-select-all-sec");
    if (selectAllBtn) {
      selectAllBtn.onclick = function () {
        const tDef = getSelectedTypeDef();
        if (tDef && Array.isArray(tDef.default_sections)) {
          tDef.default_sections.forEach(function (s) {
            selectedSections.add(s);
          });
        }
        const chks = document.querySelectorAll(".cfg-sec-chk");
        chks.forEach(function (c) {
          c.checked = true;
        });
      };
    }

    const clearSecBtn = document.getElementById("btn-clear-sec");
    if (clearSecBtn) {
      clearSecBtn.onclick = function () {
        selectedSections.clear();
        const chks = document.querySelectorAll(".cfg-sec-chk");
        chks.forEach(function (c) {
          c.checked = false;
        });
      };
    }

    const previewBtn = document.getElementById("btn-generate-preview");
    if (previewBtn) {
      previewBtn.onclick = function () {
        generatePreview();
      };
    }

    const exportBtn = document.getElementById("btn-export-pdf");
    if (exportBtn) {
      exportBtn.onclick = function () {
        executePdfExport();
      };
    }

    const footerExportBtn = document.getElementById("btn-footer-export-pdf");
    if (footerExportBtn) {
      footerExportBtn.onclick = function () {
        executePdfExport();
      };
    }

    const scrollTopBtn = document.getElementById("btn-scroll-preview");
    if (scrollTopBtn) {
      scrollTopBtn.onclick = function () {
        const c = document.getElementById("report-preview-container");
        if (c) c.scrollTo({ top: 0, behavior: "smooth" });
      };
    }
  }

  // ─── Live Preview Execution ─────────────────────────────────────────────────

  async function generatePreview() {
    const previewContainer = document.getElementById("report-preview-container");
    const previewBadge = document.getElementById("preview-status-badge");
    const exportBtn = document.getElementById("btn-export-pdf");
    const footerExportBtn = document.getElementById("btn-footer-export-pdf");
    const previewBtn = document.getElementById("btn-generate-preview");

    if (!previewContainer) return;

    if (selectedSections.size === 0) {
      if (window.toast) window.toast("Please select at least one report section to include.");
      return;
    }

    isPreviewing = true;
    if (previewBtn) {
      previewBtn.disabled = true;
      previewBtn.innerHTML = `<span class="spinner" style="width:14px;height:14px;border-width:2px;margin:0 4px 0 0;display:inline-block;vertical-align:middle;"></span> Generating...`;
    }
    if (previewBadge) {
      previewBadge.className = "badge badge-processing";
      previewBadge.textContent = "Compiling...";
    }

    previewContainer.innerHTML = `
      <div class="loading-state" style="padding:80px 20px;">
        <div class="spinner"></div>
        <div class="muted" style="font-weight:600;">Querying live multi-member metrics and compiling report preview...</div>
      </div>
    `;

    const payload = {
      report_type: selectedTypeId,
      reporting_period: selectedPeriod,
      category: selectedCategory === "All" ? null : selectedCategory,
      include_sections: Array.from(selectedSections),
      notes: executiveNotes.trim() || null,
    };

    try {
      const data = await window.ESGApi.reportPreview(payload);
      currentPreview = data;

      renderPreviewContent(data);

      if (previewBadge) {
        previewBadge.className = "badge badge-success";
        previewBadge.textContent = "Ready to Export";
      }
      if (exportBtn) exportBtn.disabled = false;
      if (footerExportBtn) footerExportBtn.disabled = false;

      const footerTs = document.getElementById("preview-footer-timestamp");
      if (footerTs) {
        footerTs.textContent = `Generated: ${formatDateTime(data.generated_at)} • Tenant ID #${data.organization_id}`;
      }
    } catch (err) {
      currentPreview = null;
      if (previewBadge) {
        previewBadge.className = "badge badge-high";
        previewBadge.textContent = "Error";
      }
      if (exportBtn) exportBtn.disabled = true;
      if (footerExportBtn) footerExportBtn.disabled = true;

      previewContainer.innerHTML = `
        <div style="padding:32px 24px;">
          <div class="alert alert-error">
            <div style="font-weight:700;margin-bottom:4px;">Failed to generate report preview</div>
            <div>${escape(err.message)}</div>
            <div style="margin-top:12px;">
              <button class="btn btn-secondary" id="btn-preview-retry" style="font-size:11px;padding:6px 12px;">Retry Preview</button>
            </div>
          </div>
        </div>
      `;
      const retryBtn = document.getElementById("btn-preview-retry");
      if (retryBtn) retryBtn.onclick = generatePreview;
    } finally {
      isPreviewing = false;
      if (previewBtn) {
        previewBtn.disabled = false;
        previewBtn.innerHTML = `<span class="icon">▤</span> Generate Preview`;
      }
    }
  }

  function renderPreviewContent(data) {
    const c = document.getElementById("report-preview-container");
    if (!c) return;

    let html = `
      <!-- Cover & Document Header -->
      <div class="report-cover" style="background:#fcfdfc;padding:24px 28px;border-bottom:2px solid #e2e8e4;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:8px;">
          <div>
            <div class="eyebrow" style="color:#1d7959;font-weight:800;letter-spacing:0.12em;">${escape(data.report_type.replace(/_/g, " "))}</div>
            <h1 style="font-size:22px;margin:2px 0 4px 0;color:#153f32;">${escape(data.title)}</h1>
            <div style="font-size:13px;font-weight:600;color:#475569;">
              ${escape(data.organization_name)} • <span style="color:#16825a;">${escape(data.reporting_period)}</span>
            </div>
          </div>
          <div style="text-align:right;">
            <span class="badge badge-neutral" style="font-size:11px;">Author: ${escape(data.generated_by_user)} (${escape(data.generated_by_role)})</span>
            <div style="font-size:10px;color:#7e8992;margin-top:4px;">${formatDateTime(data.generated_at)}</div>
          </div>
        </div>
      </div>

      <!-- Executive Summary -->
      <div class="report-section" style="padding:20px 28px;border-bottom:1px solid #edf0ee;background:#fafcfb;">
        <div style="font-weight:750;font-size:13px;color:#153f32;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.04em;">Executive Summary</div>
        <p style="font-size:12.5px;line-height:1.6;color:#2c3b35;margin:0;">
          ${escape(data.executive_summary)}
        </p>
      </div>

      <!-- Domain KPI Summary Grid -->
      ${
        Array.isArray(data.kpi_summary) && data.kpi_summary.length > 0
          ? `
        <div class="report-section" style="padding:20px 28px;border-bottom:1px solid #edf0ee;">
          <div style="font-weight:750;font-size:12px;color:#153f32;margin-bottom:12px;text-transform:uppercase;letter-spacing:0.04em;">Key Performance Metrics</div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:12px;">
            ${data.kpi_summary
              .map(function (kpi) {
                const scoreDisplay = kpi.score !== null && kpi.score !== undefined ? `${kpi.score.toFixed(1)}/100` : `<i style="color:#94a3b8;font-size:13px;">Pending Assessment</i>`;
                const statusBadge =
                  kpi.status === "ASSESSED"
                    ? `<span class="badge badge-success" style="font-size:9px;">ASSESSED</span>`
                    : kpi.status === "NO_DATA" || kpi.status === "NO_ACTIVE_SESSION"
                    ? `<span class="badge badge-neutral" style="font-size:9px;">NO SESSION</span>`
                    : `<span class="badge badge-medium" style="font-size:9px;">PENDING</span>`;
                return `
                <div style="background:#fff;border:1px solid #e5eae7;border-radius:8px;padding:12px 14px;box-shadow:0 1px 4px rgba(0,0,0,0.02);">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <div style="font-size:11px;color:#64748b;font-weight:600;">${escape(kpi.label)}</div>
                    ${statusBadge}
                  </div>
                  <div style="font-size:18px;font-weight:800;color:#153f32;">${scoreDisplay}</div>
                  <div style="font-size:10px;color:#94a3b8;margin-top:4px;">${escape(kpi.source)}</div>
                </div>
              `;
              })
              .join("")}
          </div>
        </div>
      `
          : ""
      }
    `;

    // Dynamic Sections
    if (Array.isArray(data.sections) && data.sections.length > 0) {
      data.sections.forEach(function (sec) {
        html += renderSectionBlock(sec);
      });
    } else {
      html += `
        <div class="report-section" style="padding:40px 28px;text-align:center;">
          <div class="empty-state" style="padding:28px;">
            <p style="margin:0;color:#64748b;">No sections selected or data available for this report view.</p>
          </div>
        </div>
      `;
    }

    // Audit Disclosures & Limitations Box
    if (Array.isArray(data.disclosures_and_limitations) && data.disclosures_and_limitations.length > 0) {
      html += `
        <div class="report-section" style="padding:24px 28px;background:#f8faf9;border-top:1px solid #e2e8e4;">
          <div style="font-weight:750;font-size:12px;color:#2a5c4b;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.04em;">
            Audit Disclosures, Data Provenance & Methodological Limitations
          </div>
          <div style="background:#fff;border:1px solid #d5ded8;border-radius:8px;padding:14px 16px;">
            <ul style="margin:0;padding-left:18px;font-size:11px;color:#475569;line-height:1.6;">
              ${data.disclosures_and_limitations
                .map(function (d) {
                  if (d.includes(":")) {
                    const parts = d.split(/:\s*(.+)/);
                    return `<li style="margin-bottom:4px;"><b>${escape(parts[0])}:</b> ${escape(parts[1])}</li>`;
                  }
                  return `<li style="margin-bottom:4px;">${escape(d)}</li>`;
                })
                .join("")}
            </ul>
          </div>
        </div>
      `;
    }

    c.innerHTML = html;
  }

  function renderSectionBlock(sec) {
    let contentHtml = "";

    if (sec.content_type === "table" && Array.isArray(sec.table_headers) && Array.isArray(sec.table_rows)) {
      if (sec.table_rows.length === 0) {
        contentHtml = `
          <div class="empty-state" style="padding:20px;font-size:12px;">
            No records found under tenant boundary for this section.
          </div>
        `;
      } else {
        contentHtml = `
          <div class="table-wrap" style="border:1px solid #e5eae7;border-radius:8px;overflow-x:auto;">
            <table class="data-table" style="width:100%;font-size:11.5px;">
              <thead>
                <tr>
                  ${sec.table_headers
                    .map(function (h) {
                      return `<th style="background:#f8faf9;padding:9px 12px;color:#475569;font-weight:700;">${escape(h)}</th>`;
                    })
                    .join("")}
                </tr>
              </thead>
              <tbody>
                ${sec.table_rows
                  .map(function (row) {
                    return `
                    <tr>
                      ${row
                        .map(function (cell, idx) {
                          const strVal = cell !== null && cell !== undefined ? String(cell) : "—";
                          const isRiskCol =
                            sec.table_headers[idx] &&
                            (sec.table_headers[idx].toLowerCase().includes("risk") || sec.table_headers[idx].toLowerCase().includes("severity"));
                          const formatted = isRiskCol ? renderRiskBadge(strVal) : escape(strVal);
                          return `<td style="padding:9px 12px;border-bottom:1px solid #f1f5f3;">${formatted}</td>`;
                        })
                        .join("")}
                    </tr>
                  `;
                  })
                  .join("")}
              </tbody>
            </table>
          </div>
        `;
      }
    } else if (sec.content_type === "text" && sec.text_content) {
      contentHtml = `<p style="font-size:12px;line-height:1.6;color:#334155;margin:0;">${escape(sec.text_content)}</p>`;
    } else {
      contentHtml = `<div class="muted" style="font-size:12px;">Section rendered as summary.</div>`;
    }

    return `
      <div class="report-section" style="padding:20px 28px;border-bottom:1px solid #edf0ee;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
          <h3 style="font-size:14px;color:#153f32;font-weight:750;margin:0;">${escape(sec.title)}</h3>
          ${sec.note ? `<span style="font-size:10px;color:#7e8992;font-style:italic;">${escape(sec.note)}</span>` : ""}
        </div>
        ${contentHtml}
      </div>
    `;
  }

  // ─── PDF Export Execution (Blob & Object URL Handling) ─────────────────────

  async function executePdfExport() {
    if (isExporting) return;

    const exportBtn = document.getElementById("btn-export-pdf");
    const footerExportBtn = document.getElementById("btn-footer-export-pdf");
    const previewBadge = document.getElementById("preview-status-badge");

    if (selectedSections.size === 0) {
      if (window.toast) window.toast("Please select at least one section before exporting.");
      return;
    }

    isExporting = true;
    if (exportBtn) {
      exportBtn.disabled = true;
      exportBtn.innerHTML = `<span class="spinner" style="width:14px;height:14px;border-width:2px;margin:0 4px 0 0;display:inline-block;vertical-align:middle;"></span> Generating PDF...`;
    }
    if (footerExportBtn) {
      footerExportBtn.disabled = true;
      footerExportBtn.textContent = "Exporting PDF...";
    }
    if (previewBadge) {
      previewBadge.className = "badge badge-processing";
      previewBadge.textContent = "Compiling PDF...";
    }

    const payload = {
      report_type: selectedTypeId,
      reporting_period: selectedPeriod,
      category: selectedCategory === "All" ? null : selectedCategory,
      include_sections: Array.from(selectedSections),
      notes: executiveNotes.trim() || null,
    };

    try {
      // Stream binary blob from backend
      const result = await window.ESGApi.reportExportPdf(payload);

      // Verify blob type and non-empty content
      if (!result.blob || result.blob.size === 0) {
        throw new Error("Received empty or corrupt PDF binary from export service.");
      }

      // Safe in-browser download trigger via Object URL
      const blobUrl = window.URL.createObjectURL(result.blob);
      const downloadLink = document.createElement("a");
      downloadLink.style.display = "none";
      downloadLink.href = blobUrl;
      downloadLink.download = result.filename || `${selectedTypeId.toLowerCase()}_report.pdf`;

      document.body.appendChild(downloadLink);
      downloadLink.click();
      document.body.removeChild(downloadLink);

      // Clean up object URL after dispatch
      setTimeout(function () {
        window.URL.revokeObjectURL(blobUrl);
      }, 2000);

      // ONLY display success after the download response and blob have succeeded
      if (window.toast) {
        window.toast(`Report successfully downloaded as "${downloadLink.download}" (${(result.blob.size / 1024).toFixed(1)} KB)`);
      }
      if (previewBadge) {
        previewBadge.className = "badge badge-success";
        previewBadge.textContent = "PDF Exported";
      }
    } catch (err) {
      if (window.toast) {
        window.toast(`Export failed: ${err.message}`);
      }
      if (previewBadge) {
        previewBadge.className = "badge badge-high";
        previewBadge.textContent = "Export Failed";
      }
      alert(`PDF Export Error: ${err.message}\n\nPlease check that your session is active and retry.`);
    } finally {
      isExporting = false;
      if (exportBtn) {
        exportBtn.disabled = false;
        exportBtn.innerHTML = `<span class="icon">↓</span> Export PDF Document`;
      }
      if (footerExportBtn) {
        footerExportBtn.disabled = false;
        footerExportBtn.textContent = "Download PDF";
      }
    }
  }

  // Hook global refresh button
  if (refreshBtn) {
    refreshBtn.onclick = function () {
      init();
    };
  }

  // Initialize once DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
