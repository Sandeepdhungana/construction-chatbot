const API_BASE = "";
let sessionId = window.localStorage.getItem("constructionbot-session") || null;
let selectedFiles = [];

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
        document.getElementById(`${viewName}-view`).classList.add("active");
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
        const response = await fetch(`${API_BASE}/api/upload`, {
            method: "POST",
            body: formData,
        });

        if (!response.ok) {
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
        const response = await fetch(`${API_BASE}/api/files`);
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
                    const response = await fetch(`${API_BASE}/api/files/${encodeURIComponent(fileId)}`, {
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
        const response = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message,
                session_id: sessionId,
            }),
        });
        
        if (!response.ok) {
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
