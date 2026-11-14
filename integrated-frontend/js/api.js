window.ESGApi=(function(){
// Dedicated base URL resolvers with fallback to backward-compatible localStorage keys and environment defaults
var POLICY_BASE=function(){
  return (
    localStorage.getItem("esg_policy_api_base") ||
    localStorage.getItem("esg_api_base") ||
    "http://localhost:8000"
  ).replace(/\/$/,"");
};

var PLATFORM_BASE=function(){
  return (
    localStorage.getItem("esg_platform_api_base") ||
    localStorage.getItem("esg_doc_api_base") ||
    "http://localhost:8001"
  ).replace(/\/$/,"");
};

// Aliases for backward compatibility
var BASE=POLICY_BASE;
var DOC_BASE=PLATFORM_BASE;

async function request(path,opts,baseUrl){
  var url=(baseUrl||PLATFORM_BASE())+path;var res;
  opts=opts||{};
  opts.headers=opts.headers||{};
  var token=localStorage.getItem("esg_access_token")||sessionStorage.getItem("esg_access_token");
  if(token&&!opts.headers["Authorization"]){
    opts.headers["Authorization"]="Bearer "+token;
  }
  try{res=await fetch(url,opts);}catch(err){throw new Error("Network error: "+err.message);}
  var data=null;try{data=await res.json();}catch(_){}
  if(!res.ok)throw new Error((data&&(data.detail||data.message))||"Request failed ("+res.status+")");
  return data;
}

/* ── Member 2: Policy Intelligence (Port 8000) ── */
function health(){return request("/health",{},POLICY_BASE());}
function fullAnalysis(oldFile,newFile,useAI){
  var fd=new FormData();fd.append("old_policy",oldFile);fd.append("new_policy",newFile);
  return request("/api/full-analysis?use_ai_recommendations="+(useAI===false?"false":"true"),{method:"POST",body:fd},POLICY_BASE());
}

/* ── Member 1: Document Intelligence & RAG (Port 8001) ── */
function docHealth(){return request("/health",{},PLATFORM_BASE());}
function uploadDocument(file){var fd=new FormData();fd.append("file",file);return request("/documents/upload",{method:"POST",body:fd},PLATFORM_BASE());}
function analyzeESG(document_id){return request("/documents/analyze-esg",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({document_id:document_id})},PLATFORM_BASE());}
function askDocument(query,n_results){return request("/documents/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:query,n_results:n_results||3})},PLATFORM_BASE());}
function searchDocuments(query,n_results){return request("/documents/search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:query,n_results:n_results||3})},PLATFORM_BASE());}

/* ── Member 3: Green Software Intelligence (Port 8001) ── */
var j=function(b){return{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)};};
function greenHealth(){return request("/green/health",{},PLATFORM_BASE());}
function greenConnect(token,demo){return request("/green/github/connect",j({token:token||null,demo:!!demo}),PLATFORM_BASE());}
function greenListAccounts(){return request("/green/github/accounts",{},PLATFORM_BASE());}
function greenDeleteAccount(id){return request("/green/github/accounts/"+id,{method:"DELETE"},PLATFORM_BASE());}
function greenListRepos(accountId){return request("/green/github/accounts/"+accountId+"/repositories",{},PLATFORM_BASE());}
function greenListBranches(repoId){return request("/green/github/repositories/"+repoId+"/branches",{},PLATFORM_BASE());}
function greenListPRs(repoId,state){return request("/green/github/repositories/"+repoId+"/pulls?state="+(state||"open"),{},PLATFORM_BASE());}
function greenGetPR(repoId,prNum){return request("/green/github/repositories/"+repoId+"/pulls/"+prNum,{},PLATFORM_BASE());}
function greenAnalyze(repositoryId,prNumber){return request("/green/analysis/analyze",j({repository_id:repositoryId,pr_number:prNumber}),PLATFORM_BASE());}
function greenGetResults(prId){return request("/green/analysis/results/"+prId,{},PLATFORM_BASE());}
function greenListScores(){return request("/green/analysis/scores",{},PLATFORM_BASE());}

/* ── Member 4: Cloud & Carbon Module (Port 8001) ── */
function cloudCarbonHealth(){return request("/api/cloud-carbon/health",{},PLATFORM_BASE());}
function cloudCarbonUpload(file){
  var fd=new FormData();
  fd.append("file",file);
  return request("/api/cloud-carbon/upload",{method:"POST",body:fd},PLATFORM_BASE());
}
function cloudCarbonPreview(uploadId){
  return request("/api/cloud-carbon/preview/"+uploadId,{},PLATFORM_BASE());
}
function cloudCarbonConfirmMapping(uploadId,mapping){
  return request("/api/cloud-carbon/confirm-mapping/"+uploadId,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({mapping:mapping})
  },PLATFORM_BASE());
}
function cloudCarbonAnomalyDetection(uploadId,opts){
  return request("/api/cloud-carbon/anomaly-detection/"+uploadId,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(opts||{})
  },PLATFORM_BASE());
}
function cloudCarbonEstimateEmissions(uploadId,opts){
  return request("/api/cloud-carbon/estimate-emissions/"+uploadId,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(opts||{})
  },PLATFORM_BASE());
}
function cloudCarbonAnalyze(uploadId,anomalyOpts,emissionsOpts){
  return request("/api/cloud-carbon/analyze/"+uploadId,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({
      anomaly_req: anomalyOpts||null,
      emissions_req: emissionsOpts||null
    })
  },PLATFORM_BASE());
}
function cloudCarbonGetAnalysis(uploadId){
  return request("/api/cloud-carbon/analysis/"+uploadId,{},PLATFORM_BASE());
}
function cloudCarbonGetRecommendations(uploadId){
  return request("/api/cloud-carbon/recommendations/"+uploadId,{},PLATFORM_BASE());
}
function cloudCarbonGenerateRecommendations(uploadId,forceRuleBased){
  var q=forceRuleBased?"?force_rule_based=true":"";
  return request("/api/cloud-carbon/recommendations/"+uploadId+q,{method:"POST"},PLATFORM_BASE());
}

/* ── Member 5: Platform & Supplier Intelligence (Port 8001) ── */
async function authLogin(username,password){
  var res=await request("/api/auth/login",j({username:username,password:password}),PLATFORM_BASE());
  if(res&&res.access_token){
    localStorage.setItem("esg_access_token",res.access_token);
    sessionStorage.setItem("esg_access_token",res.access_token);
    sessionStorage.setItem("esg_demo_authenticated","1");
  }
  return res;
}
function authMe(){return request("/api/auth/me",{},PLATFORM_BASE());}
async function authLogout(){
  try{await request("/api/auth/logout",{method:"POST"},PLATFORM_BASE());}catch(_){}
  localStorage.removeItem("esg_access_token");
  sessionStorage.removeItem("esg_access_token");
  sessionStorage.removeItem("esg_demo_authenticated");
}
function supplierStats(){return request("/api/suppliers/stats",{},PLATFORM_BASE());}
function supplierList(params){
  var q="";
  if(params){
    var pairs=[];
    for(var k in params){
      if(params[k]!==undefined&&params[k]!==null&&params[k]!=="")pairs.push(encodeURIComponent(k)+"="+encodeURIComponent(params[k]));
    }
    if(pairs.length)q="?"+pairs.join("&");
  }
  return request("/api/suppliers"+q,{},PLATFORM_BASE());
}
function supplierGet(id){return request("/api/suppliers/"+id,{},PLATFORM_BASE());}
function supplierCreate(data){return request("/api/suppliers",j(data),PLATFORM_BASE());}
function supplierUpdate(id,data){return request("/api/suppliers/"+id,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)},PLATFORM_BASE());}
function supplierDelete(id){return request("/api/suppliers/"+id,{method:"DELETE"},PLATFORM_BASE());}
function supplierUploadDoc(id,formData){return request("/api/suppliers/"+id+"/documents",{method:"POST",body:formData},PLATFORM_BASE());}
function supplierListDocs(id){return request("/api/suppliers/"+id+"/documents",{},PLATFORM_BASE());}
async function supplierDownloadDoc(id, docId){
  var url = PLATFORM_BASE() + "/api/suppliers/" + encodeURIComponent(id) + "/documents/" + encodeURIComponent(docId) + "/download";
  var token = localStorage.getItem("esg_access_token") || sessionStorage.getItem("esg_access_token");
  var headers = {};
  if (token) {
    headers["Authorization"] = "Bearer " + token;
  }
  var res;
  try {
    res = await fetch(url, { headers: headers });
  } catch(err) {
    throw new Error("Network error during document download: " + err.message);
  }
  if (!res.ok) {
    var errData = null;
    try { errData = await res.json(); } catch(_) {}
    throw new Error((errData && (errData.detail || errData.message)) || ("Document download failed (" + res.status + ")"));
  }
  var blob = await res.blob();
  var cd = res.headers.get("Content-Disposition") || "";
  var filename = "document";
  var match = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  if (match && match[1]) {
    filename = match[1].replace(/['"]/g, "").trim();
  }
  return { blob: blob, filename: filename };
}
function supplierListFindings(id){return request("/api/suppliers/"+id+"/findings",{},PLATFORM_BASE());}
function supplierCreateFinding(id,data){return request("/api/suppliers/"+id+"/findings",j(data),PLATFORM_BASE());}
function supplierEvaluate(id,docId,policyComparison){
  var q=[];
  if(docId)q.push("document_id="+encodeURIComponent(docId));
  if(policyComparison!==undefined)q.push("policy_comparison="+(policyComparison?"true":"false"));
  var qs=q.length?"?"+q.join("&"):"";
  return request("/api/suppliers/"+id+"/evaluate"+qs,{method:"POST"},PLATFORM_BASE());
}
function baselinePolicyGet(){return request("/api/platform/organizations/current/baseline-policy",{},PLATFORM_BASE());}
function baselinePolicyUpload(formData){return request("/api/platform/organizations/current/baseline-policy",{method:"POST",body:formData},PLATFORM_BASE());}
function dashboardMetrics(params){
  var q="";
  if(params){
    var pairs=[];
    for(var k in params){
      if(params[k]!==undefined&&params[k]!==null&&params[k]!=="")pairs.push(encodeURIComponent(k)+"="+encodeURIComponent(params[k]));
    }
    if(pairs.length)q="?"+pairs.join("&");
  }
  return request("/api/platform/dashboard"+q,{},PLATFORM_BASE());
}

/* ── Member 5: Enterprise Reporting & PDF Export (Port 8001) ── */
function reportTypes(){
  return request("/api/platform/reports/types",{},PLATFORM_BASE());
}
function reportPreview(data){
  return request("/api/platform/reports/preview", j(data), PLATFORM_BASE());
}
async function reportExportPdf(data){
  var url = PLATFORM_BASE() + "/api/platform/reports/export-pdf";
  var headers = { "Content-Type": "application/json" };
  var token = localStorage.getItem("esg_access_token") || sessionStorage.getItem("esg_access_token");
  if(token){
    headers["Authorization"] = "Bearer " + token;
  }
  var res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: headers,
      body: JSON.stringify(data)
    });
  } catch(err) {
    throw new Error("Network error during PDF export: " + err.message);
  }
  if(!res.ok){
    var errData = null;
    try { errData = await res.json(); } catch(_){}
    throw new Error((errData && (errData.detail || errData.message)) || ("PDF export failed (" + res.status + ")"));
  }
  var blob = await res.blob();
  var cd = res.headers.get("Content-Disposition") || "";
  var filename = "esg-report.pdf";
  var match = cd.match(/filename="?([^"]+)"?/);
  if(match && match[1]){
    filename = match[1];
  }
  return { blob: blob, filename: filename };
}

/* ── Member 5: Audit Logging & Notification Management (Port 8001) ── */
function auditLogsList(params){
  var q="";
  if(params){
    var pairs=[];
    for(var k in params){
      if(params[k]!==undefined&&params[k]!==null&&params[k]!=="")pairs.push(encodeURIComponent(k)+"="+encodeURIComponent(params[k]));
    }
    if(pairs.length)q="?"+pairs.join("&");
  }
  return request("/api/platform/audit-logs"+q,{},PLATFORM_BASE());
}
function notificationList(params){
  var q="";
  if(params){
    var pairs=[];
    for(var k in params){
      if(params[k]!==undefined&&params[k]!==null&&params[k]!=="")pairs.push(encodeURIComponent(k)+"="+encodeURIComponent(params[k]));
    }
    if(pairs.length)q="?"+pairs.join("&");
  }
  return request("/api/platform/notifications"+q,{},PLATFORM_BASE());
}
function notificationUnreadCount(){
  return request("/api/platform/notifications/unread-count",{},PLATFORM_BASE());
}
function notificationMarkRead(id){
  return request("/api/platform/notifications/"+encodeURIComponent(id)+"/read",{method:"PATCH"},PLATFORM_BASE());
}
function notificationMarkAllRead(){
  return request("/api/platform/notifications/mark-all-read",{method:"POST"},PLATFORM_BASE());
}

return{
  policyBase:POLICY_BASE,
  platformBase:PLATFORM_BASE,
  base:PLATFORM_BASE,
  docBase:PLATFORM_BASE,
  health:health,
  fullAnalysis:fullAnalysis,
  docHealth:docHealth,uploadDocument:uploadDocument,analyzeESG:analyzeESG,askDocument:askDocument,searchDocuments:searchDocuments,
  greenHealth:greenHealth,greenConnect:greenConnect,greenListAccounts:greenListAccounts,
  greenDeleteAccount:greenDeleteAccount,greenListRepos:greenListRepos,greenListBranches:greenListBranches,
  greenListPRs:greenListPRs,greenGetPR:greenGetPR,greenAnalyze:greenAnalyze,
  greenGetResults:greenGetResults,greenListScores:greenListScores,
  cloudCarbonHealth:cloudCarbonHealth,cloudCarbonUpload:cloudCarbonUpload,
  cloudCarbonPreview:cloudCarbonPreview,cloudCarbonConfirmMapping:cloudCarbonConfirmMapping,
  cloudCarbonAnomalyDetection:cloudCarbonAnomalyDetection,
  cloudCarbonEstimateEmissions:cloudCarbonEstimateEmissions,
  cloudCarbonAnalyze:cloudCarbonAnalyze,
  cloudCarbonGetAnalysis:cloudCarbonGetAnalysis,
  cloudCarbonGetRecommendations:cloudCarbonGetRecommendations,
  cloudCarbonGenerateRecommendations:cloudCarbonGenerateRecommendations,
  authLogin:authLogin,authMe:authMe,authLogout:authLogout,
  supplierStats:supplierStats,supplierList:supplierList,supplierGet:supplierGet,
  supplierCreate:supplierCreate,supplierUpdate:supplierUpdate,supplierDelete:supplierDelete,
  supplierUploadDoc:supplierUploadDoc,supplierListDocs:supplierListDocs,supplierDownloadDoc:supplierDownloadDoc,
  supplierListFindings:supplierListFindings,supplierCreateFinding:supplierCreateFinding,
  supplierEvaluate:supplierEvaluate,
  baselinePolicyGet:baselinePolicyGet,baselinePolicyUpload:baselinePolicyUpload,
  dashboardMetrics:dashboardMetrics,
  reportTypes:reportTypes,reportPreview:reportPreview,reportExportPdf:reportExportPdf,
  auditLogsList:auditLogsList,
  notificationList:notificationList,
  notificationUnreadCount:notificationUnreadCount,
  notificationMarkRead:notificationMarkRead,
  notificationMarkAllRead:notificationMarkAllRead
};
})();