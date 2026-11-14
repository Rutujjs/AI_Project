(function () {
  const app = document.getElementById("page-app");
  if (!app) return;

  const currentRole = (sessionStorage.getItem("esg_user_role") || "").toLowerCase();
  const isAuthorized = currentRole === "admin" || currentRole === "auditor";

  if (!isAuthorized) {
    app.innerHTML = `
      <div class="audit-restricted card">
        <div style="font-size:32px;margin-bottom:8px">🔒</div>
        <div class="badge badge-high" style="margin-bottom:12px;font-size:11px">ROLE RESTRICTION ENFORCED (HTTP 403)</div>
        <h2>Access Restricted: Audit Trail Reserved for Governance Roles</h2>
        <p class="muted" style="max-width:560px;margin:8px auto 0;font-size:12px;line-height:1.6">
          In compliance with SOC 2, ISO 27001, and corporate multi-tenant governance standards, access to immutable platform audit records is restricted to <b>Administrator</b> and <b>Lead Auditor</b> accounts. Your current account role (<b>${escapeHtml(currentRole.toUpperCase() || 'UNKNOWN')}</b>) does not have sufficient clearance to review audit logs.
        </p>
        <div style="margin-top:20px">
          <a href="index.html" class="btn btn-secondary">← Return to Dashboard</a>
        </div>
      </div>
    `;
    return;
  }

  // Authorized Admin / Auditor view
  app.innerHTML = `
    <div class="audit-filter-bar">
      <div>
        <label class="small muted" style="display:block;margin-bottom:3px;font-weight:700">EVENT ACTION</label>
        <select id="filter-action">
          <option value="">All Actions</option>
          <option value="LOGIN_SUCCESS">LOGIN_SUCCESS</option>
          <option value="LOGIN_FAILURE">LOGIN_FAILURE</option>
          <option value="LOGOUT">LOGOUT</option>
          <option value="SUPPLIER_CREATED">SUPPLIER_CREATED</option>
          <option value="SUPPLIER_UPDATED">SUPPLIER_UPDATED</option>
          <option value="SUPPLIER_DELETED">SUPPLIER_DELETED</option>
          <option value="DOCUMENT_UPLOADED">DOCUMENT_UPLOADED</option>
          <option value="DOCUMENT_DOWNLOADED">DOCUMENT_DOWNLOADED</option>
          <option value="SUPPLIER_EVALUATED">SUPPLIER_EVALUATED</option>
          <option value="BASELINE_POLICY_UPLOADED">BASELINE_POLICY_UPLOADED</option>
          <option value="REPORT_PREVIEWED">REPORT_PREVIEWED</option>
          <option value="REPORT_EXPORTED_PDF">REPORT_EXPORTED_PDF</option>
        </select>
      </div>

      <div>
        <label class="small muted" style="display:block;margin-bottom:3px;font-weight:700">RESOURCE TYPE</label>
        <select id="filter-resource">
          <option value="">All Resources</option>
          <option value="USER">USER</option>
          <option value="SUPPLIER">SUPPLIER</option>
          <option value="DOCUMENT">DOCUMENT</option>
          <option value="REPORT">REPORT</option>
          <option value="ORGANIZATION">ORGANIZATION</option>
        </select>
      </div>

      <div>
        <label class="small muted" style="display:block;margin-bottom:3px;font-weight:700">PAGE SIZE</label>
        <select id="filter-limit">
          <option value="25">25 records</option>
          <option value="50" selected>50 records</option>
          <option value="100">100 records</option>
        </select>
      </div>

      <div style="margin-left:auto;align-self:flex-end">
        <button class="btn btn-primary" id="btn-apply-filters">Apply Filters</button>
      </div>
    </div>

    <div id="audit-content-area">
      <div style="padding:40px;text-align:center"><div class="spinner"></div><div class="muted small" style="margin-top:8px">Loading immutable audit records…</div></div>
    </div>

    <div id="audit-detail-modal" class="notif-panel" style="display:none;width:520px;max-height:80vh;top:50%;left:50%;transform:translate(-50%,-50%)">
      <div class="notif-panel-head">
        <h3 id="modal-title">Audit Record Details</h3>
        <button class="btn btn-secondary" id="modal-close-btn" style="padding:2px 8px">✕</button>
      </div>
      <div class="notif-panel-body" id="modal-body" style="max-height:60vh;padding:16px;font-family:monospace;font-size:11px;background:#fbfcfc"></div>
    </div>
  `;

  const contentArea = document.getElementById("audit-content-area");
  const modal = document.getElementById("audit-detail-modal");
  const modalTitle = document.getElementById("modal-title");
  const modalBody = document.getElementById("modal-body");
  const modalClose = document.getElementById("modal-close-btn");

  modalClose.onclick = () => { modal.style.display = "none"; };

  async function loadAuditLogs() {
    contentArea.innerHTML = `<div style="padding:40px;text-align:center"><div class="spinner"></div><div class="muted small" style="margin-top:8px">Loading immutable audit records…</div></div>`;

    const action = document.getElementById("filter-action").value;
    const resource = document.getElementById("filter-resource").value;
    const limit = parseInt(document.getElementById("filter-limit").value, 10) || 50;

    const params = { limit: limit, offset: 0 };
    if (action) params.action = action;
    if (resource) params.resource_type = resource;

    try {
      const data = await window.ESGApi.auditLogsList(params);

      if (!data || !data.items || data.items.length === 0) {
        contentArea.innerHTML = `
          <div class="card" style="text-align:center;padding:48px 24px">
            <div style="font-size:28px;margin-bottom:8px">📋</div>
            <h3>No Audit Records Found</h3>
            <p class="muted small">No audit log entries match the currently applied criteria.</p>
          </div>
        `;
        return;
      }

      contentArea.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <div class="small muted">Displaying <b>${data.items.length}</b> of <b>${data.total}</b> immutable log entries</div>
          <div class="small muted">Strict Tenant Isolation Enforced</div>
        </div>
        <div class="audit-table-wrap">
          <table class="audit-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Timestamp (UTC)</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Actor (Username)</th>
                <th>Role</th>
                <th>Status</th>
                <th>IP Address</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              ${data.items.map(item => {
                const isFail = (item.status || "").toUpperCase() === "FAILURE";
                const statusBadge = isFail
                  ? '<span class="badge badge-high">FAILURE</span>'
                  : '<span class="badge badge-low">SUCCESS</span>';

                const timeStr = item.created_at ? new Date(item.created_at).toISOString().replace("T", " ").substring(0, 19) : "";
                const detailsJson = item.details ? JSON.stringify(item.details, null, 2) : "{}";

                return `
                  <tr>
                    <td>#${item.id}</td>
                    <td style="white-space:nowrap">${escapeHtml(timeStr)}</td>
                    <td><b>${escapeHtml(item.action)}</b></td>
                    <td><code>${escapeHtml(item.resource_type)}${item.resource_id ? ' #' + escapeHtml(item.resource_id) : ''}</code></td>
                    <td>${escapeHtml(item.username)}</td>
                    <td><span class="badge badge-neutral">${escapeHtml(item.user_role || 'N/A')}</span></td>
                    <td>${statusBadge}</td>
                    <td><span class="muted">${escapeHtml(item.ip_address || '—')}</span></td>
                    <td>
                      <button class="audit-json-btn" data-json="${escapeHtml(detailsJson)}" data-title="Audit #${item.id}: ${escapeHtml(item.action)}">Inspect</button>
                    </td>
                  </tr>
                `;
              }).join("")}
            </tbody>
          </table>
        </div>
      `;

      contentArea.querySelectorAll(".audit-json-btn").forEach(btn => {
        btn.onclick = () => {
          modalTitle.textContent = btn.dataset.title;
          modalBody.innerHTML = `<pre style="margin:0;white-space:pre-wrap">${escapeHtml(btn.dataset.json)}</pre>`;
          modal.style.display = "flex";
        };
      });

    } catch (err) {
      const isForbidden = err.message && (err.message.includes("403") || err.message.toLowerCase().includes("forbidden"));
      if (isForbidden) {
        contentArea.innerHTML = `
          <div class="audit-restricted card">
            <div class="badge badge-high" style="margin-bottom:12px;font-size:11px">ACCESS FORBIDDEN (HTTP 403)</div>
            <h2>Audit Log Access Forbidden</h2>
            <p class="muted small">${escapeHtml(err.message)}</p>
          </div>
        `;
      } else {
        contentArea.innerHTML = `
          <div class="card" style="text-align:center;padding:36px;color:#b23535">
            <h3>Unable to Load Audit Logs</h3>
            <p class="small muted">${escapeHtml(err.message)}</p>
            <button class="btn btn-secondary" id="btn-retry-audit" style="margin-top:12px">↻ Retry Connection</button>
          </div>
        `;
        const retryBtn = document.getElementById("btn-retry-audit");
        if (retryBtn) retryBtn.onclick = () => loadAuditLogs();
      }
    }
  }

  document.getElementById("btn-apply-filters").onclick = () => loadAuditLogs();
  const refreshAction = document.getElementById("page-refresh-action");
  if (refreshAction) refreshAction.onclick = () => loadAuditLogs();

  loadAuditLogs();
})();

