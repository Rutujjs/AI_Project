(function () {
  const app = document.getElementById("page-app");
  if (!app) return;

  app.innerHTML = `
    <div class="audit-filter-bar">
      <div>
        <label class="small muted" style="display:block;margin-bottom:3px;font-weight:700">STATUS FILTER</label>
        <select id="filter-unread-status">
          <option value="false">All Notifications</option>
          <option value="true">Unread Only</option>
        </select>
      </div>

      <div>
        <label class="small muted" style="display:block;margin-bottom:3px;font-weight:700">ALERT CATEGORY</label>
        <select id="filter-notif-category">
          <option value="">All Categories</option>
          <option value="DOCUMENT_EXPIRY">DOCUMENT_EXPIRY</option>
          <option value="SUPPLIER_RISK">SUPPLIER_RISK</option>
          <option value="POLICY">POLICY</option>
          <option value="SYSTEM">SYSTEM</option>
        </select>
      </div>

      <div style="margin-left:auto;align-self:flex-end">
        <button class="btn btn-primary" id="btn-apply-notif-filters">Filter Alerts</button>
      </div>
    </div>

    <div id="notif-summary-bar" style="margin-bottom:12px"></div>
    <div id="notif-content-area">
      <div style="padding:40px;text-align:center"><div class="spinner"></div><div class="muted small" style="margin-top:8px">Fetching live alerts…</div></div>
    </div>
  `;

  const summaryBar = document.getElementById("notif-summary-bar");
  const contentArea = document.getElementById("notif-content-area");

  async function loadNotifications() {
    contentArea.innerHTML = `<div style="padding:40px;text-align:center"><div class="spinner"></div><div class="muted small" style="margin-top:8px">Fetching live alerts…</div></div>`;

    const unreadOnly = document.getElementById("filter-unread-status").value === "true";
    const category = document.getElementById("filter-notif-category").value;

    const params = {
      unread_only: unreadOnly,
      limit: 50,
      offset: 0,
    };
    if (category) params.category = category;

    try {
      const data = await window.ESGApi.notificationList(params);

      summaryBar.innerHTML = `
        <div class="card" style="padding:10px 16px;display:flex;align-items:center;justify-content:space-between">
          <div class="small">
            Total Alerts: <b>${data.total}</b> &nbsp;|&nbsp;
            Unread Alerts: <b style="color:${data.unread_count > 0 ? '#b23535' : '#287954'}">${data.unread_count}</b>
          </div>
          <div class="small muted">
            Independent per-user read tracking active
          </div>
        </div>
      `;

      if (!data || !data.items || data.items.length === 0) {
        contentArea.innerHTML = `
          <div class="card" style="text-align:center;padding:48px 24px">
            <div style="font-size:32px;margin-bottom:8px">🔔</div>
            <h3>No Notifications Found</h3>
            <p class="muted small">All notifications have been reviewed or no records match the applied filters.</p>
          </div>
        `;
        return;
      }

      contentArea.innerHTML = `
        <div style="display:flex;flex-direction:column;gap:10px">
          ${data.items.map(n => {
            const isUnread = !n.is_read;
            const sev = (n.severity || "").toUpperCase();
            const sevCls = sev === "CRITICAL" ? "badge-critical" :
                           sev === "WARNING" ? "badge-warning" :
                           sev === "SUCCESS" ? "badge-success" : "badge-info";

            const timeStr = n.created_at ? new Date(n.created_at).toLocaleString() : "";

            return `
              <div class="card" style="padding:14px 16px;${isUnread ? 'background:#f6fbf9;border-color:#bfe3d1;' : ''}" id="page-notif-${n.id}">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
                  <div style="display:flex;align-items:center;gap:8px">
                    <span class="badge ${sevCls}">${escapeHtml(sev)}</span>
                    <span class="badge badge-neutral">${escapeHtml(n.category || 'GENERAL')}</span>
                    ${isUnread ? '<span class="badge badge-high" style="font-size:9px">UNREAD</span>' : '<span class="badge badge-neutral" style="font-size:9px">READ</span>'}
                  </div>
                  <div class="small muted">${escapeHtml(timeStr)}</div>
                </div>
                <h3 style="font-size:13px;font-weight:750;margin-bottom:4px;color:#23322e">${escapeHtml(n.title)}</h3>
                <p style="font-size:12px;color:#495852;line-height:1.5;margin-bottom:10px">${escapeHtml(n.message)}</p>
                <div style="display:flex;align-items:center;justify-content:space-between;border-top:1px solid #edf1ef;padding-top:8px">
                  <div style="font-size:11px">
                    ${n.link_url ? `<a href="${escapeHtml(n.link_url)}" class="btn btn-secondary" style="font-size:10px;padding:3px 10px">Open Related Module →</a>` : ''}
                  </div>
                  <div>
                    ${isUnread ? `<button class="btn btn-primary mark-read-btn" data-id="${n.id}" style="font-size:10px;padding:3px 10px">✓ Mark as Read</button>` : '<span class="small muted">Acknowledged</span>'}
                  </div>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      `;

      contentArea.querySelectorAll(".mark-read-btn").forEach(btn => {
        btn.onclick = async () => {
          const id = btn.dataset.id;
          try {
            await window.ESGApi.notificationMarkRead(id);
            toast("Notification marked as read");
            loadNotifications();
            if (window.refreshTopNotificationBadge) window.refreshTopNotificationBadge();
          } catch (err) {
            toast("Error marking read: " + err.message);
          }
        };
      });

    } catch (err) {
      contentArea.innerHTML = `
        <div class="card" style="text-align:center;padding:36px;color:#b23535">
          <h3>Failed to Load Notifications</h3>
          <p class="small muted">${escapeHtml(err.message)}</p>
          <button class="btn btn-secondary" id="btn-retry-notifs" style="margin-top:12px">↻ Retry</button>
        </div>
      `;
      const retryBtn = document.getElementById("btn-retry-notifs");
      if (retryBtn) retryBtn.onclick = () => loadNotifications();
    }
  }

  document.getElementById("btn-apply-notif-filters").onclick = () => loadNotifications();
  const refreshAction = document.getElementById("page-refresh-action");
  if (refreshAction) refreshAction.onclick = () => loadNotifications();

  const markAllBtn = document.getElementById("page-mark-all-read-btn");
  if (markAllBtn) {
    markAllBtn.onclick = async () => {
      try {
        const res = await window.ESGApi.notificationMarkAllRead();
        toast(res && res.message ? res.message : "All notifications marked as read");
        loadNotifications();
        if (window.refreshTopNotificationBadge) window.refreshTopNotificationBadge();
      } catch (err) {
        toast("Error marking all read: " + err.message);
      }
    };
  }

  loadNotifications();
})();

