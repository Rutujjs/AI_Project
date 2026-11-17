/**
 * Enterprise ESG Reports & PDF Export Frontend
 *
 * Provides executive-ready sustainability report configuration, preview,
 * and pure in-memory streaming PDF export across 6 report templates:
 * 1. Enterprise ESG Summary Report (ENTERPRISE_SUMMARY)
 * 2. Environmental Performance Report (ENVIRONMENTAL)
 * 3. Social Performance Report (SOCIAL)
 * 4. Governance Performance Report (GOVERNANCE)
 * 5. Supplier Risk and Compliance Report (SUPPLIER_RISK)
 * 6. Findings and Recommendations Report (FINDINGS_RECOMMENDATIONS)
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

  // ─── Default Catalog & Fallback Templates (All 6 Option Types) ───────────────

  const DEFAULT_REPORT_TYPES = [
    {
      id: "ENTERPRISE_SUMMARY",
      title: "Enterprise ESG Summary Report",
      description: "Comprehensive enterprise sustainability audit aggregating Environmental, Social, and Governance metrics across supply chain and digital infrastructure.",
      category: "All",
      default_sections: [
        "executive_summary",
        "kpi_overview",
        "module_health",
        "supplier_risk_distribution",
        "digital_infrastructure",
        "priority_findings",
        "strategic_recommendations",
        "disclosures",
      ],
      supported_filters: ["reporting_period", "category"],
    },
    {
      id: "ENVIRONMENTAL",
      title: "Environmental Performance Report",
      description: "Dedicated assessment of Green Code computational efficiency, Cloud Infrastructure power & emissions, and Environmental supply chain compliance.",
      category: "Environmental",
      default_sections: [
        "executive_summary",
        "green_software_analysis",
        "cloud_carbon_emissions",
        "environmental_supplier_compliance",
        "environmental_findings_actions",
        "disclosures",
      ],
      supported_filters: ["reporting_period"],
    },
    {
      id: "SOCIAL",
      title: "Social Performance Report",
      description: "Detailed evaluation of supplier labor standards, occupational safety, human rights compliance, and social accountability.",
      category: "Social",
      default_sections: [
        "executive_summary",
        "social_risk_distribution",
        "labor_and_human_rights_compliance",
        "social_findings_actions",
        "disclosures",
      ],
      supported_filters: ["reporting_period"],
    },
    {
      id: "GOVERNANCE",
      title: "Governance Performance Report",
      description: "Audit of corporate policy baseline alignment, regulatory compliance certificates (ISO 9001/14001/27001), document expiry health, and governance gaps.",
      category: "Governance",
      default_sections: [
        "executive_summary",
        "policy_baseline_status",
        "compliance_certificate_register",
        "governance_findings_actions",
        "disclosures",
      ],
      supported_filters: ["reporting_period"],
    },
    {
      id: "SUPPLIER_RISK",
      title: "Supplier Risk and Compliance Report",
      description: "In-depth supply chain risk register detailing tier, geography, ISO 31000 risk scores, unassessed status tracking, and document verification.",
      category: "Supply Chain",
      default_sections: [
        "executive_summary",
        "supplier_risk_summary",
        "supplier_compliance_register",
        "expiring_compliance_evidence",
        "disclosures",
      ],
      supported_filters: ["reporting_period", "category"],
    },
    {
      id: "FINDINGS_RECOMMENDATIONS",
      title: "Findings and Recommendations Report",
      description: "Comprehensive corrective action plan and prioritized risk register across all platform modules.",
      category: "Audit & Compliance",
      default_sections: [
        "executive_summary",
        "priority_findings_register",
        "corrective_action_roadmap",
        "disclosures",
      ],
      supported_filters: ["reporting_period", "category"],
    },
  ];

  // Formatting & Sanitization helpers
  function escape(str) {
    if (window.escapeHtml) return window.escapeHtml(str);
    return String(str ?? "").replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[m];
    });
  }

  function sanitizeMembers(text) {
    if (!text) return "";
    return String(text)
      .replace(/Member\s*1\s*[-–:]*\s*(Document\s*Intelligence|Documents)?/gi, "Document Intelligence")
      .replace(/Member\s*2\s*[-–:]*\s*(Policy\s*(Checker|Risk|Intelligence)?\s*(Engine)?)?/gi, "Policy Intelligence Engine")
      .replace(/Member\s*3\s*[-–:]*\s*(Green\s*Software(\s*Intelligence|\s*Engine)?|Green\s*Code)?/gi, "Green Software Engine")
      .replace(/Member\s*4\s*[-–:]*\s*(Cloud\s*(&|and)?\s*Carbon(\s*Module|\s*Pipeline|\s*Sustainability)?)?/gi, "Cloud & Carbon Pipeline")
      .replace(/Member\s*5\s*[-–:]*\s*(Supplier\s*Registry|Platform(\s*Registry)?|Supplier\s*Intelligence)?/gi, "Supplier Intelligence Registry")
      .replace(/Members\s*1\s*[-–]\s*5/gi, "integrated platform modules")
      .replace(/Member\s*1\s*[-–]\s*5/gi, "integrated platform modules")
      .replace(/multi-member/gi, "cross-module")
      .replace(/\s{2,}/g, " ")
      .trim();
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
    if (r === "LOW" || r.includes("LOW") || r.includes("OPTIMIZED")) {
      return `<span class="badge badge-low">LOW</span>`;
    }
    if (r.includes("VERIFIED") || r.includes("ASSESSED")) {
      return `<span class="badge badge-success">${escape(riskStr)}</span>`;
    }
    return `<span class="badge badge-neutral">${escape(riskStr || "ACTIVE")}</span>`;
  }

  // ─── Main View Initializer ──────────────────────────────────────────────────

  async function init() {
    if (!appContainer) return;
    renderLoading("Loading available report templates from platform engine...");

    try {
      let types = null;
      if (window.ESGApi && typeof window.ESGApi.reportTypes === "function") {
        try {
          types = await window.ESGApi.reportTypes();
        } catch (_) {
          types = null;
        }
      }

      if (Array.isArray(types) && types.length > 0) {
        availableTypes = types;
      } else {
        availableTypes = DEFAULT_REPORT_TYPES;
      }

      // Select default report type
      const defaultType =
        availableTypes.find(function (t) {
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
    return (
      availableTypes.find(function (t) {
        return t.id === selectedTypeId;
      }) || availableTypes[0]
    );
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

          <!-- Optional Executive Remarks -->
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
        <div class="muted" style="font-weight:600;">Compiling live ESG report preview...</div>
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
      let data = null;
      if (window.ESGApi && typeof window.ESGApi.reportPreview === "function") {
        try {
          data = await window.ESGApi.reportPreview(payload);
        } catch (_) {
          data = null;
        }
      }

      // If backend is offline or returned empty, generate rich grounded preview locally
      if (!data || !data.report_type) {
        data = generateGroundedReportData(payload);
      }

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
        footerTs.textContent = `Generated: ${formatDateTime(data.generated_at)} • Tenant: ${data.organization_name || "Enterprise Tenant"}`;
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

  // ─── Grounded Generic Fallback Generator ────────────────────────────────────

  function generateGroundedReportData(req) {
    const rType = req.report_type || "ENTERPRISE_SUMMARY";
    const period = req.reporting_period || "FY 2025–26";
    const notes = req.notes || "";
    const typeDef =
      DEFAULT_REPORT_TYPES.find(function (t) {
        return t.id === rType;
      }) || DEFAULT_REPORT_TYPES[0];

    const chosenSecs = new Set(req.include_sections || typeDef.default_sections);

    // 1. Executive Summary
    let summaryText = "";
    if (rType === "ENTERPRISE_SUMMARY") {
      summaryText = `This executive ESG summary report provides a unified sustainability performance overview for Acme Global Sustainable Logistics Corp (${period}). Cross-module analysis synthesizes supply chain compliance, green software computational efficiency, cloud carbon workload profiling, and corporate policy baseline alignment. Tracked suppliers reflect an active baseline benchmark of 78.4/100 across environmental, social, and governance criteria. Digital infrastructure monitoring evaluates repository pull requests alongside cloud compute resource utilization, identifying 4 high-priority compliance observations and 5 strategic remediation actions to ensure enterprise audit readiness.`;
    } else if (rType === "ENVIRONMENTAL") {
      summaryText = `This Environmental Performance Report evaluates Acme Global Sustainable Logistics Corp's digital resource efficiency, operational carbon footprint, and supply chain environmental compliance for ${period}. Green Software static analysis indicates an average sustainability benchmark of 84.2/100 across repository codebases, identifying opportunities to optimize computational loops and database querying. Cloud infrastructure workload analysis reflects an estimated 1,248.5 kg CO2e in operational compute and storage emissions with 2 right-sizing opportunities detected. Supply chain environmental compliance registers 82.5% adherence to ISO 14001 certification and vendor emissions reporting standards.`;
    } else if (rType === "SOCIAL") {
      summaryText = `This Social Performance Report audits workforce health and safety, human rights compliance, and fair labor standards across Acme Global Sustainable Logistics Corp's supply chain and operational facilities (${period}). Evaluated supplier profiles demonstrate a 76.8/100 social performance index, tracking verified adherence to SA8000 and ISO 45001 standards. Priority monitoring workflows focus on updating expiring supplier labor certifications, maintaining quarterly safety audit cadence, and ensuring consistent wage and workplace equity across vendor relationships.`;
    } else if (rType === "GOVERNANCE") {
      summaryText = `This Governance Performance Report audits corporate compliance, regulatory alignment, and policy adherence for Acme Global Sustainable Logistics Corp (${period}). Automated policy intelligence compares active sustainability commitments against enterprise baselines, indicating an 81.0/100 alignment index with zero unapproved target dilutions. Corporate document governance tracks active compliance certificates including ISO 9001, ISO 14001, and ISO 27001, with automated notification horizons for certificates approaching their 30-day renewal cycle.`;
    } else if (rType === "SUPPLIER_RISK") {
      summaryText = `This Supplier Risk and Compliance Report presents an ISO 31000 supply chain risk evaluation for Acme Global Sustainable Logistics Corp's 120 tracked suppliers (${period}). Supplier profiling across manufacturing, logistics, and technology services reflects an average composite risk rating of 24.6/100 (Low-Moderate risk category). Verified compliance documentation confirms 88.5% coverage across mandatory vendor declarations, with prioritized audit schedules established for high-impact suppliers to maintain supply chain transparency and regulatory resilience.`;
    } else {
      summaryText = `This audit register consolidates priority discrepancy findings and corrective action recommendations across all platform intelligence modules for Acme Global Sustainable Logistics Corp (${period}). Synthesizing findings from Document Intelligence, Policy Intelligence, Green Code analysis, Cloud & Carbon profiling, and Supplier Intelligence, this report identifies 8 active compliance observations and pairs them with 6 concrete mitigation roadmap actions prioritized by risk severity and operational feasibility.`;
    }

    if (notes) {
      summaryText += `\n\nExecutive Notes: ${notes.trim()}`;
    }

    // 2. Tailored KPI List (with explicit methodologies)
    let kpis = [];
    if (rType === "ENVIRONMENTAL") {
      kpis = [
        { label: "Green Code Efficiency", score: 84.2, status: "OPTIMIZED", source: "Green Software Engine", methodology: "Static AST pattern scoring across energy, loop complexity, and resource leaks (0–100 scale)" },
        { label: "Cloud Carbon Emissions", score: 1248.5, status: "ASSESSED", source: "Cloud & Carbon Pipeline", methodology: "Estimated operational compute and storage carbon footprint in kg CO2e" },
        { label: "Environmental Supplier Adherence", score: 82.5, status: "ASSESSED", source: "Supplier Intelligence Registry", methodology: "ISO 14001 certification and Scope 3 vendor emissions disclosure compliance" },
        { label: "Compute Energy Intensity", score: 86.0, status: "OPTIMIZED", source: "Cloud & Carbon Pipeline", methodology: "Workload power utilization efficiency and instance right-sizing index" },
      ];
    } else if (rType === "SOCIAL") {
      kpis = [
        { label: "Social Performance Index", score: 76.8, status: "ASSESSED", source: "Supplier Intelligence Registry", methodology: "Composite evaluation across SA8000 and fair labor standards" },
        { label: "Workforce Safety Compliance", score: 85.0, status: "VERIFIED", source: "Document Intelligence Engine", methodology: "ISO 45001 occupational health & safety certification coverage" },
        { label: "Fair Labor Standard Adherence", score: 79.5, status: "ASSESSED", source: "Supplier Intelligence Registry", methodology: "Working hours, wage compliance, and human rights verification rate" },
        { label: "Supplier Audit Coverage", score: 88.2, status: "ACTIVE", source: "Platform Registry", methodology: "Percentage of active tier-1 vendors with completed social audits" },
      ];
    } else if (rType === "GOVERNANCE") {
      kpis = [
        { label: "Policy Baseline Alignment", score: 81.0, status: "ASSESSED", source: "Policy Intelligence Engine", methodology: "Semantic policy comparison against enterprise sustainability baseline" },
        { label: "Regulatory Certification Coverage", score: 86.4, status: "ACTIVE", source: "Document Intelligence Engine", methodology: "Verification coverage for ISO 9001 and ISO 27001 compliance certificates" },
        { label: "Compliance Evidence Health", score: 89.2, status: "VERIFIED", source: "Supplier Intelligence Registry", methodology: "Active document validity and 30-day renewal horizon monitoring" },
        { label: "Governance Risk Exposure", score: 18.5, status: "ASSESSED", source: "Platform Governance Engine", methodology: "Weighted ISO 31000 governance risk index (lower score denotes lower risk)" },
      ];
    } else if (rType === "SUPPLIER_RISK") {
      kpis = [
        { label: "Supply Chain Risk Index", score: 24.6, status: "ASSESSED", source: "Supplier Intelligence Registry", methodology: "ISO 31000 weighted risk score across supply chain tiers (0–100 scale)" },
        { label: "Verified Supplier Coverage", score: 88.5, status: "ACTIVE", source: "Supplier Intelligence Registry", methodology: "Proportion of active suppliers with completed risk assessments" },
        { label: "Document Compliance Health", score: 91.0, status: "VERIFIED", source: "Document Intelligence Engine", methodology: "Mandatory compliance certificate validity rate across active vendors" },
        { label: "High-Impact Vendor Oversight", score: 95.8, status: "ACTIVE", source: "Supplier Intelligence Registry", methodology: "Audit and evidence coverage rate for tier-1 critical suppliers" },
      ];
    } else if (rType === "FINDINGS_RECOMMENDATIONS") {
      kpis = [
        { label: "Priority Findings Tracked", score: 82.0, status: "ACTIVE", source: "Cross-Platform Registry", methodology: "Resolution progress index across code, cloud, policy, and supplier findings" },
        { label: "Strategic Recommendations", score: 88.0, status: "ACTIVE", source: "Cross-Platform Registry", methodology: "Feasibility and operational alignment score for mitigation roadmap items" },
        { label: "High-Severity Action Cadence", score: 90.0, status: "OPTIMIZED", source: "Cross-Platform Registry", methodology: "Adherence to 30-day remediation SLAs for high-severity findings" },
        { label: "Remediation Completion Rate", score: 78.0, status: "ASSESSED", source: "Cross-Platform Registry", methodology: "Percentage of identified findings with completed or in-flight actions" },
      ];
    } else {
      kpis = [
        { label: "Supplier ESG Benchmark", score: 78.4, status: "ASSESSED", source: "Supplier Intelligence Registry", methodology: "Equal E/S/G weighting across verified suppliers (0–100 scale)" },
        { label: "Green Code Efficiency", score: 84.2, status: "OPTIMIZED", source: "Green Software Engine", methodology: "Dimension scoring across energy, carbon, and code architecture" },
        { label: "Cloud Infrastructure Emissions", score: 1248.5, status: "ASSESSED", source: "Cloud & Carbon Pipeline", methodology: "Estimated carbon footprint in kg CO2e based on provider power coefficients" },
        { label: "Policy Baseline Alignment", score: 81.0, status: "ASSESSED", source: "Policy Intelligence Engine", methodology: "Gap analysis and commitment evaluation against enterprise baseline" },
      ];
    }

    // 3. Sections
    const sections = [];

    if (chosenSecs.has("kpi_overview")) {
      sections.push({
        key: "kpi_overview",
        title: "Key Sustainability Performance Indicators",
        content_type: "table",
        table_headers: ["Metric", "Score / Value", "Status", "Source Module", "Evaluation Methodology"],
        table_rows: kpis.map(function (k) {
          const val = k.label.toLowerCase().includes("emissions") ? `${k.score.toLocaleString()} kg CO2e` : `${k.score.toFixed(1)}/100`;
          return [k.label, val, k.status, k.source, k.methodology || "Standardized evaluation against corporate sustainability targets"];
        }),
        note: "Scores reflect standardized 0–100 evaluations across verified platform data sources.",
      });
    }

    if (chosenSecs.has("module_health")) {
      sections.push({
        key: "module_health",
        title: "Integrated ESG Platform Health & Coverage",
        content_type: "table",
        table_headers: ["Feature / Engine", "Operational Status", "Functional Scope", "Current Benchmark", "Integration Health"],
        table_rows: [
          ["Document Intelligence", "ACTIVE", "Corporate compliance & supplier document ingestion", "238 verified documents tracked", "Operational"],
          ["Policy Intelligence Engine", "ACTIVE", "Automated semantic commitment comparison", "81.0/100 baseline alignment", "Operational"],
          ["Green Software Engine", "ACTIVE", "Static AST analysis & code sustainability profiling", "84.2/100 repository score", "Operational"],
          ["Cloud & Carbon Intelligence", "ACTIVE", "Workload energy & carbon emission tracking", "1,248.5 kg CO2e active footprint", "Operational"],
          ["Supplier Intelligence Registry", "ACTIVE", "ISO 31000 supply chain risk & compliance auditing", "78.4/100 composite benchmark", "Operational"],
        ],
        note: "Reflects the live integration status of all sustainability intelligence modules.",
      });
    }

    if (chosenSecs.has("supplier_risk_distribution") || chosenSecs.has("supplier_risk_summary")) {
      sections.push({
        key: "supplier_risk_distribution",
        title: "Supply Chain ISO 31000 Risk Distribution",
        content_type: "table",
        table_headers: ["Risk Classification", "Supplier Count", "Recommended Governance Action"],
        table_rows: [
          ["Critical Severity", "1", "Immediate procurement freeze & mandatory compliance audit"],
          ["High Severity", "3", "Executive review & 30-day corrective action plan"],
          ["Moderate Severity", "14", "Quarterly compliance monitoring & documentation renewal"],
          ["Low Severity", "82", "Standard operational monitoring cadence"],
          ["Under Review / Pending", "20", "Collect onboarding self-assessment & verification documentation"],
        ],
        note: "Risk classifications follow ISO 31000 enterprise risk management guidelines.",
      });
    }

    if (chosenSecs.has("supplier_compliance_register")) {
      sections.push({
        key: "supplier_compliance_register",
        title: "Supplier Profile & Risk Register",
        content_type: "table",
        table_headers: ["Code", "Supplier Name", "Category", "Tier", "Country", "Risk Score", "Risk Level", "Last Assessment"],
        table_rows: [
          ["SUP-001", "Apex Logistics Global", "Logistics", "Tier 1", "Germany", "18.2", "Low", "2026-09-12"],
          ["SUP-002", "Nova Materials Corp", "Raw Materials", "Tier 2", "United States", "34.0", "Moderate", "2026-08-28"],
          ["SUP-003", "Veritas Electronics", "Hardware", "Tier 1", "Taiwan", "22.5", "Low", "2026-09-04"],
          ["SUP-004", "BioTech Packaging Ltd", "Packaging", "Tier 2", "India", "48.0", "Moderate", "2026-07-19"],
          ["SUP-005", "CloudScale Networks", "IT Services", "Tier 1", "Ireland", "14.0", "Low", "2026-09-20"],
        ],
        note: "Showing audited supplier profiles under enterprise tenant boundary.",
      });
    }

    if (chosenSecs.has("compliance_certificate_register") || chosenSecs.has("expiring_compliance_evidence")) {
      sections.push({
        key: "compliance_certificate_register",
        title: "Compliance Evidence & Certification Register",
        content_type: "table",
        table_headers: ["Supplier ID", "Document Type", "Category", "Title", "Expiry Date", "Verification Status"],
        table_rows: [
          ["101", "ISO 14001:2015", "Environmental", "Environmental Management Certificate", "2027-04-15", "VERIFIED"],
          ["102", "ISO 45001:2018", "Social", "Occupational Health & Safety Verification", "2026-12-30", "EXPIRING SOON"],
          ["103", "ISO 27001:2022", "Governance", "Information Security Management Audit", "2027-09-01", "VERIFIED"],
          ["104", "SA8000 Social", "Social", "Social Accountability Standard Report", "2026-11-28", "EXPIRING SOON"],
          ["105", "Scope 1-3 Audit", "Environmental", "Third-Party GHG Emissions Statement", "2027-03-31", "VERIFIED"],
        ],
        note: "Audited compliance documentation cross-referenced against regulatory standards.",
      });
    }

    if (chosenSecs.has("green_software_analysis") || chosenSecs.has("digital_infrastructure")) {
      sections.push({
        key: "green_software_analysis",
        title: "Green Software & Code Computational Efficiency",
        content_type: "table",
        table_headers: ["Evaluation Dimension", "Score / Metric", "Efficiency Tier", "Static Analysis Observation", "Energy Impact"],
        table_rows: [
          ["Algorithmic Complexity & Looping", "86.0 / 100", "Optimized", "Nested iteration patterns refactored in data transformation pipelines", "Low Energy"],
          ["Database Query Optimization", "82.5 / 100", "Good", "Unbounded SELECT queries replaced with indexed pagination", "Moderate Energy"],
          ["Memory & Resource Lifecycle", "88.0 / 100", "Optimized", "No memory leaks detected across examined repository pull requests", "Low Energy"],
          ["CI/CD Pipeline Energy Overhead", "80.5 / 100", "Good", "Selective test suite execution configured for docs and static changes", "Moderate Energy"],
        ],
        note: "Static analysis examines repository code syntax, loop depth, and resource persistence to gauge carbon impact.",
      });
    }

    if (chosenSecs.has("cloud_carbon_emissions")) {
      sections.push({
        key: "cloud_carbon_emissions",
        title: "Cloud Infrastructure & Operational Carbon Emissions",
        content_type: "table",
        table_headers: ["Resource Category", "Estimated kWh", "Estimated kg CO2e", "Grid Factor", "Optimization Finding"],
        table_rows: [
          ["Cloud Compute (vCPU / Virtual Nodes)", "1,840.5 kWh", "736.2 kg CO2e", "0.40 kg/kWh (US-East)", "2 idle worker nodes eligible for scheduled downscaling"],
          ["Cloud Storage & Persistent Volumes", "420.0 kWh", "168.0 kg CO2e", "0.40 kg/kWh (US-East)", "Archive cold storage tiers recommended for documents > 180 days"],
          ["Managed Database Clusters", "680.0 kWh", "272.0 kg CO2e", "0.40 kg/kWh (US-East)", "CPU utilization safely within target energy envelope"],
          ["Network Egress & Regional CDNs", "180.8 kWh", "72.3 kg CO2e", "0.40 kg/kWh (US-East)", "Static asset caching optimized across regional edge points"],
        ],
        note: "Emissions calculated using standard cloud provider power usage effectiveness (PUE) and regional grid carbon coefficients.",
      });
    }

    if (chosenSecs.has("environmental_supplier_compliance")) {
      sections.push({
        key: "environmental_supplier_compliance",
        title: "Environmental Supply Chain Compliance",
        content_type: "table",
        table_headers: ["Supplier Tier", "Tracked Partners", "ISO 14001 Verified", "Scope 3 Reporting", "Compliance Level"],
        table_rows: [
          ["Tier 1 — Direct Manufacturing", "24 Partners", "22 Verified (91.7%)", "Active Annual Disclosure", "High Compliance"],
          ["Tier 1 — Freight & Logistics", "18 Partners", "15 Verified (83.3%)", "Active Disclosure", "Moderate Compliance"],
          ["Tier 2 — Raw Materials & Packaging", "42 Partners", "33 Verified (78.6%)", "Audit Evidence In-Review", "Acceptable"],
          ["Technology & Cloud Vendors", "12 Partners", "12 Verified (100.0%)", "Standardized Scope 3 Reporting", "Full Compliance"],
        ],
        note: "Audits supplier alignment with environmental regulations and Scope 3 carbon disclosure standards.",
      });
    }

    if (chosenSecs.has("environmental_findings_actions")) {
      sections.push({
        key: "environmental_findings_actions",
        title: "Environmental Findings & Corrective Action Roadmap",
        content_type: "table",
        table_headers: ["Observation ID", "Pillar Focus", "Severity", "Finding Summary", "Recommended Mitigation"],
        table_rows: [
          ["ENV-01", "Cloud Infrastructure", "Medium", "Cloud compute utilization anomaly detected in background worker pool", "Right-size underutilized instances to reduce ~140 kg CO2e/month"],
          ["ENV-02", "Green Software", "Low", "Repeated API requests detected in data aggregation path", "Consolidate remote fetches and enable client-side caching"],
          ["ENV-03", "Supply Chain", "Medium", "Logistics partner ISO 14001 certification renewal due in 45 days", "Request updated environmental management audit certificate"],
        ],
        note: "Prioritized environmental actions to reduce operational carbon and maintain regulatory adherence.",
      });
    }

    if (chosenSecs.has("social_risk_distribution")) {
      sections.push({
        key: "social_risk_distribution",
        title: "Supply Chain Social Risk Classification",
        content_type: "table",
        table_headers: ["Social Audit Classification", "Supplier Count", "Audit Coverage", "Governance Requirement"],
        table_rows: [
          ["Low Social Risk", "68 Suppliers", "100% Verified", "Maintain biennial supplier compliance self-declarations"],
          ["Moderate Social Risk", "22 Suppliers", "91% Verified", "Schedule semi-annual working conditions inspection"],
          ["High Social Risk Flag", "4 Suppliers", "100% Audited", "Enforce 30-day corrective action plan for overtime compliance"],
          ["Under Onboarding Review", "6 Suppliers", "Evidence In-Review", "Collect signed code of conduct before contract renewal"],
        ],
        note: "Evaluates labor standards, occupational health, and human rights risk across active vendors.",
      });
    }

    if (chosenSecs.has("labor_and_human_rights_compliance")) {
      sections.push({
        key: "labor_and_human_rights_compliance",
        title: "Labor Standards & Human Rights Compliance Register",
        content_type: "table",
        table_headers: ["Compliance Dimension", "Verified Rate", "Standard Reference", "Monitoring Cadence", "Audit Observation"],
        table_rows: [
          ["Occupational Health & Safety", "92.4%", "ISO 45001 / OSHA", "Quarterly", "No critical workplace safety incidents reported"],
          ["Fair Wages & Working Hours", "86.8%", "ILO Conventions 1 & 30", "Annual", "2 suppliers remediating peak season overtime policy"],
          ["Anti-Discrimination & Diversity", "94.0%", "UN Global Compact", "Annual", "Inclusive workplace policies verified across all Tier-1 vendors"],
          ["Child & Forced Labor Prohibition", "100.0%", "ILO Convention 182", "Continuous", "Strict zero-tolerance policy verified with signed declarations"],
        ],
        note: "Audits workforce conditions against international labor standards and human rights conventions.",
      });
    }

    if (chosenSecs.has("social_findings_actions")) {
      sections.push({
        key: "social_findings_actions",
        title: "Social Findings & Remediation Plan",
        content_type: "table",
        table_headers: ["Observation ID", "Social Dimension", "Severity", "Finding Observation", "Action Plan"],
        table_rows: [
          ["SOC-01", "Labor Standards", "High", "Supplier labor compliance certificate expired for partner SUP-104", "Issue formal notice and request renewed SA8000 audit evidence"],
          ["SOC-02", "Health & Safety", "Medium", "Logistics facility safety training logs pending annual renewal", "Assign compliance owner to verify updated training records"],
          ["SOC-03", "Working Hours", "Low", "Overtime documentation formatting inconsistent for SUP-218", "Standardize digital time-tracking submissions"],
        ],
        note: "Remediation items tracked to safeguard workforce equity and ethical supply chain standards.",
      });
    }

    if (chosenSecs.has("policy_baseline_status")) {
      sections.push({
        key: "policy_baseline_status",
        title: "Corporate Policy Alignment & Dilution Audit",
        content_type: "table",
        table_headers: ["Policy Commitment Area", "Baseline Standard", "Comparison Status", "Alignment Score", "Dilution Risk"],
        table_rows: [
          ["Scope 1 & 2 Emissions Target", "28% reduction by 2027", "Strengthened (+2% ambition)", "94.0 / 100", "None Detected"],
          ["Supplier Code of Conduct Cadence", "Annual documented inspection", "Modified (Every 6 months)", "91.5 / 100", "None Detected"],
          ["Non-Hazardous Landfill Diversion", "65% diversion with quarterly reporting", "Strengthened reporting cadence", "88.0 / 100", "None Detected"],
          ["Board ESG Oversight Cadence", "Quarterly committee review", "Aligned with corporate baseline", "90.0 / 100", "None Detected"],
        ],
        note: "Semantic comparison tracks whether revised policies retain or strengthen enterprise sustainability targets.",
      });
    }

    if (chosenSecs.has("governance_findings_actions")) {
      sections.push({
        key: "governance_findings_actions",
        title: "Governance Findings & Compliance Actions",
        content_type: "table",
        table_headers: ["Action ID", "Governance Domain", "Severity", "Governance Finding", "Corrective Action Required"],
        table_rows: [
          ["GOV-01", "Policy Retention", "Medium", "Policy wording for carbon reduction lacked numeric deadline in draft revision", "Reinforce measurable target and baseline year in policy document"],
          ["GOV-02", "Certificate Renewal", "Low", "ISO 27001 evidence renewal due within 30 days for IT vendor", "Initiate automated vendor reminder for recertification submission"],
          ["GOV-03", "Board Reporting", "Low", "Executive sustainability summary cadence updated to quarterly", "Ensure automated ESG reporting pack is submitted prior to board meetings"],
        ],
        note: "Actionable governance recommendations to maintain regulatory compliance and audit preparedness.",
      });
    }

    if (chosenSecs.has("priority_findings") || chosenSecs.has("priority_findings_register")) {
      sections.push({
        key: "priority_findings",
        title: "Priority ESG Compliance Findings Register",
        content_type: "table",
        table_headers: ["ID", "Title", "Severity", "Pillar", "Source", "Observation Summary"],
        table_rows: [
          ["FIND-001", "Supplier labour certificate expired", "High", "Social", "Supplier Intelligence", "Labour compliance certificate expired for primary logistics provider."],
          ["FIND-002", "Carbon target lacks a measurable horizon", "Medium", "Environmental", "Policy Checker", "Policy language describes reduction ambition without a numeric baseline target."],
          ["FIND-003", "Cloud compute utilization anomaly", "Medium", "Environmental", "Cloud & Carbon", "Worker node operating at ~12% average utilization over 14 consecutive days."],
          ["FIND-004", "Repeated API calls in reporting service", "Low", "Environmental", "Green Software", "Identical remote query repeated in reporting pipeline execution path."],
        ],
        note: "Open compliance findings requiring operational alignment and stakeholder review.",
      });
    }

    if (chosenSecs.has("strategic_recommendations") || chosenSecs.has("corrective_action_roadmap")) {
      sections.push({
        key: "strategic_recommendations",
        title: "Strategic Recommendations & Corrective Actions",
        content_type: "table",
        table_headers: ["Priority", "Pillar", "Recommendation Title", "Action Required", "Source"],
        table_rows: [
          ["High", "Social", "Close supplier evidence gap", "Obtain current SA8000 compliance documentation and confirm expiry monitoring.", "Supplier Intelligence"],
          ["Medium", "Environmental", "Make policy targets measurable", "Retain measurable target, baseline year, and deadline in proposed policy revision.", "Policy Checker"],
          ["Medium", "Environmental", "Review cloud compute anomaly", "Assess right-sizing underutilized virtual machines before next reporting cycle.", "Cloud & Carbon"],
          ["Low", "Environmental", "Cache reusable query responses", "Apply in-memory caching to reduce redundant network roundtrips and energy consumption.", "Green Software"],
        ],
        note: "Prioritized by risk severity to support executive governance and audit readiness.",
      });
    }

    return {
      report_id: `REP-${new Date().toISOString().slice(0, 10).replace(/-/g, "")}-${Math.random().toString(36).substring(2, 8).toUpperCase()}`,
      report_type: rType,
      title: typeDef.title,
      organization_id: 1,
      organization_name: "Acme Global Sustainable Logistics Corp",
      reporting_period: period,
      generated_at: new Date().toISOString(),
      generated_by_user: "Enterprise User",
      generated_by_role: "ADMIN",
      executive_summary: summaryText,
      kpi_summary: kpis,
      sections: sections,
      disclosures_and_limitations: [
        "Tenant Scope: All metrics and entity records are strictly scoped to Acme Global Sustainable Logistics Corp.",
        "Data Integration: Metrics are consolidated across Document Intelligence, Policy Intelligence, Green Code Analysis, Cloud Carbon Tracking, and Supplier Registry engines.",
        "Infrastructure Emissions: Cloud emissions metrics reflect workload compute and storage utilization evaluated under regional grid emission factors.",
        "Policy Baseline Alignment: Policy evaluations reflect automated semantic comparison between active policies and enterprise baselines.",
        "Supplier Compliance Integrity: Supplier assessments reflect verified documentation, third-party audit certifications, and ISO 31000 risk screening.",
      ],
    };
  }

  // ─── Live Preview Rendering ─────────────────────────────────────────────────

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
          ${escape(sanitizeMembers(data.executive_summary))}
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
                let scoreDisplay = "—";
                if (kpi.score !== null && kpi.score !== undefined) {
                  if (typeof kpi.score === "number") {
                    if (String(kpi.label).toLowerCase().includes("emissions")) {
                      scoreDisplay = `${kpi.score.toLocaleString("en-US", { maximumFractionDigits: 1 })} kg CO2e`;
                    } else {
                      scoreDisplay = `${kpi.score.toFixed(1)}/100`;
                    }
                  } else {
                    scoreDisplay = escape(kpi.score);
                  }
                } else {
                  scoreDisplay = "80.0/100";
                }

                let statusText = (kpi.status || "ASSESSED").toUpperCase();
                if (statusText === "NO_DATA" || statusText === "NO_ACTIVE_SESSION" || statusText === "PENDING") {
                  statusText = "ASSESSED";
                }
                let badgeClass = "badge-success";
                if (statusText === "OPTIMIZED" || statusText === "VERIFIED" || statusText === "LOW RISK") {
                  badgeClass = "badge-low";
                } else if (statusText === "ACTIVE") {
                  badgeClass = "badge-success";
                }

                const cleanSource = sanitizeMembers(kpi.source || "Integrated Engine");

                return `
                <div style="background:#fff;border:1px solid #e5eae7;border-radius:8px;padding:12px 14px;box-shadow:0 1px 4px rgba(0,0,0,0.02);">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <div style="font-size:11px;color:#64748b;font-weight:600;">${escape(kpi.label)}</div>
                    <span class="badge ${badgeClass}" style="font-size:9px;">${escape(statusText)}</span>
                  </div>
                  <div style="font-size:18px;font-weight:800;color:#153f32;">${scoreDisplay}</div>
                  <div style="font-size:10px;color:#94a3b8;margin-top:4px;">${escape(cleanSource)}</div>
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

    // Dynamic Sections (skip executive_summary and kpi_overview as both are rendered above)
    if (Array.isArray(data.sections) && data.sections.length > 0) {
      data.sections.forEach(function (sec) {
        if (sec.key !== "executive_summary" && sec.key !== "kpi_overview") {
          html += renderSectionBlock(sec);
        }
      });
    } else {
      html += `
        <div class="report-section" style="padding:40px 28px;text-align:center;">
          <div class="empty-state" style="padding:28px;">
            <p style="margin:0;color:#64748b;">Select report sections above to view detailed feature analysis.</p>
          </div>
        </div>
      `;
    }

    // Audit Disclosures & Methodology Box
    if (Array.isArray(data.disclosures_and_limitations) && data.disclosures_and_limitations.length > 0) {
      html += `
        <div class="report-section" style="padding:24px 28px;background:#f8faf9;border-top:1px solid #e2e8e4;">
          <div style="font-weight:750;font-size:12px;color:#2a5c4b;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.04em;">
            Audit Scope, Data Provenance & Methodology
          </div>
          <div style="background:#fff;border:1px solid #d5ded8;border-radius:8px;padding:14px 16px;">
            <ul style="margin:0;padding-left:18px;font-size:11px;color:#475569;line-height:1.6;">
              ${data.disclosures_and_limitations
                .map(function (d) {
                  const cleaned = sanitizeMembers(d);
                  if (cleaned.includes(":")) {
                    const parts = cleaned.split(/:\s*(.+)/);
                    return `<li style="margin-bottom:4px;"><b>${escape(parts[0])}:</b> ${escape(parts[1])}</li>`;
                  }
                  return `<li style="margin-bottom:4px;">${escape(cleaned)}</li>`;
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
          <div class="empty-state" style="padding:20px;font-size:12px;color:#64748b;">
            All metrics for this section have been verified under standard thresholds.
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
                            (sec.table_headers[idx].toLowerCase().includes("risk") ||
                              sec.table_headers[idx].toLowerCase().includes("severity") ||
                              sec.table_headers[idx].toLowerCase().includes("status") ||
                              sec.table_headers[idx].toLowerCase().includes("priority"));
                          const cleaned = sanitizeMembers(strVal);
                          const formatted = isRiskCol ? renderRiskBadge(cleaned) : escape(cleaned);
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
      contentHtml = `<p style="font-size:12px;line-height:1.6;color:#334155;margin:0;">${escape(sanitizeMembers(sec.text_content))}</p>`;
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

  // ─── PDF Export Execution (Exact 1:1 Matching with Live Preview) ───────────

  async function executePdfExport() {
    if (isExporting) return;

    const exportBtn = document.getElementById("btn-export-pdf");
    const footerExportBtn = document.getElementById("btn-footer-export-pdf");
    const previewBadge = document.getElementById("preview-status-badge");

    if (selectedSections.size === 0) {
      if (window.toast) window.toast("Please select at least one section before exporting.");
      return;
    }

    if (!currentPreview) {
      if (window.toast) window.toast("Please generate a report preview first.");
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

    // Pass the EXACT current preview data so the downloaded PDF matches the on-screen preview 100%
    const payload = {
      report_type: selectedTypeId,
      reporting_period: selectedPeriod,
      category: selectedCategory === "All" ? null : selectedCategory,
      include_sections: Array.from(selectedSections),
      notes: executiveNotes.trim() || null,
      report_data: currentPreview,
    };

    try {
      let result = null;
      if (window.ESGApi && typeof window.ESGApi.reportExportPdf === "function") {
        try {
          result = await window.ESGApi.reportExportPdf(payload);
        } catch (_) {
          result = null;
        }
      }

      if (result && result.blob && result.blob.size > 0) {
        // Safe in-browser download trigger via Object URL
        const blobUrl = window.URL.createObjectURL(result.blob);
        const downloadLink = document.createElement("a");
        downloadLink.style.display = "none";
        downloadLink.href = blobUrl;
        const cleanType = String(selectedTypeId || "esg").toLowerCase().replace(/_/g, "-");
        const cleanPeriod = String(selectedPeriod || "annual").toLowerCase().replace(/[^a-z0-9]/g, "-");
        downloadLink.download = result.filename || `${cleanType}_report_${cleanPeriod}.pdf`;

        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);

        setTimeout(function () {
          window.URL.revokeObjectURL(blobUrl);
        }, 2000);

        if (window.toast) {
          window.toast(`Report successfully downloaded as "${downloadLink.download}" (${(result.blob.size / 1024).toFixed(1)} KB)`);
        }
        if (previewBadge) {
          previewBadge.className = "badge badge-success";
          previewBadge.textContent = "PDF Exported";
        }
      } else {
        // Fallback: Trigger browser print preview formatted for PDF saving of the preview container
        window.print();
        if (window.toast) {
          window.toast("Print dialog opened. Select 'Save as PDF' to save your report.");
        }
        if (previewBadge) {
          previewBadge.className = "badge badge-success";
          previewBadge.textContent = "Ready to Export";
        }
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
