// State
let selectedFile = null;
let currentJobId = null;
let pollInterval = null;

// DOM elements
const views = {
    upload: document.getElementById('view-upload'),
    processing: document.getElementById('view-processing'),
    error: document.getElementById('view-error'),
    results: document.getElementById('view-results'),
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupDropZone();
    setupSettings();
    document.getElementById('btn-start').addEventListener('click', startProcess);
});

function showView(name) {
    Object.values(views).forEach(v => v.classList.remove('active'));
    views[name].classList.add('active');
}

// ─── Drop Zone ───
function setupDropZone() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFile(fileInput.files[0]);
        }
    });
}

function handleFile(file) {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    const allowed = ['.mp4', '.mov', '.avi', '.mkv', '.webm'];
    if (!allowed.includes(ext)) {
        alert('지원하지 않는 파일 형식입니다.\n지원: ' + allowed.join(', '));
        return;
    }

    selectedFile = file;
    document.getElementById('file-name').textContent = file.name;
    document.getElementById('file-size').textContent = formatSize(file.size);
    document.getElementById('file-info').classList.remove('hidden');
    document.getElementById('btn-start').disabled = false;
}

function formatSize(bytes) {
    if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB';
    if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB';
    return (bytes / 1e3).toFixed(0) + ' KB';
}

// ─── Settings ───
function setupSettings() {
    document.getElementById('settings-toggle').addEventListener('click', () => {
        const body = document.getElementById('settings-body');
        const arrow = document.querySelector('.arrow');
        body.classList.toggle('hidden');
        arrow.textContent = body.classList.contains('hidden') ? '▼' : '▲';
    });

    ['max-shorts', 'min-duration', 'max-duration'].forEach(id => {
        const slider = document.getElementById(id);
        const display = document.getElementById(id + '-val');
        slider.addEventListener('input', () => {
            display.textContent = slider.value;
        });
    });
}

// ─── Process ───
async function startProcess() {
    if (!selectedFile) return;

    showView('processing');
    resetSteps();
    setActiveStep('uploading');

    try {
        // Upload
        const formData = new FormData();
        formData.append('file', selectedFile);

        const xhr = new XMLHttpRequest();
        const uploadPromise = new Promise((resolve, reject) => {
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const pct = Math.round((e.loaded / e.total) * 100);
                    document.getElementById('upload-progress').textContent = pct + '%';
                    document.getElementById('progress-bar').style.width = (pct * 0.1) + '%';
                    document.getElementById('progress-text').textContent = `업로드 중... ${pct}%`;
                }
            });
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(JSON.parse(xhr.responseText));
                } else {
                    try {
                        const err = JSON.parse(xhr.responseText);
                        reject(new Error(err.detail || '업로드 실패'));
                    } catch {
                        reject(new Error('업로드 실패'));
                    }
                }
            });
            xhr.addEventListener('error', () => reject(new Error('네트워크 오류')));
        });

        xhr.open('POST', '/api/jobs/upload');
        xhr.send(formData);

        const uploadResult = await uploadPromise;
        currentJobId = uploadResult.job_id;
        markStepDone('uploading');

        // Start processing
        const settings = {
            max_shorts: parseInt(document.getElementById('max-shorts').value),
            min_duration_sec: parseInt(document.getElementById('min-duration').value),
            max_duration_sec: parseInt(document.getElementById('max-duration').value),
        };

        const processResp = await fetch(`/api/jobs/${currentJobId}/process`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings),
        });

        if (!processResp.ok) {
            const err = await processResp.json();
            throw new Error(err.detail || '처리 시작 실패');
        }

        // Start polling
        startPolling();

    } catch (err) {
        showError(err.message);
    }
}

function startPolling() {
    pollInterval = setInterval(async () => {
        try {
            const resp = await fetch(`/api/jobs/${currentJobId}/status`);
            const data = await resp.json();

            updateProgress(data);

            if (data.status === 'completed') {
                clearInterval(pollInterval);
                await showResults();
            } else if (data.status === 'failed') {
                clearInterval(pollInterval);
                showError(data.error || '알 수 없는 오류가 발생했습니다.');
            }
        } catch (err) {
            // Network error during polling — keep trying
        }
    }, 2000);
}

function updateProgress(data) {
    const stepMap = {
        'extracting_audio': 'extracting_audio',
        'transcribing': 'transcribing',
        'analyzing': 'analyzing',
        'cutting': 'cutting',
    };

    const stepOrder = ['uploading', 'extracting_audio', 'transcribing', 'analyzing', 'cutting'];
    const currentIdx = stepOrder.indexOf(stepMap[data.status] || data.status);

    stepOrder.forEach((step, idx) => {
        if (idx < currentIdx) markStepDone(step);
        else if (idx === currentIdx) setActiveStep(step);
    });

    document.getElementById('progress-bar').style.width = data.progress_percent + '%';
    document.getElementById('progress-text').textContent = data.current_step;
}

function resetSteps() {
    document.querySelectorAll('.step').forEach(s => {
        s.classList.remove('active', 'done');
    });
}

function setActiveStep(stepName) {
    document.querySelectorAll('.step').forEach(s => {
        if (s.dataset.step === stepName) {
            s.classList.add('active');
            s.classList.remove('done');
        }
    });
}

function markStepDone(stepName) {
    document.querySelectorAll('.step').forEach(s => {
        if (s.dataset.step === stepName) {
            s.classList.remove('active');
            s.classList.add('done');
        }
    });
}

// ─── Results ───
async function showResults() {
    try {
        const resp = await fetch(`/api/jobs/${currentJobId}/results`);
        const data = await resp.json();

        const grid = document.getElementById('shorts-grid');
        grid.innerHTML = '';

        data.shorts.forEach((short, idx) => {
            const card = document.createElement('div');
            card.className = 'short-card';
            card.innerHTML = `
                <video controls preload="metadata"
                    src="${short.download_url}">
                </video>
                <div class="short-card-body">
                    <div class="short-title">${escapeHtml(short.title)}</div>
                    <div class="short-meta">
                        <span class="badge badge-score">점수 ${short.virality_score}/10</span>
                        <span class="badge badge-time">${formatTime(short.start_time)} - ${formatTime(short.end_time)}</span>
                        <span class="badge badge-time">${short.duration}초</span>
                    </div>
                    <div class="short-hook">"${escapeHtml(short.hook_text)}"</div>
                    <button class="toggle-reasoning" onclick="toggleReasoning(this)">분석 이유 보기 ▼</button>
                    <div class="short-reasoning">${escapeHtml(short.reasoning)}</div>
                    <a href="${short.download_url}" download class="short-download">다운로드</a>
                </div>
            `;
            grid.appendChild(card);
        });

        showView('results');
    } catch (err) {
        showError('결과를 불러오는데 실패했습니다.');
    }
}

function toggleReasoning(btn) {
    const reasoning = btn.nextElementSibling;
    reasoning.classList.toggle('show');
    btn.textContent = reasoning.classList.contains('show') ? '분석 이유 접기 ▲' : '분석 이유 보기 ▼';
}

function downloadAll() {
    const links = document.querySelectorAll('.short-download');
    links.forEach((link, idx) => {
        setTimeout(() => link.click(), idx * 500);
    });
}

// ─── Error ───
function showError(message) {
    document.getElementById('error-message').textContent = message;
    showView('error');
}

// ─── Reset ───
function resetToUpload() {
    if (pollInterval) clearInterval(pollInterval);
    selectedFile = null;
    currentJobId = null;
    document.getElementById('file-input').value = '';
    document.getElementById('file-info').classList.add('hidden');
    document.getElementById('btn-start').disabled = true;
    showView('upload');
}

// ─── Helpers ───
function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
