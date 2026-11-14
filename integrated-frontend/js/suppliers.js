/**
 * Member 5: Supplier Intelligence & Performance Management
 * Connects directly to FastAPI backend (/api/suppliers)
 * Adheres strictly to Member 2's ISO 31000 risk matrix
 */

(function () {
  const app = document.getElementById("page-app");
  if (!app) return;

  let state = {
    suppliers: [],
    selectedSupplier: null,
    stats: {
      total_suppliers: 0,
      high_risk_count: 0,
      expiring_documents_count: 0,
      average_esg_score: 0,
    },
    baselinePolicy: null,
    page: 1,
    pageSize: 10,
    totalPages: 1,
    total: 0,
    filters: {
      search: "",
      category: "",
      tier: "",
      risk_level: "",
    },
    isLoading: false,
    isDetailLoading: false,
    isLiveBackend: false,
    errorMessage: null,
  };

  // Helper to format ISO date strings
  function formatDate(dStr) {
    if (!dStr) return "—";
    try {
      const d = new Date(dStr);
      return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
    } catch (_) {
      return dStr;
    }
  }

  // Determine badge styling for risk level (specifically handling NOT_ASSESSED)
  function renderRiskBadge(riskLevel) {
    const s = String(riskLevel || "NOT_ASSESSED").toUpperCase();
    if (s === "NOT_ASSESSED" || s === "NOT ASSESSED") {
      return `<span class="badge badge-neutral">NOT ASSESSED</span>`;
    }
    return badge(riskLevel);
  }

  // Determine badge styling for expiry status
  function expiryBadge(status, days) {
    const s = String(status || "").toUpperCase();
    if (s === "EXPIRED") {
      const dayText = days !== null && days !== undefined ? ` (${Math.abs(days)}d ago)` : "";
      return `<span class="badge badge-high">EXPIRED${dayText}</span>`;
    }
    if (s === "EXPIRING_SOON") {
      const dayText = days !== null && days !== undefined ? ` (in ${days}d)` : "";
      return `<span class="badge badge-medium">EXPIRING SOON${dayText}</span>`;
    }
    if (s === "VALID") {
      return `<span class="badge badge-low">VALID</span>`;
    }
    return `<span class="badge badge-neutral">${escapeHtml(status || "ACTIVE")}</span>`;
  }

  // Load KPI stats and supplier list from API
  async function loadData() {
    state.isLoading = true;
    state.errorMessage = null;
    render();

    try {
      // 0. Fetch enterprise baseline policy
      try {
        state.baselinePolicy = await ESGApi.baselinePolicyGet();
      } catch (_) {
        state.baselinePolicy = null;
      }

      // 1. Fetch live KPI stats
      const statsRes = await ESGApi.supplierStats();
      state.stats = statsRes;
      state.isLiveBackend = true;

      // 2. Fetch suppliers with pagination & filtering
      const params = {
        page: state.page,
        page_size: state.pageSize,
      };
      if (state.filters.search) params.search = state.filters.search;
      if (state.filters.category && state.filters.category !== "All") params.category = state.filters.category;
      if (state.filters.tier && state.filters.tier !== "All") params.tier = state.filters.tier;
      if (state.filters.risk_level && state.filters.risk_level !== "All") params.risk_level = state.filters.risk_level;

      const listRes = await ESGApi.supplierList(params);
      state.suppliers = listRes.items || [];
      state.total = listRes.total || 0;
      state.totalPages = listRes.total_pages || 1;

      // Auto-select first supplier or retain selection
      if (!state.selectedSupplier && state.suppliers.length > 0) {
        await selectSupplier(state.suppliers[0].id, false);
      } else if (state.selectedSupplier) {
        // Refresh selected supplier details
        await selectSupplier(state.selectedSupplier.id, false);
      }
    } catch (err) {
      console.warn("Could not load from API, falling back to mock view:", err.message);
      state.isLiveBackend = false;
      state.errorMessage = "Backend connection: " + err.message;
      // Fallback mock representation if server unreachable
      if (window.MOCK && window.MOCK.suppliers) {
        state.suppliers = window.MOCK.suppliers.map((s, idx) => ({
          id: idx + 1,
          name: s[0],
          code: `SUP-00${idx + 1}`,
          category: "General",
          tier: "Tier 1",
          country: "EU",
          overall_score: parseFloat(s[1]),
          environmental_score: parseFloat(s[2]),
          social_score: parseFloat(s[3]),
          governance_score: parseFloat(s[4]),
          document_count: 5,
          risk_level: s[6].toUpperCase(),
          status: "Active",
        }));
        state.stats = {
          total_suppliers: state.suppliers.length,
          high_risk_count: 1,
          expiring_documents_count: 2,
          average_esg_score: 77.2,
        };
      }
    } finally {
      state.isLoading = false;
      render();
    }
  }

  // Select a supplier and fetch detailed profile (docs & findings)
  async function selectSupplier(id, triggerRender = true) {
    state.isDetailLoading = true;
    if (triggerRender) render();

    try {
      if (state.isLiveBackend) {
        const detail = await ESGApi.supplierGet(id);
        state.selectedSupplier = detail;
      } else {
        const found = state.suppliers.find((s) => s.id === id);
        if (found) {
          state.selectedSupplier = {
            ...found,
            documents: [
              {
                id: 101,
                title: "ISO 14001 Environmental Standard",
                document_type: "ISO 14001",
                expiry_status: "VALID",
                verification_status: "Verified",
                uploaded_at: new Date().toISOString(),
              },
            ],
            findings: [
              {
                id: 201,
                title: "Compliance evidence check",
                category: "Governance",
                severity: "Medium",
                risk_score: 36.0,
                description: "Annual verification requires final review.",
                recommendation: "Request updated audit signoff.",
                status: "Open",
              },
            ],
          };
        }
      }
    } catch (err) {
      toast("Error loading supplier details: " + err.message);
    } finally {
      state.isDetailLoading = false;
      if (triggerRender) render();
    }
  }

  // Trigger ISO 31000 risk recalculation / Member 2 policy comparison
  async function triggerEvaluation(supplierId, policyComparison = true) {
    try {
      loading(
        document.getElementById("eval-btn-wrap"),
        policyComparison ? "Comparing policy via Member 2 API..." : "Calculating local ISO 31000 risk..."
      );
      const res = await ESGApi.supplierEvaluate(supplierId, null, policyComparison);
      const modeStr = res.evaluation_mode === "MEMBER2_REMOTE_API" ? "Member 2 Engine (Online)" : "Local ISO 31000 Fallback";
      const scoreText = res.risk_score !== null && res.risk_score !== undefined ? `${res.risk_score}/100` : "Not Assessed";
      toast(`[${modeStr}] Risk: ${res.risk_level} (${scoreText}) — Score: ${res.overall_score}/100`);
      await loadData();
    } catch (err) {
      toast("Evaluation error: " + err.message);
      render();
    }
  }

  // Delete a supplier (Admin only)
  async function handleDelete(supplierId, supplierName) {
    if (!confirm(`Are you sure you want to delete supplier "${supplierName}"? This action cannot be undone.`)) {
      return;
    }
    try {
      await ESGApi.supplierDelete(supplierId);
      toast(`Supplier "${supplierName}" deleted successfully.`);
      if (state.selectedSupplier && state.selectedSupplier.id === supplierId) {
        state.selectedSupplier = null;
      }
      await loadData();
    } catch (err) {
      toast("Delete failed: " + err.message);
    }
  }

  // Render the entire Supplier Management UI
  function render() {
    const s = state.selectedSupplier;

    app.innerHTML = `
      <!-- Connection Status & Errors -->
      ${
        state.errorMessage
          ? `<div class="alert alert-error" style="display:flex;justify-content:space-between;align-items:center">
              <div><b>Notice:</b> ${escapeHtml(state.errorMessage)} (Showing fallback data)</div>
              <button class="btn btn-secondary btn-sm" id="btn-retry">Retry Connection</button>
             </div>`
          : ""
      }

      <!-- Top KPI Summary Cards -->
      <div class="kpi-strip">
        <div class="kpi">
          <div class="kpi-label">TOTAL SUPPLIERS</div>
          <div class="kpi-value">${state.stats.total_suppliers}</div>
          <div class="kpi-note">Active tenant registry</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">HIGH RISK SUPPLIERS</div>
          <div class="kpi-value" style="color:#b54343">${state.stats.high_risk_count}</div>
          <div class="kpi-note">ISO 31000 score &ge; 40</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">DOCUMENTS EXPIRING</div>
          <div class="kpi-value" style="color:#9b6819">${state.stats.expiring_documents_count}</div>
          <div class="kpi-note">Expired or next 30 days</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">AVG SUPPLIER ESG SCORE</div>
          <div class="kpi-value" style="color:#16825a">${state.stats.average_esg_score}<span style="font-size:14px;color:#78838e">/100</span></div>
          <div class="kpi-note">Equal E / S / G weighting</div>
        </div>
      </div>

      <!-- Enterprise Baseline Policy Banner -->
      <div class="card" style="margin-bottom:18px;background:#f8fafc;border-left:4px solid ${state.baselinePolicy && state.baselinePolicy.is_configured ? '#16825a' : '#d97706'}">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
          <div>
            <div style="font-weight:700;font-size:14px;color:#1e293b;display:flex;align-items:center;gap:8px">
              Enterprise Baseline Policy Benchmark
              ${
                state.baselinePolicy && state.baselinePolicy.is_configured
                  ? '<span class="badge badge-low">CONFIGURED</span>'
                  : '<span class="badge badge-medium">ACTION REQUIRED</span>'
              }
            </div>
            <div style="font-size:12px;color:#64748b;margin-top:4px">
              ${
                state.baselinePolicy && state.baselinePolicy.is_configured
                  ? `Active Standard: <b>${escapeHtml(state.baselinePolicy.baseline_policy_name || "Enterprise Baseline")}</b> &bull; Ground-truth benchmark for Member 2 ISO 31000 policy comparisons.`
                  : "No baseline policy configured. Upload an enterprise baseline policy document (PDF/DOCX) to enable automated supplier policy comparisons with Member 2."
              }
            </div>
          </div>
          <div>
            <button class="btn btn-secondary btn-sm" id="btn-upload-baseline">
              ${state.baselinePolicy && state.baselinePolicy.is_configured ? "Update Baseline Policy" : "+ Upload Baseline Policy"}
            </button>
          </div>
        </div>
      </div>

      <!-- Main Supplier Register Card -->
      <div class="card">
        <div class="section-head">
          <div>
            <div style="display:flex;align-items:center;gap:10px">
              <h2>Supplier ESG Register</h2>
              ${
                !state.isLiveBackend
                  ? `<span class="badge badge-processing">MOCK MODE</span>`
                  : ""
              }
            </div>
            <p>Multi-tenant registry with ISO 31000 risk scoring, document compliance, and audit findings.</p>
          </div>
          <div class="toolbar">
            <input type="text" id="filter-search" class="filter" placeholder="Search name, code, country..." value="${escapeHtml(state.filters.search)}" style="min-width:210px">
            <select id="filter-category" class="filter">
              <option value="All">All Categories</option>
              <option value="Heavy Manufacturing" ${state.filters.category === "Heavy Manufacturing" ? "selected" : ""}>Heavy Manufacturing</option>
              <option value="Electronics & Hardware" ${state.filters.category === "Electronics & Hardware" ? "selected" : ""}>Electronics & Hardware</option>
              <option value="Logistics & Transport" ${state.filters.category === "Logistics & Transport" ? "selected" : ""}>Logistics & Transport</option>
              <option value="Packaging Materials" ${state.filters.category === "Packaging Materials" ? "selected" : ""}>Packaging Materials</option>
              <option value="Facilities & IT" ${state.filters.category === "Facilities & IT" ? "selected" : ""}>Facilities & IT</option>
              <option value="Raw Materials" ${state.filters.category === "Raw Materials" ? "selected" : ""}>Raw Materials</option>
            </select>
            <select id="filter-tier" class="filter">
              <option value="All">All Tiers</option>
              <option value="Tier 1" ${state.filters.tier === "Tier 1" ? "selected" : ""}>Tier 1</option>
              <option value="Tier 2" ${state.filters.tier === "Tier 2" ? "selected" : ""}>Tier 2</option>
              <option value="Tier 3" ${state.filters.tier === "Tier 3" ? "selected" : ""}>Tier 3</option>
            </select>
            <select id="filter-risk" class="filter">
              <option value="All">All Risk Levels</option>
              <option value="LOW" ${state.filters.risk_level === "LOW" ? "selected" : ""}>Low Risk (&lt;20)</option>
              <option value="MODERATE" ${state.filters.risk_level === "MODERATE" ? "selected" : ""}>Moderate Risk (20-39)</option>
              <option value="HIGH" ${state.filters.risk_level === "HIGH" ? "selected" : ""}>High Risk (40-67)</option>
              <option value="CRITICAL" ${state.filters.risk_level === "CRITICAL" ? "selected" : ""}>Critical Risk (&ge;68)</option>
            </select>
            <button class="btn btn-secondary btn-sm" id="btn-reset-filters" title="Reset all filters">Reset</button>
          </div>
        </div>

        <!-- Supplier Data Table -->
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Supplier Code & Name</th>
                <th>Category</th>
                <th>Tier</th>
                <th>Country</th>
                <th>ESG Score</th>
                <th>Env</th>
                <th>Soc</th>
                <th>Gov</th>
                <th>Docs</th>
                <th>ISO Risk</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${
                state.suppliers.length === 0
                  ? `<tr><td colspan="11" class="empty-state">No suppliers found matching the criteria.</td></tr>`
                  : state.suppliers
                      .map(
                        (sup) => `
                    <tr style="cursor:pointer;${s && s.id === sup.id ? "background:#f2f9f5;font-weight:600" : ""}" data-id="${sup.id}">
                      <td>
                        <div style="font-weight:750;color:#183c2f">${escapeHtml(sup.name)}</div>
                        <div style="font-size:10px;color:#78848c">${escapeHtml(sup.code)}</div>
                      </td>
                      <td>${escapeHtml(sup.category || "General")}</td>
                      <td><span class="badge badge-neutral">${escapeHtml(sup.tier || "Tier 1")}</span></td>
                      <td>${escapeHtml(sup.country || "—")}</td>
                      <td>
                        <div style="display:flex;align-items:center;gap:6px">
                          <span style="font-weight:800;font-size:13px">${Math.round(sup.overall_score || 0)}</span>
                          <span style="font-size:10px;color:#78848c">/100</span>
                        </div>
                        <div class="progress" style="width:70px;margin-top:3px"><span style="width:${Math.round(sup.overall_score || 0)}%"></span></div>
                      </td>
                      <td>${Math.round(sup.environmental_score || 0)}</td>
                      <td>${Math.round(sup.social_score || 0)}</td>
                      <td>${Math.round(sup.governance_score || 0)}</td>
                      <td><span class="pill-count">${sup.document_count || 0}</span></td>
                      <td>${renderRiskBadge(sup.risk_level)}</td>
                      <td>
                        <div style="display:flex;gap:6px">
                          <button class="btn btn-secondary btn-sm btn-select-sup" data-id="${sup.id}">Select</button>
                          <button class="btn btn-danger btn-sm btn-del-sup" data-id="${sup.id}" data-name="${escapeHtml(sup.name)}" title="Delete Supplier">&times;</button>
                        </div>
                      </td>
                    </tr>
                  `
                      )
                      .join("")
              }
            </tbody>
          </table>
        </div>

        <!-- Pagination Controls -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:14px;padding:4px 6px">
          <div style="font-size:11px;color:#78848c">
            Showing page <b>${state.page}</b> of <b>${state.totalPages}</b> (${state.total} total suppliers)
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn btn-secondary btn-sm" id="btn-prev-page" ${state.page <= 1 ? "disabled" : ""}>&larr; Previous</button>
            <button class="btn btn-secondary btn-sm" id="btn-next-page" ${state.page >= state.totalPages ? "disabled" : ""}>Next &rarr;</button>
          </div>
        </div>
      </div>

      <!-- Supplier Detail View (when selected) -->
      ${
        s
          ? `
        <div class="card" style="margin-top:18px">
          <div class="section-head">
            <div>
              <div style="display:flex;align-items:center;gap:10px">
                <h2>${escapeHtml(s.name)}</h2>
                <span class="badge badge-neutral">${escapeHtml(s.code)}</span>
                <span class="badge badge-neutral">${escapeHtml(s.tier)}</span>
                ${renderRiskBadge(s.risk_level)}
              </div>
              <p>Category: <b>${escapeHtml(s.category)}</b> &bull; Country: <b>${escapeHtml(s.country)}</b> &bull; Contact: <b>${escapeHtml(s.contact_person || "—")}</b> (${escapeHtml(s.contact_email)}) &bull; Status: <b>${escapeHtml(s.status)}</b></p>
            </div>
            <div id="eval-btn-wrap" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <button class="btn btn-primary btn-sm" id="btn-eval-policy" data-id="${s.id}" title="Run policy gap analysis against enterprise baseline using Member 2 risk engine">
                &#9881; Compare Policy (Member 2 Engine)
              </button>
              <button class="btn btn-secondary btn-sm" id="btn-eval-local" data-id="${s.id}" title="Recalculate ISO 31000 risk strictly from recorded findings and certificate expiry">
                &#8635; Recalculate Local Findings
              </button>
            </div>
          </div>

          <!-- Score Overview Grid -->
          <div class="grid-3" style="margin-bottom:18px">
            <div class="metric">
              <div class="label">Overall ESG Score</div>
              <div class="value" style="color:#16825a">${Math.round(s.overall_score || 0)}/100</div>
              <div class="progress" style="margin-top:8px"><span style="width:${Math.round(s.overall_score || 0)}%"></span></div>
            </div>
            <div class="metric">
              <div class="label">ISO 31000 Risk Level</div>
              <div class="value" style="font-size:18px;margin-top:8px">${renderRiskBadge(s.risk_level)}</div>
              <div style="font-size:11px;color:#78848c;margin-top:6px">
                ${s.risk_score !== null && s.risk_score !== undefined
                  ? `Risk Score: <b>${s.risk_score}</b>/100 (5x5 Matrix)`
                  : `Risk Score: <i>Not Assessed</i> (Pending evaluation)`}
              </div>
            </div>
            <div class="metric">
              <div class="label">Subscore Performance</div>
              <div style="font-size:11px;margin-top:6px;display:grid;gap:4px">
                <div>Environmental: <b>${Math.round(s.environmental_score || 0)}/100</b></div>
                <div>Social: <b>${Math.round(s.social_score || 0)}/100</b></div>
                <div>Governance: <b>${Math.round(s.governance_score || 0)}/100</b></div>
              </div>
            </div>
          </div>

          <!-- Detail Columns: Documents and Findings -->
          <div class="grid-2">
            <!-- Documents Column -->
            <div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                <h3 style="margin:0">Compliance Documents &amp; Certificates (${(s.documents || []).length})</h3>
                <button class="btn btn-secondary btn-sm" id="btn-open-doc-modal">+ Upload Doc</button>
              </div>

              <div class="table-wrap">
                <table class="data-table" style="min-width:100%">
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Category</th>
                      <th>Type</th>
                      <th>Expiry</th>
                      <th>Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${
                      (s.documents || []).length === 0
                        ? `<tr><td colspan="6" class="empty-state" style="padding:18px">No documents uploaded yet.</td></tr>`
                        : s.documents
                            .map(
                              (d) => `
                          <tr>
                            <td>
                              <div style="font-weight:700">${escapeHtml(d.title)}</div>
                              <div style="font-size:9px;color:#78848c">${formatDate(d.uploaded_at)}</div>
                            </td>
                            <td>
                              <span class="badge ${d.document_category === "POLICY" ? "badge-low" : d.document_category === "CERTIFICATE" ? "badge-neutral" : "badge-medium"}">
                                ${escapeHtml(d.document_category || "GENERAL")}
                              </span>
                            </td>
                            <td><span class="badge badge-neutral">${escapeHtml(d.document_type)}</span></td>
                            <td>${formatDate(d.expiry_date)}</td>
                            <td>${expiryBadge(d.expiry_status, d.days_until_expiry)}</td>
                            <td>
                              <button type="button" class="btn btn-secondary btn-sm btn-view-doc" data-supplier-id="${s.id}" data-doc-id="${d.id}" data-doc-title="${escapeHtml(d.title)}" style="font-size:10px;padding:2px 6px">
                                &#128190; View
                              </button>
                            </td>
                          </tr>
                        `
                            )
                            .join("")
                    }
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Findings & Recommendations Column -->
            <div>
              ${(() => {
                const rawFindings = s.findings || [];
                const uniqueFindings = [];
                const seenFindingKeys = new Set();
                rawFindings.forEach((f) => {
                  const key = ((f.title || "") + "::" + (f.category || "")).toLowerCase().trim();
                  if (!seenFindingKeys.has(key)) {
                    seenFindingKeys.add(key);
                    uniqueFindings.push(f);
                  }
                });
                return `
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                    <h3 style="margin:0">Audit Findings &amp; Recommendations (${uniqueFindings.length})</h3>
                    <button class="btn btn-secondary btn-sm" id="btn-open-finding-modal">+ Add Finding</button>
                  </div>

                  ${
                    uniqueFindings.length === 0
                      ? `<div class="empty-state" style="padding:22px">No open compliance findings. Performance is aligned with baseline.</div>`
                      : uniqueFindings
                          .map(
                            (f) => `
                        <div class="evidence" style="margin-bottom:10px">
                          <div style="display:flex;justify-content:space-between;align-items:center">
                            <span class="confidence">${escapeHtml(f.category).toUpperCase()} &bull; ISO SCORE: ${f.risk_score}/100</span>
                            ${badge(f.severity)}
                          </div>
                          <div class="row-title" style="margin-top:6px;font-size:13px">${escapeHtml(f.title)}</div>
                          <div class="quote">${escapeHtml(f.description)}</div>
                          <div class="small green-text" style="margin-top:8px;font-weight:700">
                            Recommendation: ${escapeHtml(f.recommendation)}
                          </div>
                        </div>
                      `
                          )
                          .join("")
                  }
                `;
              })()}
            </div>
          </div>
        </div>
      `
          : ""
      }

      <!-- Modal: Onboard New Supplier -->
      <div class="modal-backdrop" id="modal-onboard">
        <div class="modal">
          <div class="modal-head">
            <h3>Onboard New Supplier</h3>
            <button class="btn btn-ghost btn-sm" id="btn-close-onboard">&times;</button>
          </div>
          <div class="modal-body">
            <form id="form-onboard" class="form-grid">
              <div class="field">
                <label>Supplier Name *</label>
                <input type="text" name="name" required placeholder="e.g. Acme Components GmbH">
              </div>
              <div class="field">
                <label>Supplier Code *</label>
                <input type="text" name="code" required placeholder="e.g. SUP-007">
              </div>
              <div class="field">
                <label>Category *</label>
                <select name="category">
                  <option value="Heavy Manufacturing">Heavy Manufacturing</option>
                  <option value="Electronics & Hardware">Electronics & Hardware</option>
                  <option value="Logistics & Transport">Logistics & Transport</option>
                  <option value="Packaging Materials">Packaging Materials</option>
                  <option value="Facilities & IT">Facilities & IT</option>
                  <option value="Raw Materials">Raw Materials</option>
                </select>
              </div>
              <div class="field">
                <label>Supply Tier *</label>
                <select name="tier">
                  <option value="Tier 1">Tier 1 (Direct)</option>
                  <option value="Tier 2">Tier 2 (Component)</option>
                  <option value="Tier 3">Tier 3 (Commodity)</option>
                </select>
              </div>
              <div class="field">
                <label>Country *</label>
                <input type="text" name="country" required value="Germany">
              </div>
              <div class="field">
                <label>Contact Email *</label>
                <input type="email" name="contact_email" required placeholder="compliance@supplier.com">
              </div>
              <div class="field">
                <label>Contact Person</label>
                <input type="text" name="contact_person" placeholder="Hans Weber">
              </div>
              <div class="field">
                <label>Contact Phone</label>
                <input type="text" name="contact_phone" placeholder="+49 89 123456">
              </div>
              <div class="full" style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px">
                <button type="button" class="btn btn-secondary" id="btn-cancel-onboard">Cancel</button>
                <button type="submit" class="btn btn-primary" id="btn-submit-onboard">Save &amp; Onboard</button>
              </div>
            </form>
          </div>
        </div>
      </div>

      <!-- Modal: Upload Document -->
      <div class="modal-backdrop" id="modal-doc">
        <div class="modal">
          <div class="modal-head">
            <h3>Upload Compliance Document / Certificate</h3>
            <button class="btn btn-ghost btn-sm" id="btn-close-doc">&times;</button>
          </div>
          <div class="modal-body">
            <form id="form-doc" class="form-grid">
              <div class="field full">
                <label>Document Title *</label>
                <input type="text" name="title" required placeholder="e.g. ISO 14001 Environmental Standard 2026">
              </div>
              <div class="field">
                <label>Document Category *</label>
                <select name="document_category">
                  <option value="POLICY">Policy (Code of Conduct, Environmental, Labour)</option>
                  <option value="CERTIFICATE" selected>Certificate (ISO 14001, SA 8000, etc.)</option>
                  <option value="AUDIT_REPORT">Audit Report</option>
                  <option value="GENERAL">General / Other</option>
                </select>
              </div>
              <div class="field">
                <label>Document Type *</label>
                <select name="document_type">
                  <option value="ISO 14001">ISO 14001 (Environmental)</option>
                  <option value="ISO 45001">ISO 45001 (Health &amp; Safety)</option>
                  <option value="SA 8000">SA 8000 (Labour &amp; Social)</option>
                  <option value="Carbon Audit">Scope 1 &amp; 2 Carbon Audit</option>
                  <option value="Code of Conduct">Supplier Code of Conduct</option>
                  <option value="Environmental Policy">Environmental Policy</option>
                  <option value="Labour Policy">Labour Policy</option>
                  <option value="REACH / RoHS">REACH / RoHS Attestation</option>
                  <option value="Other ESG">Other ESG Document</option>
                </select>
              </div>
              <div class="field">
                <label>Certificate Expiry Date</label>
                <input type="date" name="expiry_date">
              </div>
              <div class="field full">
                <label>File (PDF, DOCX, XLSX, max 20MB) *</label>
                <input type="file" name="file" required accept=".pdf,.docx,.doc,.xlsx,.csv,.txt">
              </div>
              <div class="field full">
                <label>Audit Notes</label>
                <textarea name="notes" rows="2" placeholder="Verification notes or scope comments..."></textarea>
              </div>
              <div class="full" style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px">
                <button type="button" class="btn btn-secondary" id="btn-cancel-doc">Cancel</button>
                <button type="submit" class="btn btn-primary">Upload &amp; Verify</button>
              </div>
            </form>
          </div>
        </div>
      </div>

      <!-- Modal: Upload Enterprise Baseline Policy -->
      <div class="modal-backdrop" id="modal-baseline">
        <div class="modal">
          <div class="modal-head">
            <h3>Enterprise Baseline Policy Benchmark</h3>
            <button class="btn btn-ghost btn-sm" id="btn-close-baseline">&times;</button>
          </div>
          <div class="modal-body">
            <form id="form-baseline" class="form-grid">
              <div class="field full">
                <label>Baseline Policy Document (PDF or DOCX, max 20MB) *</label>
                <input type="file" name="file" required accept=".pdf,.docx,.doc,.txt">
                <small style="color:#78848c;margin-top:4px;display:block">
                  This enterprise baseline standard serves as ground-truth for automated policy gap analysis via Member 2's risk engine.
                </small>
              </div>
              <div class="full" style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">
                <button type="button" class="btn btn-secondary" id="btn-cancel-baseline">Cancel</button>
                <button type="submit" class="btn btn-primary">Upload Benchmark</button>
              </div>
            </form>
          </div>
        </div>
      </div>

      <!-- Modal: Add Finding -->
      <div class="modal-backdrop" id="modal-finding">
        <div class="modal">
          <div class="modal-head">
            <h3>Add Audit Finding &amp; ISO 31000 Recommendation</h3>
            <button class="btn btn-ghost btn-sm" id="btn-close-finding">&times;</button>
          </div>
          <div class="modal-body">
            <form id="form-finding" class="form-grid">
              <div class="field full">
                <label>Finding Title *</label>
                <input type="text" name="title" required placeholder="e.g. Waste treatment permit renewal delayed">
              </div>
              <div class="field">
                <label>Category *</label>
                <select name="category">
                  <option value="Environmental">Environmental</option>
                  <option value="Social">Social</option>
                  <option value="Governance">Governance</option>
                </select>
              </div>
              <div class="field">
                <label>Severity *</label>
                <select name="severity">
                  <option value="Critical">Critical</option>
                  <option value="High">High</option>
                  <option value="Medium" selected>Medium</option>
                  <option value="Low">Low</option>
                </select>
              </div>
              <div class="field">
                <label>Likelihood (1 to 5) *</label>
                <input type="number" name="likelihood" min="1" max="5" value="3" required>
              </div>
              <div class="field">
                <label>Impact (1 to 5) *</label>
                <input type="number" name="impact" min="1" max="5" value="3" required>
              </div>
              <div class="field full">
                <label>Finding Description *</label>
                <textarea name="description" rows="2" required placeholder="Evidence and observation details..."></textarea>
              </div>
              <div class="field full">
                <label>Audit Recommendation *</label>
                <textarea name="recommendation" rows="2" required placeholder="Corrective action required..."></textarea>
              </div>
              <div class="full" style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px">
                <button type="button" class="btn btn-secondary" id="btn-cancel-finding">Cancel</button>
                <button type="submit" class="btn btn-primary">Add Finding</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    bindEvents();
  }

  // Attach interactive UI listeners
  function bindEvents() {
    // Retry button if error
    const btnRetry = document.getElementById("btn-retry");
    if (btnRetry) btnRetry.onclick = () => loadData();

    // Filters
    const fSearch = document.getElementById("filter-search");
    if (fSearch) {
      let debounceTimer;
      fSearch.oninput = (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          state.filters.search = e.target.value.trim();
          state.page = 1;
          loadData();
        }, 300);
      };
    }

    const fCat = document.getElementById("filter-category");
    if (fCat) {
      fCat.onchange = (e) => {
        state.filters.category = e.target.value;
        state.page = 1;
        loadData();
      };
    }

    const fTier = document.getElementById("filter-tier");
    if (fTier) {
      fTier.onchange = (e) => {
        state.filters.tier = e.target.value;
        state.page = 1;
        loadData();
      };
    }

    const fRisk = document.getElementById("filter-risk");
    if (fRisk) {
      fRisk.onchange = (e) => {
        state.filters.risk_level = e.target.value;
        state.page = 1;
        loadData();
      };
    }

    const btnReset = document.getElementById("btn-reset-filters");
    if (btnReset) {
      btnReset.onclick = () => {
        state.filters = { search: "", category: "", tier: "", risk_level: "" };
        state.page = 1;
        loadData();
      };
    }

    // Pagination
    const btnPrev = document.getElementById("btn-prev-page");
    if (btnPrev) {
      btnPrev.onclick = () => {
        if (state.page > 1) {
          state.page--;
          loadData();
        }
      };
    }

    const btnNext = document.getElementById("btn-next-page");
    if (btnNext) {
      btnNext.onclick = () => {
        if (state.page < state.totalPages) {
          state.page++;
          loadData();
        }
      };
    }

    // Row selection
    document.querySelectorAll(".btn-select-sup").forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        selectSupplier(parseInt(btn.dataset.id, 10));
      };
    });

    document.querySelectorAll("tr[data-id]").forEach((row) => {
      row.onclick = () => {
        selectSupplier(parseInt(row.dataset.id, 10));
      };
    });

    // View/Download Compliance Document via Authenticated Fetch
    document.querySelectorAll(".btn-view-doc").forEach((btn) => {
      btn.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const supId = btn.getAttribute("data-supplier-id");
        const docId = btn.getAttribute("data-doc-id");
        const docTitle = btn.getAttribute("data-doc-title") || "document";
        const origHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = "&#8987; Loading...";
        try {
          const { blob, filename } = await ESGApi.supplierDownloadDoc(supId, docId);
          const blobUrl = window.URL.createObjectURL(blob);
          const win = window.open(blobUrl, "_blank");
          if (!win) {
            // Popup blocked by browser: fallback to programmatic anchor download
            const a = document.createElement("a");
            a.style.display = "none";
            a.href = blobUrl;
            a.download = filename || docTitle;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }
          setTimeout(() => {
            window.URL.revokeObjectURL(blobUrl);
          }, 60000);
        } catch (err) {
          toast("Error viewing document: " + err.message);
        } finally {
          btn.disabled = false;
          btn.innerHTML = origHtml;
        }
      };
    });

    // Delete supplier
    document.querySelectorAll(".btn-del-sup").forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        handleDelete(parseInt(btn.dataset.id, 10), btn.dataset.name);
      };
    });

    // Evaluate Risk Buttons (Member 2 Policy Comparison & Local Recalculation)
    const btnEvalPolicy = document.getElementById("btn-eval-policy");
    if (btnEvalPolicy) {
      btnEvalPolicy.onclick = () => {
        triggerEvaluation(parseInt(btnEvalPolicy.dataset.id, 10), true);
      };
    }

    const btnEvalLocal = document.getElementById("btn-eval-local");
    if (btnEvalLocal) {
      btnEvalLocal.onclick = () => {
        triggerEvaluation(parseInt(btnEvalLocal.dataset.id, 10), false);
      };
    }

    // Modal Triggers: Baseline Policy
    const btnUploadBaseline = document.getElementById("btn-upload-baseline");
    const modalBaseline = document.getElementById("modal-baseline");
    const btnCloseBaseline = document.getElementById("btn-close-baseline");
    const btnCancelBaseline = document.getElementById("btn-cancel-baseline");
    if (btnUploadBaseline && modalBaseline) {
      btnUploadBaseline.onclick = () => modalBaseline.classList.add("open");
      if (btnCloseBaseline) btnCloseBaseline.onclick = () => modalBaseline.classList.remove("open");
      if (btnCancelBaseline) btnCancelBaseline.onclick = () => modalBaseline.classList.remove("open");
    }

    const formBaseline = document.getElementById("form-baseline");
    if (formBaseline) {
      formBaseline.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(formBaseline);
        try {
          await ESGApi.baselinePolicyUpload(fd);
          toast("Enterprise baseline policy benchmark updated successfully.");
          modalBaseline.classList.remove("open");
          formBaseline.reset();
          await loadData();
        } catch (err) {
          toast("Baseline upload failed: " + err.message);
        }
      };
    }

    // Modal Triggers: Onboard
    const btnAddSup = document.getElementById("btn-add-supplier");
    const modalOnboard = document.getElementById("modal-onboard");
    const btnCloseOnboard = document.getElementById("btn-close-onboard");
    const btnCancelOnboard = document.getElementById("btn-cancel-onboard");
    if (btnAddSup && modalOnboard) {
      btnAddSup.onclick = () => modalOnboard.classList.add("open");
      if (btnCloseOnboard) btnCloseOnboard.onclick = () => modalOnboard.classList.remove("open");
      if (btnCancelOnboard) btnCancelOnboard.onclick = () => modalOnboard.classList.remove("open");
    }

    const formOnboard = document.getElementById("form-onboard");
    if (formOnboard) {
      formOnboard.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(formOnboard);
        const payload = {
          name: fd.get("name").trim(),
          code: fd.get("code").trim().toUpperCase(),
          category: fd.get("category"),
          tier: fd.get("tier"),
          country: fd.get("country").trim(),
          contact_email: fd.get("contact_email").trim(),
          contact_person: fd.get("contact_person").trim() || null,
          contact_phone: fd.get("contact_phone").trim() || null,
          status: "Active",
        };
        try {
          await ESGApi.supplierCreate(payload);
          toast(`Supplier "${payload.name}" onboarded successfully.`);
          modalOnboard.classList.remove("open");
          formOnboard.reset();
          await loadData();
        } catch (err) {
          toast("Onboard failed: " + err.message);
        }
      };
    }

    // Modal Triggers: Upload Doc
    const btnOpenDoc = document.getElementById("btn-open-doc-modal");
    const modalDoc = document.getElementById("modal-doc");
    const btnCloseDoc = document.getElementById("btn-close-doc");
    const btnCancelDoc = document.getElementById("btn-cancel-doc");
    if (btnOpenDoc && modalDoc) {
      btnOpenDoc.onclick = () => modalDoc.classList.add("open");
      if (btnCloseDoc) btnCloseDoc.onclick = () => modalDoc.classList.remove("open");
      if (btnCancelDoc) btnCancelDoc.onclick = () => modalDoc.classList.remove("open");
    }

    const formDoc = document.getElementById("form-doc");
    if (formDoc && state.selectedSupplier) {
      formDoc.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(formDoc);
        try {
          await ESGApi.supplierUploadDoc(state.selectedSupplier.id, fd);
          toast("Document uploaded and verified.");
          modalDoc.classList.remove("open");
          formDoc.reset();
          await selectSupplier(state.selectedSupplier.id);
        } catch (err) {
          toast("Upload failed: " + err.message);
        }
      };
    }

    // Modal Triggers: Add Finding
    const btnOpenFinding = document.getElementById("btn-open-finding-modal");
    const modalFinding = document.getElementById("modal-finding");
    const btnCloseFinding = document.getElementById("btn-close-finding");
    const btnCancelFinding = document.getElementById("btn-cancel-finding");
    if (btnOpenFinding && modalFinding) {
      btnOpenFinding.onclick = () => modalFinding.classList.add("open");
      if (btnCloseFinding) btnCloseFinding.onclick = () => modalFinding.classList.remove("open");
      if (btnCancelFinding) btnCancelFinding.onclick = () => modalFinding.classList.remove("open");
    }

    const formFinding = document.getElementById("form-finding");
    if (formFinding && state.selectedSupplier) {
      formFinding.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(formFinding);
        const payload = {
          title: fd.get("title").trim(),
          category: fd.get("category"),
          severity: fd.get("severity"),
          likelihood: parseInt(fd.get("likelihood"), 10),
          impact: parseInt(fd.get("impact"), 10),
          description: fd.get("description").trim(),
          recommendation: fd.get("recommendation").trim(),
          status: "Open",
        };
        try {
          await ESGApi.supplierCreateFinding(state.selectedSupplier.id, payload);
          toast("Finding recorded and ISO 31000 risk updated.");
          modalFinding.classList.remove("open");
          formFinding.reset();
          await selectSupplier(state.selectedSupplier.id);
        } catch (err) {
          toast("Finding creation failed: " + err.message);
        }
      };
    }
  }

  // Initial load
  loadData();
})();
