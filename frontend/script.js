const API_BASE = "";
let sessionId = window.localStorage.getItem("constructionbot-session") || null;
let selectedFiles = [];
let authToken = localStorage.getItem("constructionbot-token") || null;
let currentUser = JSON.parse(localStorage.getItem("constructionbot-user") || "null");

// Authentication state
function isAuthenticated() {
    return authToken !== null && currentUser !== null;
}

// API helper with authentication
async function apiCall(endpoint, options = {}) {
    // Always get the latest token from localStorage in case it was updated
    const token = localStorage.getItem("constructionbot-token") || authToken;
    
    const headers = {
        ...options.headers,
    };
    
    // Don't set Content-Type for FormData (browser will set it with boundary)
    if (!(options.body instanceof FormData)) {
        headers["Content-Type"] = headers["Content-Type"] || "application/json";
    }
    
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }
    
    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
    });
    
    if (response.status === 401) {
        // Token expired or invalid
        logout();
        return null;
    }
    
    return response;
}

// Initialize authentication
function initAuth() {
    if (isAuthenticated()) {
        showApp();
        updateUserInfo();
    } else {
        showAuthModal();
    }
}

function showAuthModal() {
    document.getElementById("auth-modal").style.display = "flex";
    document.getElementById("app-wrapper").style.display = "none";
}

function showApp() {
    document.getElementById("auth-modal").style.display = "none";
    document.getElementById("app-wrapper").style.display = "flex";
}

function updateUserInfo() {
    if (currentUser) {
        document.getElementById("user-name").textContent = currentUser.name || currentUser.email.split("@")[0];
        document.getElementById("user-email").textContent = currentUser.email;
        document.getElementById("user-info").style.display = "flex";
    }
}

function logout() {
    authToken = null;
    currentUser = null;
    sessionId = null;
    localStorage.removeItem("constructionbot-token");
    localStorage.removeItem("constructionbot-user");
    localStorage.removeItem("constructionbot-session");
    showAuthModal();
    // Clear messages
    if (messagesEl) {
        messagesEl.innerHTML = "";
    }
}

// Login handler
document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("login-form");
    const registerForm = document.getElementById("register-form");
    const switchToRegister = document.getElementById("switch-to-register");
    const switchToLogin = document.getElementById("switch-to-login");
    const logoutBtn = document.getElementById("logout-btn");
    const authTitle = document.getElementById("auth-title");
    const authSubtitle = document.getElementById("auth-subtitle");
    
    // Switch between login and register
    function showRegisterForm() {
        if (loginForm) {
            loginForm.classList.remove("active");
            loginForm.style.display = "none";
        }
        if (registerForm) {
            registerForm.classList.add("active");
            registerForm.style.display = "block";
        }
        if (authTitle) authTitle.textContent = "Create Your Account";
        if (authSubtitle) authSubtitle.textContent = "Get started with ConstructionBot";
    }
    
    function showLoginForm() {
        if (registerForm) {
            registerForm.classList.remove("active");
            registerForm.style.display = "none";
        }
        if (loginForm) {
            loginForm.classList.add("active");
            loginForm.style.display = "block";
        }
        if (authTitle) authTitle.textContent = "Welcome to ConstructionBot";
        if (authSubtitle) authSubtitle.textContent = "Sign in to access your workspace";
    }
    
    if (switchToRegister) {
        switchToRegister.onclick = function(e) {
            e.preventDefault();
            e.stopPropagation();
            showRegisterForm();
            return false;
        };
    }
    
    if (switchToLogin) {
        switchToLogin.onclick = function(e) {
            e.preventDefault();
            e.stopPropagation();
            showLoginForm();
            return false;
        };
    }
    
    // Login form submission
    loginForm?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("login-email").value;
        const password = document.getElementById("login-password").value;
        const errorEl = document.getElementById("login-error");
        
        errorEl.textContent = "";
        
        try {
            const response = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password }),
            });
            
            const data = await response.json();
            
            if (response.ok && data.success) {
                authToken = data.access_token;
                currentUser = data.user;
                localStorage.setItem("constructionbot-token", authToken);
                localStorage.setItem("constructionbot-user", JSON.stringify(currentUser));
                // Reload page to ensure everything initializes properly
                window.location.reload();
            } else {
                errorEl.textContent = data.detail || "Invalid email or password";
            }
        } catch (error) {
            errorEl.textContent = "Network error. Please try again.";
        }
    });
    
    // Register form submission
    registerForm?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("register-name").value;
        const email = document.getElementById("register-email").value;
        const password = document.getElementById("register-password").value;
        const confirm = document.getElementById("register-confirm").value;
        const errorEl = document.getElementById("register-error");
        
        errorEl.textContent = "";
        
        if (password !== confirm) {
            errorEl.textContent = "Passwords do not match";
            return;
        }
        
        if (password.length < 6) {
            errorEl.textContent = "Password must be at least 6 characters";
            return;
        }
        
        if (password.length > 72) {
            errorEl.textContent = "Password cannot be longer than 72 characters";
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE}/api/auth/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password, name: name || null }),
            });
            
            const data = await response.json();
            
            if (response.ok && data.success) {
                authToken = data.access_token;
                currentUser = data.user;
                localStorage.setItem("constructionbot-token", authToken);
                localStorage.setItem("constructionbot-user", JSON.stringify(currentUser));
                // Reload page to ensure everything initializes properly
                window.location.reload();
            } else {
                errorEl.textContent = data.detail || "Registration failed. Please try again.";
            }
        } catch (error) {
            errorEl.textContent = "Network error. Please try again.";
        }
    });
    
    // Logout handler
    logoutBtn?.addEventListener("click", logout);
    
    // Initialize auth on page load
    initAuth();
});

// DOM Elements
const navButtons = document.querySelectorAll(".nav-button");
const views = document.querySelectorAll(".view");
const uploadForm = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const fileList = document.getElementById("file-list");
const uploadBtn = document.getElementById("upload-btn");
const uploadStatus = document.getElementById("upload-status");
const filesList = document.getElementById("files-list");
const refreshFilesBtn = document.getElementById("refresh-files-btn");
const messagesEl = document.getElementById("messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const newChatBtn = document.getElementById("new-chat-btn");
const fileDropzone = document.querySelector(".file-dropzone");
const uploadModal = document.getElementById("upload-modal");
const openUploadModalBtn = document.getElementById("open-upload-modal-btn");
const closeUploadModalBtn = document.getElementById("close-upload-modal-btn");

// Navigation
navButtons.forEach(button => {
    button.addEventListener("click", () => {
        const viewName = button.dataset.view;
        
        // Update active states
        navButtons.forEach(btn => btn.classList.remove("active"));
        views.forEach(view => view.classList.remove("active"));
        
        button.classList.add("active");
        const viewElement = document.getElementById(`${viewName}-view`);
        viewElement.classList.add("active");
        
        // Set default tabs when switching views
        if (viewName === "notifications") {
            // Activate SMTP Settings tab
            const smtpTab = viewElement.querySelector('[data-tab="smtp"]');
            const smtpTabContent = viewElement.querySelector('#smtp-tab');
            if (smtpTab && smtpTabContent) {
                // Remove active from all notification tabs
                viewElement.querySelectorAll('.tab-button').forEach(t => t.classList.remove("active"));
                viewElement.querySelectorAll('.tab-content').forEach(c => c.classList.remove("active"));
                // Activate SMTP tab
                smtpTab.classList.add("active");
                smtpTabContent.classList.add("active");
                loadSMTPConfigs();
            }
        } else if (viewName === "erp") {
            // Activate Payments tab
            const paymentsTab = viewElement.querySelector('[data-tab="payments"]');
            const paymentsTabContent = viewElement.querySelector('#payments-tab');
            if (paymentsTab && paymentsTabContent) {
                // Remove active from all ERP tabs
                viewElement.querySelectorAll('#erp-view .tab-button').forEach(t => t.classList.remove("active"));
                viewElement.querySelectorAll('#erp-view .tab-content').forEach(c => c.classList.remove("active"));
                // Activate Payments tab
                paymentsTab.classList.add("active");
                paymentsTabContent.classList.add("active");
                loadPayments();
            }
        }
    });
});

// Modal Handling
openUploadModalBtn.addEventListener("click", () => {
    uploadModal.classList.add("active");
    document.body.style.overflow = "hidden";
});

closeUploadModalBtn.addEventListener("click", () => {
    closeModal();
});

uploadModal.addEventListener("click", (e) => {
    if (e.target === uploadModal) {
        closeModal();
    }
});

// Close modal on Escape key
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && uploadModal.classList.contains("active")) {
        closeModal();
    }
});

function closeModal() {
    uploadModal.classList.remove("active");
    document.body.style.overflow = "";
    // Reset form if needed
    if (selectedFiles.length === 0) {
        selectedFiles = [];
        fileInput.value = "";
        updateFileList();
        updateUploadButton();
        uploadStatus.classList.remove("show");
    }
}

// File Upload Handling
fileInput.addEventListener("change", (e) => {
    selectedFiles = Array.from(e.target.files);
    updateFileList();
    updateUploadButton();
});

// Drag and drop
fileDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    fileDropzone.classList.add("drag-over");
});

fileDropzone.addEventListener("dragleave", () => {
    fileDropzone.classList.remove("drag-over");
});

fileDropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    fileDropzone.classList.remove("drag-over");
    const files = Array.from(e.dataTransfer.files);
    selectedFiles = [...selectedFiles, ...files];
    updateFileList();
    updateUploadButton();
});

function updateFileList() {
    fileList.innerHTML = "";
    if (selectedFiles.length === 0) {
        fileList.style.display = "none";
        return;
    }
    
    fileList.style.display = "flex";
    selectedFiles.forEach((file, index) => {
        const fileItem = document.createElement("div");
        fileItem.className = "file-item";
        fileItem.innerHTML = `
            <span class="file-name">${escapeHtml(file.name)}</span>
            <span class="file-size">${formatFileSize(file.size)}</span>
            <button class="file-remove" data-index="${index}" type="button">×</button>
        `;
        fileList.appendChild(fileItem);
    });

    document.querySelectorAll(".file-remove").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const index = parseInt(e.target.dataset.index);
            selectedFiles.splice(index, 1);
            updateFileList();
            updateUploadButton();
        });
    });
}

function updateUploadButton() {
    uploadBtn.disabled = selectedFiles.length === 0;
}

function formatFileSize(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (selectedFiles.length === 0) {
        showUploadStatus("Please select at least one file.", "error");
        return;
    }

    uploadBtn.disabled = true;
    showUploadStatus("Uploading and processing files...", "loading");

    const formData = new FormData();
    selectedFiles.forEach(file => formData.append("files", file));

    try {
        const response = await apiCall(`/api/upload`, {
            method: "POST",
            body: formData,
        });

        if (!response || !response.ok) {
            const errorText = await response.text();
            throw new Error(errorText);
        }

        const data = await response.json();
        showUploadStatus(
            `Successfully uploaded ${data.files_uploaded} file(s). ` +
            `Processed: ${data.pdf_count || 0} PDFs, ${data.docx_count || 0} DOCX, ` +
            `${data.pptx_count || 0} PPTX, ${data.csv_count || 0} CSVs, ` +
            `${data.excel_count || 0} Excel files, ${data.image_count || 0} images.`,
            "success"
        );
        
        selectedFiles = [];
        fileInput.value = "";
        updateFileList();
        updateUploadButton();
        
        // Close modal after successful upload
        setTimeout(() => {
            closeModal();
        }, 1500);
        
        // Refresh files list
        loadFiles();
    } catch (error) {
        console.error(error);
        showUploadStatus(`Upload failed: ${error.message}`, "error");
    } finally {
        uploadBtn.disabled = false;
    }
});

function showUploadStatus(message, type) {
    uploadStatus.textContent = message;
    uploadStatus.className = `upload-status ${type} show`;
    
    if (type === "success") {
        setTimeout(() => {
            uploadStatus.classList.remove("show");
        }, 5000);
    }
}

// File Management
async function loadFiles() {
    try {
        const response = await apiCall(`/api/files`);
        if (!response.ok) throw new Error("Failed to load files");
        const data = await response.json();
        displayFiles(data.files);
    } catch (error) {
        console.error(error);
        filesList.innerHTML = `<div class="error-state">Failed to load files: ${error.message}</div>`;
    }
}

function displayFiles(files) {
    if (files.length === 0) {
        filesList.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📁</div>
                <h3 class="empty-title">No files uploaded yet</h3>
                <p class="empty-description">Upload files to build your knowledge base</p>
            </div>
        `;
        return;
    }

    filesList.innerHTML = files.map(file => `
        <div class="file-card">
            <div class="file-card-header">
                <div class="file-type-icon">${getFileIcon(file.type)}</div>
                <div class="file-card-info">
                    <div class="file-card-name">${escapeHtml(file.filename)}</div>
                    <div class="file-card-meta">${formatFileSize(file.size_bytes)} • ${formatDate(file.uploaded_at)}</div>
                </div>
            </div>
            <div class="file-card-actions">
                <button class="delete-file-btn" data-file-id="${escapeHtml(file.id)}">Delete</button>
            </div>
        </div>
    `).join("");

    document.querySelectorAll(".delete-file-btn").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            const fileId = e.target.dataset.fileId;
            if (confirm("Are you sure you want to delete this file?")) {
                try {
                    const response = await apiCall(`/api/files/${encodeURIComponent(fileId)}`, {
                        method: "DELETE",
                    });
                    if (!response.ok) throw new Error("Failed to delete file");
                    loadFiles();
                } catch (error) {
                    console.error(error);
                    alert(`Failed to delete file: ${error.message}`);
                }
            }
        });
    });
}

function getFileIcon(type) {
    const icons = {
        pdf: "📄",
        docx: "📝",
        pptx: "📊",
        csv: "📈",
        excel: "📊",
        image: "🖼️",
        unknown: "📎"
    };
    return icons[type] || icons.unknown;
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + " " + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

refreshFilesBtn.addEventListener("click", loadFiles);

// Chat Functionality
const appendMessage = (role, text, isLoading = false) => {
    const bubble = document.createElement("div");
    bubble.classList.add("message", role);
    if (isLoading) bubble.classList.add("loading");
    
    const avatar = role === "user" ? "👤" : "🤖";
    
    bubble.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">${role === "user" ? escapeHtml(text) : formatMarkdown(text)}</div>
    `;
    
    messagesEl.appendChild(bubble);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return bubble;
};

function formatMarkdown(text) {
    // Simple markdown formatting
    text = escapeHtml(text);
    text = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/\*(.*?)\*/g, "<em>$1</em>");
    text = text.replace(/\n/g, "<br>");
    return text;
}

const resetSession = () => {
    sessionId = null;
    window.localStorage.removeItem("constructionbot-session");
    messagesEl.innerHTML = "";
    appendMessage(
        "ai",
        "Hello! I'm ConstructionBot, your AI assistant for construction compliance and planning. " +
        "I can help you analyze documents, spreadsheets, and answer questions about your projects. " +
        "Upload files in the Knowledge Base section, then ask me anything!"
    );
};

newChatBtn.addEventListener("click", resetSession);

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;
    
    appendMessage("user", message);
    chatInput.value = "";
    const loadingBubble = appendMessage("ai", "Thinking...", true);

    try {
        const response = await apiCall(`/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message,
                session_id: sessionId,
            }),
        });
        
        if (!response || !response.ok) {
            const errorText = await response.text();
            throw new Error(errorText);
        }
        
        const data = await response.json();
        sessionId = data.session_id;
        window.localStorage.setItem("constructionbot-session", sessionId);
        loadingBubble.remove();
        appendMessage("ai", data.response);
    } catch (error) {
        console.error(error);
        loadingBubble.remove();
        appendMessage("ai", `Sorry, I encountered an error: ${error.message}. Please try again.`);
    }
});

// Initialize
loadFiles();
resetSession();

// ==================== NOTIFICATIONS FUNCTIONALITY ====================

// Notification DOM Elements
const notificationTabs = document.querySelectorAll("#notifications-view .tab-button");
const tabContents = document.querySelectorAll("#notifications-view .tab-content");
const smtpList = document.getElementById("smtp-list");
const recipientsList = document.getElementById("recipients-list");
const schedulesList = document.getElementById("schedules-list");
const historyList = document.getElementById("history-list");
const recipientTypeFilter = document.getElementById("recipient-type-filter");

// Modals
const smtpModal = document.getElementById("smtp-modal");
const recipientModal = document.getElementById("recipient-modal");
const scheduleModal = document.getElementById("schedule-modal");

// Tab switching
notificationTabs.forEach(tab => {
    tab.addEventListener("click", () => {
        const tabName = tab.dataset.tab;
        notificationTabs.forEach(t => t.classList.remove("active"));
        tabContents.forEach(c => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(`${tabName}-tab`).classList.add("active");
        
        // Load data when switching tabs
        if (tabName === "smtp") loadSMTPConfigs();
        else if (tabName === "recipients") loadRecipients();
        else if (tabName === "schedules") loadSchedules();
        else if (tabName === "history") loadHistory();
    });
});

// SMTP Config Functions
document.getElementById("add-smtp-btn")?.addEventListener("click", () => {
    document.getElementById("smtp-modal-title").textContent = "Add SMTP Configuration";
    document.getElementById("smtp-form").reset();
    document.getElementById("smtp-id").value = "";
    smtpModal.classList.add("active");
});

document.getElementById("close-smtp-modal-btn")?.addEventListener("click", () => {
    smtpModal.classList.remove("active");
});

document.getElementById("smtp-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("smtp-id").value;
    const data = {
        name: document.getElementById("smtp-name").value,
        host: document.getElementById("smtp-host").value,
        port: parseInt(document.getElementById("smtp-port").value),
        username: document.getElementById("smtp-username").value,
        password: document.getElementById("smtp-password").value,
        from_email: document.getElementById("smtp-from-email").value,
        from_name: document.getElementById("smtp-from-name").value,
        use_tls: document.getElementById("smtp-use-tls").checked
    };
    
    try {
        const url = id ? `/api/notifications/smtp/${id}` : "/api/notifications/smtp";
        const method = id ? "PUT" : "POST";
        const response = await apiCall(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        if (response && response.ok) {
            smtpModal.classList.remove("active");
            loadSMTPConfigs();
        } else {
            alert("Error saving SMTP config");
        }
    } catch (error) {
        alert("Error: " + error.message);
    }
});

async function loadSMTPConfigs() {
    try {
        const response = await apiCall("/api/notifications/smtp");
        if (!response || !response.ok) {
            console.error("Failed to load SMTP configs:", response?.status);
            return;
        }
        const data = await response.json();
        smtpList.innerHTML = data.configs.length === 0 
            ? "<div class='empty-state'><p>No SMTP configurations. Add one to get started.</p></div>"
            : data.configs.map(config => `
                <div class="config-card">
                    <h3>${config.name}</h3>
                    <p><strong>Host:</strong> ${config.host}:${config.port}</p>
                    <p><strong>From:</strong> ${config.from_email}</p>
                    <div class="card-actions">
                        <button onclick="editSMTP(${config.id})">Edit</button>
                        <button onclick="deleteSMTP(${config.id})" class="delete-btn">Delete</button>
                    </div>
                </div>
            `).join("");
    } catch (error) {
        console.error("Error loading SMTP configs:", error);
    }
}

window.editSMTP = async function(id) {
    const response = await apiCall(`/api/notifications/smtp/${id}`);
    const data = await response.json();
    const config = data.config;
    document.getElementById("smtp-id").value = id;
    document.getElementById("smtp-name").value = config.name;
    document.getElementById("smtp-host").value = config.host;
    document.getElementById("smtp-port").value = config.port;
    document.getElementById("smtp-username").value = config.username;
    document.getElementById("smtp-password").value = ""; // Don't show password
    document.getElementById("smtp-from-email").value = config.from_email;
    document.getElementById("smtp-from-name").value = config.from_name || "";
    document.getElementById("smtp-use-tls").checked = config.use_tls;
    document.getElementById("smtp-modal-title").textContent = "Edit SMTP Configuration";
    smtpModal.classList.add("active");
};

window.deleteSMTP = async function(id) {
    if (!confirm("Delete this SMTP configuration?")) return;
    try {
        const response = await apiCall(`/api/notifications/smtp/${id}`, { method: "DELETE" });
        if (response.ok) loadSMTPConfigs();
    } catch (error) {
        alert("Error deleting SMTP config");
    }
};

// Recipient Functions
document.getElementById("add-recipient-btn")?.addEventListener("click", () => {
    document.getElementById("recipient-modal-title").textContent = "Add Recipient";
    document.getElementById("recipient-form").reset();
    document.getElementById("recipient-id").value = "";
    loadSMTPConfigsForSelect();
    recipientModal.classList.add("active");
});

document.getElementById("close-recipient-modal-btn")?.addEventListener("click", () => {
    recipientModal.classList.remove("active");
});

recipientTypeFilter?.addEventListener("change", () => {
    loadRecipients();
});

document.getElementById("recipient-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("recipient-id").value;
    const data = {
        name: document.getElementById("recipient-name").value,
        email: document.getElementById("recipient-email").value,
        type: document.getElementById("recipient-type").value,
        phone: document.getElementById("recipient-phone").value,
        company: document.getElementById("recipient-company").value,
        address: document.getElementById("recipient-address").value,
        notes: document.getElementById("recipient-notes").value,
        smtp_config_id: document.getElementById("recipient-smtp-config").value || null
    };
    
    try {
        const url = id ? `/api/notifications/recipients/${id}` : "/api/notifications/recipients";
        const method = id ? "PUT" : "POST";
        const response = await apiCall(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        if (response && response.ok) {
            recipientModal.classList.remove("active");
            loadRecipients();
        } else {
            alert("Error saving recipient");
        }
    } catch (error) {
        alert("Error: " + error.message);
    }
});

async function loadRecipients() {
    try {
        const type = recipientTypeFilter?.value || "";
        const url = type ? `/api/notifications/recipients?type=${type}` : "/api/notifications/recipients";
        const response = await apiCall(url);
        if (!response) return;
        const data = await response.json();
        recipientsList.innerHTML = data.recipients.length === 0
            ? "<div class='empty-state'><p>No recipients. Add one to get started.</p></div>"
            : data.recipients.map(rec => `
                <div class="recipient-card">
                    <h3>${rec.name}</h3>
                    <p><strong>Type:</strong> ${rec.type}</p>
                    <p><strong>Email:</strong> ${rec.email}</p>
                    ${rec.company ? `<p><strong>Company:</strong> ${rec.company}</p>` : ""}
                    <div class="card-actions">
                        <button onclick="editRecipient(${rec.id})">Edit</button>
                        <button onclick="deleteRecipient(${rec.id})" class="delete-btn">Delete</button>
                        <button onclick="sendNotificationToRecipient(${rec.id})" class="send-btn">Send Now</button>
                    </div>
                </div>
            `).join("");
    } catch (error) {
        console.error("Error loading recipients:", error);
    }
}

async function loadSMTPConfigsForSelect() {
    try {
        const response = await apiCall("/api/notifications/smtp");
        const data = await response.json();
        const select = document.getElementById("recipient-smtp-config");
        select.innerHTML = '<option value="">Use Default</option>' +
            data.configs.map(c => `<option value="${c.id}">${c.name}</option>`).join("");
    } catch (error) {
        console.error("Error loading SMTP configs:", error);
    }
}

window.editRecipient = async function(id) {
    const response = await apiCall(`/api/notifications/recipients/${id}`);
    const data = await response.json();
    const rec = data.recipient;
    document.getElementById("recipient-id").value = id;
    document.getElementById("recipient-name").value = rec.name;
    document.getElementById("recipient-email").value = rec.email;
    document.getElementById("recipient-type").value = rec.type;
    document.getElementById("recipient-phone").value = rec.phone || "";
    document.getElementById("recipient-company").value = rec.company || "";
    document.getElementById("recipient-address").value = rec.address || "";
    document.getElementById("recipient-notes").value = rec.notes || "";
    await loadSMTPConfigsForSelect();
    if (rec.smtp_config_id) {
        document.getElementById("recipient-smtp-config").value = rec.smtp_config_id;
    }
    document.getElementById("recipient-modal-title").textContent = "Edit Recipient";
    recipientModal.classList.add("active");
};

window.deleteRecipient = async function(id) {
    if (!confirm("Delete this recipient?")) return;
    try {
        const response = await apiCall(`/api/notifications/recipients/${id}`, { method: "DELETE" });
        if (response.ok) loadRecipients();
    } catch (error) {
        alert("Error deleting recipient");
    }
};

window.sendNotificationToRecipient = async function(id) {
    const type = prompt("Notification type (payment_reminder, payment_request, custom):", "payment_reminder");
    if (!type) return;
    try {
        const response = await apiCall("/api/notifications/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                recipient_id: id,
                notification_type: type,
                context: {}
            })
        });
        const data = await response.json();
        if (data.success) {
            alert("Notification sent successfully!");
            loadHistory();
        } else {
            alert("Error: " + (data.error || "Failed to send"));
        }
    } catch (error) {
        alert("Error: " + error.message);
    }
};

// Schedule Functions
document.getElementById("add-schedule-btn")?.addEventListener("click", () => {
    document.getElementById("schedule-modal-title").textContent = "Create Schedule";
    document.getElementById("schedule-form").reset();
    document.getElementById("schedule-id").value = "";
    document.getElementById("schedule-interval").value = "7";
    document.getElementById("schedule-enabled").checked = true;
    loadRecipientsForSelect();
    scheduleModal.classList.add("active");
});

document.getElementById("close-schedule-modal-btn")?.addEventListener("click", () => {
    scheduleModal.classList.remove("active");
});

document.getElementById("schedule-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("schedule-id").value;
    const data = {
        name: document.getElementById("schedule-name").value,
        recipient_id: parseInt(document.getElementById("schedule-recipient").value),
        notification_type: document.getElementById("schedule-type").value,
        interval_days: parseInt(document.getElementById("schedule-interval").value),
        enabled: document.getElementById("schedule-enabled").checked,
        payment_link: document.getElementById("schedule-payment-link").value || null,
        email_template: document.getElementById("schedule-template").value || null,
        trigger_condition: document.getElementById("schedule-trigger").value || null
    };
    
    try {
        const url = id ? `/api/notifications/schedules/${id}` : "/api/notifications/schedules";
        const method = id ? "PUT" : "POST";
        const response = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        if (response.ok) {
            scheduleModal.classList.remove("active");
            loadSchedules();
        } else {
            alert("Error saving schedule");
        }
    } catch (error) {
        alert("Error: " + error.message);
    }
});

async function loadSchedules() {
    try {
        const response = await apiCall("/api/notifications/schedules");
        if (!response || !response.ok) {
            console.error("Failed to load schedules:", response?.status);
            return;
        }
        const data = await response.json();
        schedulesList.innerHTML = data.schedules.length === 0
            ? "<div class='empty-state'><p>No schedules. Create one to get started.</p></div>"
            : await Promise.all(data.schedules.map(async sched => {
                const recResponse = await apiCall(`/api/notifications/recipients/${sched.recipient_id}`);
                const recData = await recResponse.json();
                const recipient = recData.recipient;
                
                // Load payment info if it's a payment-based schedule
                let paymentInfo = "";
                if (sched.payment_id) {
                    try {
                        const paymentResponse = await apiCall(`/api/erp/payments/${sched.payment_id}`);
                        if (!paymentResponse || !paymentResponse.ok) return null;
                        const paymentData = await paymentResponse.json();
                        const payment = paymentData.payment;
                        paymentInfo = `<p><strong>💳 Payment:</strong> $${parseFloat(payment.amount).toLocaleString('en-US', {minimumFractionDigits: 2})} - Due: ${payment.due_date}</p>`;
                    } catch (e) {
                        paymentInfo = `<p><strong>💳 Payment ID:</strong> ${sched.payment_id}</p>`;
                    }
                }
                
                let scheduleDetails = "";
                if (sched.schedule_type === 'before_due') {
                    scheduleDetails = `<p><strong>⏰ Schedule:</strong> ${sched.days_before_due} days before due date</p>`;
                } else if (sched.schedule_type === 'date') {
                    scheduleDetails = `<p><strong>📅 Scheduled Date:</strong> ${sched.scheduled_date || 'N/A'}</p>`;
                } else {
                    scheduleDetails = `<p><strong>🔄 Interval:</strong> Every ${sched.interval_days || 'N/A'} days</p>`;
                }
                
                return `
                    <div class="schedule-card">
                        <h3>${sched.name} ${sched.enabled ? "✅" : "❌"}</h3>
                        <p><strong>👤 Recipient:</strong> ${recipient.name} (${recipient.type})</p>
                        <p><strong>📧 Type:</strong> ${sched.notification_type.replace('_', ' ')}</p>
                        <p><strong>📋 Schedule Type:</strong> ${sched.schedule_type || 'interval'}</p>
                        ${scheduleDetails}
                        ${paymentInfo}
                        ${sched.next_send_at ? `<p><strong>⏭️ Next Send:</strong> ${sched.next_send_at}</p>` : ""}
                        ${sched.last_sent_at ? `<p><strong>📬 Last Sent:</strong> ${sched.last_sent_at}</p>` : ""}
                        <div class="card-actions">
                            ${sched.schedule_type === 'before_due' && sched.payment_id ? 
                                `<button onclick="showCreateRemindersModal(${sched.payment_id})" class="action-btn">Update Reminders</button>` : 
                                `<button onclick="editSchedule(${sched.id})" class="action-btn">Edit</button>`}
                            <button onclick="deleteSchedule(${sched.id})" class="delete-btn">Delete</button>
                            <button onclick="sendScheduleNotification(${sched.id})" class="send-btn">Send Now</button>
                        </div>
                    </div>
                `;
            })).then(html => html.join(""));
    } catch (error) {
        console.error("Error loading schedules:", error);
    }
}

async function loadRecipientsForSelect() {
    try {
        const response = await apiCall("/api/notifications/recipients");
        const data = await response.json();
        const select = document.getElementById("schedule-recipient");
        select.innerHTML = '<option value="">Select Recipient</option>' +
            data.recipients.map(r => `<option value="${r.id}">${r.name} (${r.type})</option>`).join("");
    } catch (error) {
        console.error("Error loading recipients:", error);
    }
}

window.editSchedule = async function(id) {
    const response = await apiCall(`/api/notifications/schedules/${id}`);
    const data = await response.json();
    const sched = data.schedule;
    document.getElementById("schedule-id").value = id;
    document.getElementById("schedule-name").value = sched.name;
    document.getElementById("schedule-recipient").value = sched.recipient_id;
    document.getElementById("schedule-type").value = sched.notification_type;
    document.getElementById("schedule-interval").value = sched.interval_days;
    document.getElementById("schedule-payment-link").value = sched.payment_link || "";
    document.getElementById("schedule-template").value = sched.email_template || "";
    document.getElementById("schedule-trigger").value = sched.trigger_condition || "";
    document.getElementById("schedule-enabled").checked = sched.enabled;
    await loadRecipientsForSelect();
    document.getElementById("schedule-modal-title").textContent = "Edit Schedule";
    scheduleModal.classList.add("active");
};

window.deleteSchedule = async function(id) {
    if (!confirm("Delete this schedule? This will remove all reminder notifications for this schedule.")) return;
    try {
        const response = await apiCall(`/api/notifications/schedules/${id}`, { method: "DELETE" });
        if (response.ok) {
            loadSchedules();
            // Also reload payments if we're in ERP view to update button states
            if (document.getElementById("payments-tab")?.classList.contains("active")) {
                loadPayments();
            }
        } else {
            alert("Error deleting schedule");
        }
    } catch (error) {
        alert("Error deleting schedule: " + error.message);
    }
};

window.sendScheduleNotification = async function(id) {
    try {
        const response = await apiCall("/api/notifications/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                schedule_id: id,
                notification_type: "custom",
                context: {}
            })
        });
        const data = await response.json();
        if (data.success) {
            alert("Notification sent successfully!");
            loadHistory();
        } else {
            alert("Error: " + (data.error || "Failed to send"));
        }
    } catch (error) {
        alert("Error: " + error.message);
    }
};

// History Functions
document.getElementById("refresh-history-btn")?.addEventListener("click", () => {
    loadHistory();
});

async function loadHistory() {
    try {
        const response = await apiCall("/api/notifications/history?limit=50");
        if (!response || !response.ok) {
            console.error("Failed to load history:", response?.status);
            return;
        }
        const data = await response.json();
        historyList.innerHTML = data.history.length === 0
            ? "<div class='empty-state'><p>No notification history.</p></div>"
            : await Promise.all(data.history.map(async entry => {
                const recResponse = await apiCall(`/api/notifications/recipients/${entry.recipient_id}`);
                if (!recResponse || !recResponse.ok) return null;
                const recData = await recResponse.json();
                const recipient = recData.recipient;
                const statusIcon = entry.status === "sent" ? "✅" : "❌";
                return `
                    <div class="history-item">
                        <div class="history-header">
                            <span>${statusIcon}</span>
                            <strong>${recipient.name}</strong>
                            <span class="history-date">${new Date(entry.sent_at).toLocaleString()}</span>
                        </div>
                        <p><strong>Subject:</strong> ${entry.subject}</p>
                        <p><strong>Type:</strong> ${entry.notification_type}</p>
                        ${entry.error_message ? `<p class="error">Error: ${entry.error_message}</p>` : ""}
                    </div>
                `;
            })).then(html => html.join(""));
    } catch (error) {
        console.error("Error loading history:", error);
    }
}

// Load initial data when notifications view is accessed
navButtons.forEach(button => {
    button.addEventListener("click", () => {
        if (button.dataset.view === "notifications") {
            loadSMTPConfigs();
            loadRecipients();
            loadSchedules();
            loadHistory();
        } else if (button.dataset.view === "erp") {
            loadPayments();
        }
    });
});

// ==================== ERP FUNCTIONALITY ====================

// ERP Tab switching
const erpTabs = document.querySelectorAll("#erp-view .tab-button");
const erpTabContents = document.querySelectorAll("#erp-view .tab-content");

erpTabs.forEach(tab => {
    tab.addEventListener("click", () => {
        const tabName = tab.dataset.tab;
        erpTabs.forEach(t => t.classList.remove("active"));
        erpTabContents.forEach(c => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(`${tabName}-tab`).classList.add("active");
    });
});

// Generate Mock Data
document.getElementById("generate-mock-data-btn")?.addEventListener("click", async () => {
    if (!confirm("Generate mock payment data? This will add sample payments.")) return;
    try {
        const response = await apiCall("/api/erp/generate-mock-data", { method: "POST" });
        const data = await response.json();
        if (data.success) {
            alert("Mock data generated successfully!");
            loadPayments();
        } else {
            alert("Error generating mock data");
        }
    } catch (error) {
        alert("Error: " + error.message);
    }
});

// Payments Functions
document.getElementById("add-payment-btn")?.addEventListener("click", async () => {
    document.getElementById("payment-modal-title").textContent = "Add Payment";
    document.getElementById("payment-form").reset();
    document.getElementById("payment-id").value = "";
    document.getElementById("payment-status").value = "pending";
    document.getElementById("payment-type").value = "receive";
    updatePaymentFormFields();
    document.getElementById("payment-modal").classList.add("active");
});

document.getElementById("close-payment-modal-btn")?.addEventListener("click", () => {
    document.getElementById("payment-modal").classList.remove("active");
});

// Close payment modal on outside click or Escape
const paymentModal = document.getElementById("payment-modal");
paymentModal?.addEventListener("click", (e) => {
    if (e.target === paymentModal) {
        paymentModal.classList.remove("active");
    }
});
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && paymentModal?.classList.contains("active")) {
        paymentModal.classList.remove("active");
    }
});

document.getElementById("close-reminder-modal-btn")?.addEventListener("click", () => {
    document.getElementById("reminder-modal").classList.remove("active");
});

// Close reminder modal on outside click or Escape
const reminderModal = document.getElementById("reminder-modal");
reminderModal?.addEventListener("click", (e) => {
    if (e.target === reminderModal) {
        reminderModal.classList.remove("active");
    }
});
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && reminderModal?.classList.contains("active")) {
        reminderModal.classList.remove("active");
    }
});

// Payment type change handler - show/hide relevant fields
document.getElementById("payment-type")?.addEventListener("change", () => {
    updatePaymentFormFields();
});

document.getElementById("payment-type-filter")?.addEventListener("change", () => {
    loadPayments();
});

document.getElementById("payment-status-filter")?.addEventListener("change", () => {
    loadPayments();
});

document.getElementById("payment-entity-search")?.addEventListener("input", (e) => {
    loadPayments();
});

function updatePaymentFormFields() {
    const paymentType = document.getElementById("payment-type")?.value;
    const clientFieldsGroup = document.getElementById("client-fields-group");
    const clientEmailGroup = document.getElementById("client-email-group");
    
    if (paymentType === "receive") {
        // Receive from client - show client name and email fields
        if (clientFieldsGroup) clientFieldsGroup.style.display = "block";
        if (clientEmailGroup) clientEmailGroup.style.display = "block";
    } else if (paymentType === "send") {
        // Send to worker or vendor - hide client fields
        if (clientFieldsGroup) clientFieldsGroup.style.display = "none";
        if (clientEmailGroup) clientEmailGroup.style.display = "none";
    }
}


document.getElementById("payment-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("payment-id").value;
    const paymentType = document.getElementById("payment-type").value;
    
    // Get client name and email for receive payments
    let clientName = "";
    let clientEmail = "";
    
    if (paymentType === "receive") {
        clientName = document.getElementById("payment-client-name").value.trim();
        clientEmail = document.getElementById("payment-client-email").value.trim();
        
        if (!clientName) {
            alert("Please enter client name");
            return;
        }
        if (!clientEmail) {
            alert("Please enter client email");
            return;
        }
    }
    
    const data = {
        payment_type: paymentType,
        entity_type: paymentType === "receive" ? "client" : "other",
        entity_id: 0,
        client_name: clientName,
        client_email: clientEmail,
        amount: parseFloat(document.getElementById("payment-amount").value),
        due_date: document.getElementById("payment-due-date").value,
        invoice_number: document.getElementById("payment-invoice-number").value || null,
        project_name: document.getElementById("payment-project-name").value || null,
        description: document.getElementById("payment-description").value || null,
        status: document.getElementById("payment-status").value,
        payment_link: document.getElementById("payment-link").value || null
    };
    
    try {
        const url = id ? `/api/erp/payments/${id}` : "/api/erp/payments";
        const method = id ? "PUT" : "POST";
        const response = await apiCall(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        if (response && response.ok) {
            document.getElementById("payment-modal").classList.remove("active");
            loadPayments();
        } else {
            const errorData = await response.json();
            alert("Error saving payment: " + (errorData.detail || "Unknown error"));
        }
    } catch (error) {
        alert("Error: " + error.message);
    }
});

async function loadPayments() {
    try {
        const type = document.getElementById("payment-type-filter")?.value || "";
        const status = document.getElementById("payment-status-filter")?.value || "";
        const searchQuery = document.getElementById("payment-entity-search")?.value.toLowerCase().trim() || "";
        let url = "/api/erp/payments?";
        if (type) url += `payment_type=${type}&`;
        if (status) url += `status=${status}&`;
        
        const response = await apiCall(url);
        if (!response) return;
        const data = await response.json();
        
        // Update stats
        const dueSoonResponse = await apiCall("/api/erp/payments/due-soon?days=7");
        if (dueSoonResponse) {
            const dueSoonData = await dueSoonResponse.json();
            document.getElementById("due-soon-count").textContent = dueSoonData.count || 0;
        }
        
        const overdueResponse = await apiCall("/api/erp/payments/overdue");
        if (overdueResponse) {
            const overdueData = await overdueResponse.json();
            document.getElementById("overdue-count").textContent = overdueData.count || 0;
        }
        
        const getEntityName = (payment) => {
            // Use client_name if available, otherwise fallback to entity_type
            if (payment.client_name) {
                return payment.client_name;
            }
            return `${payment.entity_type} #${payment.entity_id}`;
        };
        
        // Filter payments by search query
        let filteredPayments = data.payments;
        if (searchQuery) {
            filteredPayments = data.payments.filter(p => {
                const entityName = getEntityName(p).toLowerCase();
                return entityName.includes(searchQuery);
            });
        }
        
        // Check for existing reminders for each payment
        const paymentsWithReminders = await Promise.all(
            filteredPayments.map(async (p) => {
                if (p.status === 'pending' || p.status === 'partial') {
                    try {
                        const remindersResponse = await apiCall(`/api/erp/payments/${p.id}/reminders`);
                        const remindersData = await remindersResponse.json();
                        return { ...p, hasReminders: remindersData.exists };
                    } catch (e) {
                        return { ...p, hasReminders: false };
                    }
                }
                return { ...p, hasReminders: false };
            })
        );
        
        const list = document.getElementById("payments-list");
        list.innerHTML = paymentsWithReminders.length === 0
            ? "<div class='empty-state'><p>No payments found. Add one or generate mock data.</p></div>"
            : `<table class="payments-table-content">
                <thead>
                    <tr>
                        <th>Type</th>
                        <th>Entity</th>
                        <th>Amount</th>
                        <th>Due Date</th>
                        <th>Status</th>
                        <th>Project</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${paymentsWithReminders.map(p => `
                        <tr class="${p.status === 'overdue' ? 'overdue-row' : ''}">
                            <td>${p.payment_type === 'receive' ? '📥 Receive' : '📤 Send'}</td>
                            <td>${getEntityName(p)}</td>
                            <td>$${parseFloat(p.amount).toLocaleString('en-US', {minimumFractionDigits: 2})}</td>
                            <td>${p.due_date}</td>
                            <td><span class="status-badge status-${p.status}">${p.status}</span></td>
                            <td>${p.project_name || 'N/A'}</td>
                            <td>
                                <button onclick="editPayment(${p.id})" class="action-btn">Edit</button>
                                <button onclick="deletePayment(${p.id})" class="delete-btn">Delete</button>
                                ${p.status === 'pending' || p.status === 'partial' ? 
                                    `<button onclick="showCreateRemindersModal(${p.id})" class="send-btn ${p.hasReminders ? 'update-btn' : ''}">${p.hasReminders ? 'Update Reminders' : 'Create Reminders'}</button>` : ''}
                            </td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>`;
    } catch (error) {
        console.error("Error loading payments:", error);
    }
}

window.editPayment = async function(id) {
    const response = await apiCall(`/api/erp/payments/${id}`);
    const data = await response.json();
    const p = data.payment;
    
    document.getElementById("payment-id").value = id;
    document.getElementById("payment-type").value = p.payment_type;
    document.getElementById("payment-amount").value = p.amount;
    document.getElementById("payment-due-date").value = p.due_date;
    document.getElementById("payment-invoice-number").value = p.invoice_number || "";
    document.getElementById("payment-project-name").value = p.project_name || "";
    document.getElementById("payment-description").value = p.description || "";
    document.getElementById("payment-status").value = p.status;
    document.getElementById("payment-link").value = p.payment_link || "";
    
    updatePaymentFormFields();
    
    // Set client name and email if available
    if (p.client_name) {
        document.getElementById("payment-client-name").value = p.client_name;
    }
    if (p.client_email) {
        document.getElementById("payment-client-email").value = p.client_email;
    }
    
    document.getElementById("payment-modal-title").textContent = "Edit Payment";
    document.getElementById("payment-modal").classList.add("active");
};

window.deletePayment = async function(id) {
    if (!confirm("Delete this payment?")) return;
    try {
        const response = await apiCall(`/api/erp/payments/${id}`, { method: "DELETE" });
        if (response.ok) loadPayments();
    } catch (error) {
        alert("Error deleting payment");
    }
};

window.showCreateRemindersModal = async function(paymentId) {
    // Load payment details
    const paymentResponse = await apiCall(`/api/erp/payments/${paymentId}`);
    const paymentData = await paymentResponse.json();
    const payment = paymentData.payment;
    
    // Check if reminders already exist
    const remindersResponse = await apiCall(`/api/erp/payments/${paymentId}/reminders`);
    const remindersData = await remindersResponse.json();
    const existingReminders = remindersData.schedules || [];
    
    document.getElementById("reminder-payment-id").value = paymentId;
    document.getElementById("reminder-payment-info").textContent = 
        `Payment: $${parseFloat(payment.amount).toLocaleString('en-US', {minimumFractionDigits: 2})} - Due: ${payment.due_date}`;
    
    // If reminders exist, populate with existing values
    if (existingReminders.length > 0) {
        const daysBefore = existingReminders
            .map(s => s.days_before_due)
            .filter(d => d !== null)
            .sort((a, b) => b - a) // Sort descending
            .join(',');
        document.getElementById("reminder-days-before").value = daysBefore || "7,3,1";
        
        // Get email template from first schedule (they should all have the same template)
        const emailTemplate = existingReminders[0].email_template || "";
        document.getElementById("reminder-email-template").value = emailTemplate;
    } else {
        // Set default days before due
        document.getElementById("reminder-days-before").value = "7,3,1";
        // Clear email template
        document.getElementById("reminder-email-template").value = "";
    }
    
    document.getElementById("reminder-modal").classList.add("active");
};

window.createPaymentReminders = async function() {
    const paymentId = parseInt(document.getElementById("reminder-payment-id").value);
    const daysBeforeStr = document.getElementById("reminder-days-before").value;
    const emailTemplate = document.getElementById("reminder-email-template").value;
    
    if (!paymentId) {
        alert("Payment ID is required");
        return;
    }
    
    // Parse days before
    const daysBefore = daysBeforeStr.split(',').map(d => parseInt(d.trim())).filter(d => !isNaN(d));
    if (daysBefore.length === 0) {
        daysBefore.push(7, 3, 1); // Default
    }
    
    try {
        const response = await apiCall(`/api/erp/payments/${paymentId}/create-reminders`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                days_before: daysBefore,
                email_template: emailTemplate || null
            })
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: "Unknown error" }));
            alert("Error creating reminders: " + (errorData.detail || `HTTP ${response.status}`));
            return;
        }
        
        const result = await response.json();
        if (result.success) {
            const hasInstant = daysBefore.includes(0);
            const isUpdate = result.updated;
            let message = `${isUpdate ? '✅ Updated' : '✅ Created'} ${result.count} reminder schedule(s) successfully!`;
            if (hasInstant) {
                message += `\n📧 An immediate notification has been sent!`;
            }
            alert(message);
            document.getElementById("reminder-modal").classList.remove("active");
            loadPayments(); // Reload to update button text
            // Reload schedules in notifications view if it's active
            if (document.getElementById("schedules-tab")?.classList.contains("active")) {
                loadSchedules();
            }
        } else {
            alert("Error creating reminders: " + (result.detail || "Unknown error"));
        }
    } catch (error) {
        alert("Error: " + error.message);
    }
};
