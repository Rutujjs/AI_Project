const app = document.getElementById("page-app");
const currentPolicy = localStorage.getItem("esg_policy_api_base") || localStorage.getItem("esg_api_base") || "http://localhost:8000";
const currentPlatform = localStorage.getItem("esg_platform_api_base") || localStorage.getItem("esg_doc_api_base") || "http://localhost:8001";

app.innerHTML = `
<div class="grid-2">
  <section class="card">
    <div class="section-head"><div><h2>Organization</h2><p>Workspace identity and reporting context.</p></div></div>
    <div class="form-grid">
      <div class="field full"><label>Company Name</label><input value="Acme Global Logistics Corp"></div>
      <div class="field"><label>Industry</label><select><option>Logistics & Transportation</option><option>Manufacturing</option><option>Technology</option></select></div>
      <div class="field"><label>Reporting Period</label><select><option>FY 2025–26</option><option>FY 2024–25</option></select></div>
    </div>
  </section>

  <section class="card">
    <div class="section-head"><div><h2>Backend Connections</h2><p>Dual-backend microservice architecture configuration.</p></div></div>
    <div class="field">
      <label>Core Platform & Intelligence Backend URL <span class="badge badge-neutral" style="margin-left:6px">port 8001</span></label>
      <input id="doc-api-url" value="${escapeHtml(currentPlatform)}">
      <div class="small muted">Powers Auth, Dashboard, Documents (RAG), Green Software, Cloud Carbon, Suppliers, Reporting, Audit, and Notifications (Members 1, 3, 4, 5).</div>
    </div>
    <div class="field" style="margin-top:14px">
      <label>Policy Intelligence Backend URL <span class="badge badge-neutral" style="margin-left:6px">port 8000</span></label>
      <input id="api-url" value="${escapeHtml(currentPolicy)}">
      <div class="small muted">Powers Policy Checker, commitment extraction, and side-by-side comparison (Member 2).</div>
    </div>
    <div class="toolbar" style="margin-top:14px">
      <button class="btn btn-primary" id="save-api">Save Configuration</button>
      <button class="btn btn-secondary" id="test-doc">Test Platform (8001)</button>
      <button class="btn btn-secondary" id="test-policy">Test Policy (8000)</button>
      <span id="api-result"></span>
    </div>
  </section>

  <section class="card">
    <div class="section-head"><div><h2>ESG Configuration</h2><p>Risk thresholds and scoring weights.</p></div></div>
    <div class="form-grid">
      <div class="field"><label>High Risk Threshold</label><input value="70"></div>
      <div class="field"><label>Medium Risk Threshold</label><input value="40"></div>
      <div class="field"><label>Environmental Weight</label><input value="40%"></div>
      <div class="field"><label>Social Weight</label><input value="30%"></div>
      <div class="field"><label>Governance Weight</label><input value="30%"></div>
    </div>
  </section>

  <section class="card">
    <div class="section-head"><div><h2>Account</h2><p>Current workspace administrator.</p></div></div>
    <div style="display:flex;align-items:center;gap:11px">
      <div class="avatar">PS</div>
      <div><b>Pragati Sahu</b><div class="small muted">Project Admin</div></div>
    </div>
    <button class="btn btn-danger" style="margin-top:15px" data-toast="Logout is disabled in this demo">Logout</button>
  </section>
</div>

<div class="card" style="margin-top:16px">
  <div class="section-head"><div><h2>Architecture & Service Startup Guide</h2><p>How the two backend services and frontend orchestrate together.</p></div></div>
  <div class="grid-2">
    <div class="evidence">
      <div class="confidence">CORE PLATFORM BACKEND (port 8001) — Members 1, 3, 4, 5</div>
      <div class="quote" style="margin-top:8px">
        <code>cd AI_ESG_Platform/backend</code><br>
        <code>venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8001</code>
      </div>
    </div>
    <div class="evidence">
      <div class="confidence">POLICY INTELLIGENCE BACKEND (port 8000) — Member 2</div>
      <div class="quote" style="margin-top:8px">
        <code>cd "esg-enterprise-frontend-complete (2)/esg-enterprise-frontend-complete/esg-cr/backend"</code><br>
        <code>..\\..\\..\\.venv\\Scripts\\python.exe -m uvicorn main:app --port 8000</code>
      </div>
    </div>
  </div>
</div>`;

document.getElementById("save-api").onclick = () => {
  const policyVal = document.getElementById("api-url").value.replace(/\/$/, "");
  const platformVal = document.getElementById("doc-api-url").value.replace(/\/$/, "");
  localStorage.setItem("esg_policy_api_base", policyVal);
  localStorage.setItem("esg_api_base", policyVal);
  localStorage.setItem("esg_platform_api_base", platformVal);
  localStorage.setItem("esg_doc_api_base", platformVal);
  toast("Backend URLs saved successfully");
};

document.getElementById("test-policy").onclick = async () => {
  const r = document.getElementById("api-result");
  r.innerHTML = `<span class="small muted">Testing Policy (8000)…</span>`;
  try {
    await ESGApi.health();
    r.innerHTML = badge("Policy (8000): Connected");
  } catch (err) {
    r.innerHTML = badge("Policy (8000): Offline");
  }
};

document.getElementById("test-doc").onclick = async () => {
  const r = document.getElementById("api-result");
  r.innerHTML = `<span class="small muted">Testing Platform (8001)…</span>`;
  try {
    await ESGApi.docHealth();
    r.innerHTML = badge("Platform (8001): Connected");
  } catch (err) {
    r.innerHTML = badge("Platform (8001): Offline");
  }
};
