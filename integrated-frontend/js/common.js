(function(){
const curRole=(sessionStorage.getItem("esg_user_role")||"admin").toLowerCase();
const curName=sessionStorage.getItem("esg_user_name")||"Enterprise User";
const initials=curName.split(" ").map(w=>w[0]).join("").substring(0,2).toUpperCase()||"EU";
const nav=[
 ["index.html","Dashboard","▦",""],
 ["documents.html","Document Center","▤",""],
 ["policy-checker.html","Policy Checker","⌁","v2 vs v1"],
 ["suppliers.html","Suppliers","♧","120"],
 ["green-code.html","Green Code","⌘","3"],
 ["cloud-carbon.html","Cloud & Carbon","◌","3"],
 ["risks.html","ESG Risk Center","△","5"],
 ["insights.html","AI Insights","✦","5 recs"],
 ["reports.html","ESG Reports","▥",""]
];
const page=document.body.dataset.page||"dashboard";
const activeFile=page==="dashboard"?"index.html":page+".html";
document.getElementById("app-shell").innerHTML=`
<aside class="app-sidebar" id="sidebar">
 <div class="brand"><div class="brand-mark">E</div><div class="brand-title">ESG Intelligence</div><div class="brand-sub">Enterprise Sustainability Platform</div></div>
 <div class="nav-label">NAVIGATION</div><nav class="side-nav">${nav.map(n=>`<a class="nav-item ${n[0]===activeFile?'active':''}" href="${n[0]}"><span class="nav-icon">${n[2]}</span><span>${n[1]}</span>${n[3]?`<span class="nav-badge ${n[1]==='ESG Risk Center'?'red':''}">${n[3]}</span>`:''}</a>`).join("")}</nav>
 <div class="sidebar-bottom"><div class="profile-mini"><div class="avatar">${initials}</div><div><div class="name">${curName}</div><div class="role">${curRole.toUpperCase()}</div></div></div></div>
</aside><div class="sidebar-overlay" id="sidebar-overlay"></div>`;
const titleMap={dashboard:"ESG Dashboard",documents:"Document Center","policy-checker":"Policy Intelligence & Checker",suppliers:"Supplier Intelligence","green-code":"Green Code","cloud-carbon":"Cloud & Carbon",risks:"ESG Risk Center",insights:"AI Insights",reports:"ESG Reports",settings:"Settings","audit-logs":"Platform Audit Logs",notifications:"Notifications & Alerts"};
document.getElementById("topbar").innerHTML=`
<header class="topbar"><button class="top-icon mobile-menu" id="mobile-menu">☰</button><div class="top-title">${titleMap[page]||"ESG Intelligence"}</div>
<div class="org-select">Acme Global Logistics Corp <span class="muted">⌄</span></div>
<div class="top-actions">
  <div class="search-box"><span class="search-icon">⌕</span><input id="global-search" placeholder="Search ESG data..."></div>
  <div style="position:relative">
    <button class="top-icon notif-btn" id="top-notif-btn" title="Platform Notifications">🔔<span id="top-notif-badge" class="notif-badge" style="display:none">0</span></button>
    <div id="notif-dropdown" class="notif-panel" style="display:none"></div>
  </div>
  <button class="top-icon" data-toast="Workspace synced" title="Sync Status">↻</button>
  <div class="top-avatar" title="${curName} (${curRole.toUpperCase()})">${initials}</div>
</div></header>`;
const side=document.getElementById("sidebar"), overlay=document.getElementById("sidebar-overlay"), menu=document.getElementById("mobile-menu");
if(menu)menu.onclick=()=>{side.classList.toggle("open");overlay.classList.toggle("open")};
if(overlay)overlay.onclick=()=>{side.classList.remove("open");overlay.classList.remove("open")};
document.querySelectorAll("[data-toast]").forEach(el=>el.addEventListener("click",()=>toast(el.dataset.toast)));
window.toast=function(msg){let c=document.querySelector(".toast-container");if(!c){c=document.createElement("div");c.className="toast-container";document.body.appendChild(c)}let t=document.createElement("div");t.className="toast";t.textContent=msg;c.appendChild(t);setTimeout(()=>t.remove(),2600)};
window.escapeHtml=function(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))};
window.badge=function(v){const x=String(v||"").toLowerCase();const cls=x.includes("high")||x.includes("critical")||x.includes("error")||x.includes("weakened")||x.includes("removed")?"badge-high":x.includes("medium")||x.includes("warning")||x.includes("changed")||x.includes("modified")?"badge-medium":x.includes("low")||x.includes("success")||x.includes("strengthened")||x.includes("added")?"badge-low":"badge-neutral";return `<span class="badge ${cls}">${escapeHtml(v)}</span>`};
window.loading=function(el,msg="Loading..."){el.innerHTML=`<div class="loading-state"><div class="spinner"></div><div class="muted">${escapeHtml(msg)}</div></div>`};
window.apiBase=function(){return localStorage.getItem("esg_api_base")||"http://localhost:8000"};

// ── Notification Center Dropdown Handler ──
let unreadFilter = false;
async function refreshTopNotificationBadge(){
  const badgeEl = document.getElementById("top-notif-badge");
  if(!badgeEl || !window.ESGApi || !window.ESGApi.notificationUnreadCount) return;
  try {
    const res = await window.ESGApi.notificationUnreadCount();
    if(res && typeof res.unread_count === "number"){
      if(res.unread_count > 0){
        badgeEl.textContent = res.unread_count > 99 ? "99+" : String(res.unread_count);
        badgeEl.style.display = "inline-block";
      } else {
        badgeEl.style.display = "none";
      }
    }
  } catch(_){}
}

async function renderNotificationDropdown(){
  const dd = document.getElementById("notif-dropdown");
  if(!dd || !window.ESGApi || !window.ESGApi.notificationList) return;
  dd.innerHTML = `<div class="notif-panel-head">
    <h3>Notifications</h3>
    <div style="display:flex;gap:6px;align-items:center">
      <button class="btn btn-secondary" style="padding:2px 8px;font-size:10px" id="notif-filter-toggle">${unreadFilter ? "Show All" : "Unread Only"}</button>
      <button class="btn btn-secondary" style="padding:2px 8px;font-size:10px" id="notif-mark-all-btn">Mark All Read</button>
    </div>
  </div>
  <div class="notif-panel-body" id="notif-panel-list">
    <div style="padding:20px;text-align:center"><div class="spinner"></div><div class="small muted">Loading alerts…</div></div>
  </div>
  <div style="padding:8px 14px;border-top:1px solid #edf1ef;text-align:center;background:#fafcfb">
    <a href="notifications.html" style="font-size:11px;font-weight:700;color:#2b8c69;text-decoration:none">View Notification Management Center →</a>
  </div>`;

  document.getElementById("notif-filter-toggle").onclick = (e) => {
    e.stopPropagation();
    unreadFilter = !unreadFilter;
    renderNotificationDropdown();
  };
  document.getElementById("notif-mark-all-btn").onclick = async (e) => {
    e.stopPropagation();
    try {
      await window.ESGApi.notificationMarkAllRead();
      toast("All notifications marked as read");
      refreshTopNotificationBadge();
      renderNotificationDropdown();
    } catch(err){
      toast("Failed to mark all read: " + err.message);
    }
  };

  const listEl = document.getElementById("notif-panel-list");
  try {
    const data = await window.ESGApi.notificationList({ unread_only: unreadFilter, limit: 15 });
    if(!data || !data.items || data.items.length === 0){
      listEl.innerHTML = `<div style="padding:24px 12px;text-align:center;color:#879590;font-size:11px">No ${unreadFilter ? 'unread ' : ''}notifications</div>`;
      return;
    }
    listEl.innerHTML = data.items.map(n => {
      const isUnread = !n.is_read;
      const sevCls = (n.severity || "").toLowerCase() === "critical" ? "badge-critical" :
                     (n.severity || "").toLowerCase() === "warning" ? "badge-warning" : "badge-info";
      const timeStr = n.created_at ? new Date(n.created_at).toLocaleString() : "";
      return `<div class="notif-item ${isUnread ? 'unread' : ''}" id="notif-item-${n.id}">
        <div class="notif-meta">
          <span class="badge ${sevCls}">${escapeHtml(n.severity || 'INFO')}</span>
          <span class="muted" style="font-size:9px">${escapeHtml(n.category || 'SYSTEM')}</span>
          <span class="notif-time">${escapeHtml(timeStr)}</span>
        </div>
        <div class="notif-title">${escapeHtml(n.title)}</div>
        <div class="notif-msg">${escapeHtml(n.message)}</div>
        <div class="notif-actions">
          ${n.link_url ? `<a href="${escapeHtml(n.link_url)}">Inspect & Action →</a>` : ''}
          ${isUnread ? `<button class="btn btn-secondary notif-read-btn" data-id="${n.id}">Mark read</button>` : '<span class="muted small" style="margin-left:auto;font-size:9px">Read</span>'}
        </div>
      </div>`;
    }).join("");

    listEl.querySelectorAll(".notif-read-btn").forEach(btn => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;
        try {
          await window.ESGApi.notificationMarkRead(id);
          refreshTopNotificationBadge();
          renderNotificationDropdown();
        } catch(err){
          toast("Error: " + err.message);
        }
      };
    });
  } catch(err) {
    listEl.innerHTML = `<div style="padding:16px;text-align:center;color:#b23535;font-size:11px">Failed to load notifications: ${escapeHtml(err.message)}<div style="margin-top:8px"><button class="btn btn-secondary" id="notif-retry-btn" style="font-size:10px;padding:3px 8px">Retry</button></div></div>`;
    const retryBtn = document.getElementById("notif-retry-btn");
    if(retryBtn) retryBtn.onclick = () => renderNotificationDropdown();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const notifBtn = document.getElementById("top-notif-btn");
  const dropdown = document.getElementById("notif-dropdown");
  if(notifBtn && dropdown){
    notifBtn.onclick = (e) => {
      e.stopPropagation();
      const isOpen = dropdown.style.display !== "none";
      if(isOpen){
        dropdown.style.display = "none";
      } else {
        dropdown.style.display = "flex";
        renderNotificationDropdown();
      }
    };
    document.addEventListener("click", (e) => {
      if(!dropdown.contains(e.target) && e.target !== notifBtn){
        dropdown.style.display = "none";
      }
    });
  }
  refreshTopNotificationBadge();
});
})();