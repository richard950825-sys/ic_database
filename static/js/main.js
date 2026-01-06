// DOM Elements
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const chatMessages = document.getElementById('chatContainer');
const fileInput = document.getElementById('fileInput');
const dropZone = document.getElementById('dropZone');
const uploadBtn = document.getElementById('uploadBtn');
const taskList = document.getElementById('taskList');
const previewModal = document.getElementById('previewModal');
const previewContent = document.getElementById('previewContent');
const closeModal = document.querySelector('.close-modal');

// State
let pollingIntervals = {}; // taskId -> intervalId

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Auto-resize textarea
    chatInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        if (this.value === '') this.style.height = 'auto';
    });

    // Enter to send
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    sendBtn.addEventListener('click', sendMessage);

    // File Upload
    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });

    // Initial Load
    loadFileList();
});

// Tab Switching
function switchTab(tabName) {
    // Hide all views
    document.querySelectorAll('.view-section').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    // Show selected
    document.getElementById(`view-${tabName}`).classList.remove('hidden');

    // Activate nav button
    const btn = document.querySelector(`.nav-item[onclick="switchTab('${tabName}')"]`);
    if (btn) btn.classList.add('active');

    if (tabName === 'docs') {
        loadFileList();
    }
}

// File Handling
async function handleFiles(files) {
    if (!files.length) return;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        if (files[i].type === 'application/pdf') {
            formData.append('files', files[i]);
        }
    }

    if (!formData.has('files')) {
        alert('请选择 PDF 文件');
        return;
    }

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error('上传请求失败');

        const tasks = await response.json();
        tasks.forEach(task => {
            createTaskElement(task.task_id, task.filename);
            startPolling(task.task_id);
        });

    } catch (error) {
        console.error('Upload Error:', error);
        alert('上传失败: ' + error.message);
    }

    // Reset input
    fileInput.value = '';
}

// Task Progress UI
function createTaskElement(taskId, filename) {
    const div = document.createElement('div');
    div.className = 'task-item';
    div.id = `task-${taskId}`;
    div.innerHTML = `
        <div class="task-header">
            <span class="task-filename" title="${filename}">${filename}</span>
            <button class="btn-cancel" onclick="cancelTask('${taskId}')">取消</button>
        </div>
        <div class="progress-track">
            <div class="progress-fill" style="width: 0%"></div>
        </div>
        <div class="task-status">
            <span class="status-msg">等待中...</span>
            <span class="status-percent">0%</span>
        </div>
        <div class="task-details" style="font-size: 0.75rem; color: #94a3b8; margin-top: 0.25rem;"></div>
    `;
    taskList.prepend(div);
}

function updateTaskUI(taskId, data) {
    const el = document.getElementById(`task-${taskId}`);
    if (!el) return;

    const fill = el.querySelector('.progress-fill');
    const msg = el.querySelector('.status-msg');
    const percent = el.querySelector('.status-percent');
    const details = el.querySelector('.task-details');
    const cancelBtn = el.querySelector('.btn-cancel');

    fill.style.width = `${data.progress}%`;
    msg.textContent = data.message;
    percent.textContent = `${data.progress}%`;
    if (data.details) details.textContent = data.details;

    if (data.status === 'completed') {
        fill.style.backgroundColor = '#10b981'; // Green
        cancelBtn.remove();
        loadFileList(); // Refresh file list
        setTimeout(() => {
            // Optional: fade out after 5 seconds
            // el.style.opacity = '0.5';
        }, 5000);
    } else if (data.status === 'error' || data.status === 'cancelled') {
        fill.style.backgroundColor = '#ef4444'; // Red
        cancelBtn.remove();
    }
}

function startPolling(taskId) {
    if (pollingIntervals[taskId]) return;

    pollingIntervals[taskId] = setInterval(async () => {
        try {
            const res = await fetch(`/api/task/${taskId}`);
            if (!res.ok) { // Task might be gone or server error
                clearInterval(pollingIntervals[taskId]);
                return;
            }
            const data = await res.json();
            updateTaskUI(taskId, data);

            if (data.status === 'completed' || data.status === 'error' || data.status === 'cancelled') {
                clearInterval(pollingIntervals[taskId]);
                delete pollingIntervals[taskId];
            }
        } catch (e) {
            console.error('Polling error', e);
        }
    }, 1000); // Poll every 1s
}

async function cancelTask(taskId) {
    try {
        await fetch(`/api/task/${taskId}/cancel`, { method: 'POST' });
        // UI update will happen on next poll or immediately
    } catch (e) {
        console.error('Cancel failed', e);
    }
}

// Chat Logic
async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    // Add User Message
    addMessage(text, 'user');
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Show Loading
    const loadingId = addLoadingMessage();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: text })
        });

        if (!response.ok) throw new Error('Failed to get response');

        const data = await response.json();

        // Remove Loading
        removeMessage(loadingId);

        // Add AI Message
        addMessage(data.answer, 'ai', data.sources);

    } catch (error) {
        removeMessage(loadingId);
        addMessage('抱歉，发生了错误。请稍后重试。', 'ai');
        console.error(error);
    }
}

function addMessage(text, type, sources = []) {
    const div = document.createElement('div');
    div.className = `message ${type}-message`;

    let avatarHtml = type === 'ai'
        ? '<div class="avatar"><i class="fa-solid fa-robot"></i></div>'
        : '<div class="avatar"><i class="fa-regular fa-user"></i></div>';

    let contentHtml = marked.parse(text);

    // Add sources if any
    if (sources && sources.length > 0) {
        contentHtml += '<div class="sources-list"><strong>参考来源:</strong><br>';
        sources.slice(0, 3).forEach(src => {
            const pageInfo = src.page ? `P${src.page}` : '';
            const filename = src.file_name.split('/').pop();
            contentHtml += `<div class="source-item" onclick="showPreview('${src.file_name}', ${src.page})">
                <i class="fa-regular fa-file-pdf"></i>
                <span>${filename} ${pageInfo}</span>
                <!-- <span class="source-tag">相似度 ${(src.score * 100).toFixed(0)}%</span> -->
            </div>`;
        });
        contentHtml += '</div>';
    }

    div.innerHTML = `${avatarHtml}<div class="message-content">${contentHtml}</div>`;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Highlight code blocks
    div.querySelectorAll('pre code').forEach((block) => {
        // hljs.highlightBlock(block); // If highlight.js is used
    });
}

function addLoadingMessage() {
    const id = 'loading-' + Date.now();
    const div = document.createElement('div');
    div.className = 'message ai-message';
    div.id = id;
    div.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="message-content">
            <div class="typing-indicator">
                <span>.</span><span>.</span><span>.</span>
            </div>
        </div>
    `;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return id;
}

function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

// Document Management
async function loadFileList() {
    const tbody = document.getElementById('file-list-body');
    if (!tbody) return; // If on wrong page

    try {
        const res = await fetch('/api/files');
        const files = await res.json();

        tbody.innerHTML = '';
        files.forEach(file => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${file.filename}</td>
                <td>${file.upload_time || '-'}</td>
                <td>${formatSize(file.size)}</td>
                <td><span style="color: #10b981;">已索引</span></td>
                <td>
                    <button class="btn-delete" onclick="deleteFile('${file.filename}')">删除</button>
                </td>
            `;
            tbody.appendChild(tr);
        });

        // Also update sidebar list
        const sidebarList = document.getElementById('fileList');
        // Not implemented in sidebar yet, can rely on doc view

    } catch (e) {
        console.error('Failed to list files', e);
    }
}

async function deleteFile(filename) {
    if (!confirm(`确定要删除 ${filename} 吗？`)) return;

    try {
        const res = await fetch(`/api/files/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });

        if (res.ok) {
            loadFileList(); // Refresh
        } else {
            alert('删除失败');
        }
    } catch (e) {
        alert('删除请求错误');
    }
}

// Utils
function formatSize(bytes) {
    if (!bytes) return '-';
    if (bytes < 1024) return bytes + ' B';
    else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    else return (bytes / 1048576).toFixed(1) + ' MB';
}

function showPreview(filename, page) {
    // Simple placeholder for now, ideally fetch content snippet
    alert(`预览 functionality to be implemented for ${filename}`);
}

// Modal closing
closeModal.addEventListener('click', () => {
    previewModal.classList.remove('visible');
    setTimeout(() => previewModal.classList.add('hidden'), 300);
});
